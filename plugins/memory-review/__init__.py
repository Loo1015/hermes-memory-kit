"""memory-review — LLM 审核 memory()/skills() 写入的 pre_tool_call 插件。

每次 memory/skills 工具调用，把 operations 全文 + 磁盘上的 MEMORY.md/USER.md 现状 +
浓缩版写入规则发给一个「从 Hermes 自己配置里选出来的模型」，三态裁决：
  approve → 返回 None，放行
  reject  → {"action": "block"}，理由作为 message（模型可见，可改写重试）
  defer   → 默认 block 带复核提示（defer_blocks: true），可改为放行
失败语义 = fail open：审核模型超时/连不上/返回解析不了 → 一律放行，交给
memory-cleanup 事后兜底。本插件永不 raise（raise 在 pre_tool_call 里等于 fail closed）。

审核模型从 Hermes config 解析（零新增凭据）：
  memory_review:
    alias: workbuddy          # 复用 model_aliases 里的条目（model/provider/base_url/key_env）
    # 或者显式指定：
    # provider: local-llama   # providers.<name>，type=openai
    # model: qwen3-4b
    timeout_s: 25
  未配置时默认取 model_aliases 的第一项。
凭据解析：api_key 字面量 | "${VAR}" 引用 | key_env 环境变量名。key 只在内存中使用，
绝不写日志、绝不写文件。
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes" if (Path.home() / ".hermes").exists() else "D:/Hermes"))
_MEMORIES_DIR = _HERMES_HOME / "memories"
_REVIEWABLE_TOOLS = {"memory"}  # skills 自进化走 skill_manage，有意不拦（用户拍板：写差技能不占常驻预算，cleanup 兜底）
_RULES = """你是记忆写入审核员。对提案的 operations 逐条判断，返回严格 JSON：
{"decision":"approve|reject|defer","reason":"<一句话，中文>"}

规则（判不准一律 defer，不要猜）：
1 保留价值：说不出未来什么场景会调用 → reject。一次性调试细节、PR 号、SHA、临时路径、任务进度 → reject。
2 可推导性：能从权威来源（文档、配置、重跑命令）低成本重建的裸事实 → reject；但重建会丢决策理由的保留。
3 重复：与现有条目等价 → reject；新增细节 → 改写合并提示放行；事实已变 → 修订原条目。
4 成本：会话临时状态、极少数场合才有用 → reject。
5 写法：祈使句（"永远/必须…"开头）→ reject 并提示改陈述句。一条捆多个主题 → reject 并要求拆分。
6 归属：关于用户的进 USER.md（target=user），环境事实进 MEMORY.md。放错 target → reject。
MEMORY.md 只收确需全局常驻、无专门归宿的例外。"""


def _plugin_dir() -> Path:
    d = _HERMES_HOME / "pending" / "memory-review"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _receipts_path() -> Path:
    return _plugin_dir() / "receipts.jsonl"


def _unread_background_notes() -> Optional[str]:
    """后台 fork 被 reject/defer 且尚未向前台播报的回执，拼成一行搭车提示。

    播报游标 = seen.json 里记录的 receipts.jsonl 行数（回执只追加，行数即游标）。"""
    try:
        rec = _receipts_path()
        lines = rec.read_text(encoding="utf-8").splitlines() if rec.exists() else []
        seen_file = _plugin_dir() / "seen.json"
        seen = json.loads(seen_file.read_text(encoding="utf-8")) if seen_file.exists() else {}
        cursor = int(seen.get("cursor", 0))
        notes = []
        for line in lines[cursor:]:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if str(r.get("origin", "")).startswith("background") and r.get("verdict") in ("reject", "defer"):
                notes.append(f"{r['verdict']}({r.get('reason', '')[:50]})")
        seen["cursor"] = len(lines)
        seen_file.write_text(json.dumps(seen), encoding="utf-8")
        if not notes:
            return None
        return (f"\n\n📋 后台审核回执 {len(notes)} 条未读：{'；'.join(notes)}"
                f"。/memory-review recent 查看详情。")
    except Exception:
        return None


def _ops_key(args: dict) -> str:
    """operations 内容哈希：approve 通行证与 pending 提案的稳定键。"""
    raw = json.dumps({"t": args.get("target", "memory"), "o": args.get("operations")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _ops_similar(new_ops: list, old_ops: list) -> bool:
    """两条提案是否为「同一提案的改写」：patch 的 old_text 完全一致，或任一内容对相似度 >=0.6。"""
    def _texts(ops):
        out = []
        for o in ops or []:
            if not isinstance(o, dict):
                continue
            if o.get("old_text"):
                out.append(("old", str(o["old_text"])))
            if o.get("content"):
                out.append(("content", str(o["content"])))
        return out
    a, b = _texts(new_ops), _texts(old_ops)
    for ka, ta in a:
        for kb, tb in b:
            if ka == "old" and kb == "old" and ta == tb:
                return True
            if difflib.SequenceMatcher(None, ta, tb).ratio() >= 0.6:
                return True
    return False


def _purge_superseded(args: dict, origin: str, verdict: str) -> int:
    """裁决落点清理：同 origin 的旧 pending 里，若与本次提案构成「改写」关系则删除。

    场景：defer 被拒后模型改写重提 → 新 key 通过/再 defer，旧 pending 成僵尸。
    误删代价 = 少一条待复核，低于僵尸堆积；所有删除都记 superseded 回执可追溯。"""
    n = 0
    try:
        for f in _plugin_dir().glob("*.json"):
            if f.name in _STATE_FILES:
                continue
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(it.get("origin", "")) != str(origin):
                continue
            old_ops = it.get("args", {}).get("operations", [])
            if _ops_similar(args.get("operations") or [], old_ops):
                f.unlink()
                n += 1
                _receipt("superseded", it.get("id", f.stem),
                         f"被同 origin 的新提案取代（新裁决 {verdict}）", origin,
                         it.get("target", "?"))
    except Exception:
        pass  # 清理失败不影响裁决
    return n


_STATE_FILES = ("passes.json", "remind.json", "seen.json", "index.json")


def _pending_items() -> list:
    """待复核提案（排除状态文件）。"""
    out = []
    try:
        for f in _plugin_dir().glob("*.json"):
            if f.name in _STATE_FILES:
                continue
            try:
                out.append((f, json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                out.append((f, {}))
    except Exception:
        pass
    return out


def _pending_notice() -> Optional[str]:
    """每轮注入一行 pending 提醒（pre_llm_call → 用户消息尾，不碰前缀缓存）。

    冷却：默认 30 分钟提醒一次；pending 数与上次播报不同则立即再提醒（新增/清零都要知道）。
    冷却状态存 remind.json，含上次播报时间与条数。"""
    try:
        items = _pending_items()
        n = len(items)
        if not n:
            return None
        cfg = {}
        try:
            cfg = (_load_hermes_config().get("memory_review") or {})
        except Exception:
            pass
        cooldown = int(cfg.get("remind_cooldown_s", 1800))
        rfile = _plugin_dir() / "remind.json"
        state = json.loads(rfile.read_text(encoding="utf-8")) if rfile.exists() else {}
        now = time.time()
        if state.get("n") == n and now - float(state.get("ts", 0)) < cooldown:
            return None
        rfile.write_text(json.dumps({"ts": now, "n": n}), encoding="utf-8")
        oldest = min((str(it.get("ts", "")) for _f, it in items), default="")
        tail = f"，最早 {oldest[5:16].replace('T', ' ')}" if oldest else ""
        return (f"⚠️ memory-review 有 {n} 条待人工复核{tail}。"
                f"用 /memory-review list 查看，approve <id> 放行 / reject <id> 丢弃。")
    except Exception:
        return None


def _receipt(verdict: str, key: str, reason: str, origin: str, target: str, usage: Optional[dict] = None) -> None:
    line = json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "verdict": verdict,
                       "key": key, "origin": origin, "target": target, "reason": reason[:200],
                       **({"usage": usage} if usage else {})},
                      ensure_ascii=False)
    try:
        with open(_plugin_dir() / "receipts.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # 回执写不进去不影响裁决


def _save_pending(args: dict, key: str, reason: str, origin: str) -> bool:
    item = {"id": key, "ts": datetime.now().isoformat(timespec="seconds"), "origin": origin,
            "target": args.get("target", "memory"), "reason": reason[:300],
            "args": {"target": args.get("target", "memory"), "operations": args.get("operations")}}
    try:
        (_plugin_dir() / f"{key}.json").write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except Exception:
        return False


def _load_hermes_config() -> dict:
    import yaml  # hermes 运行环境必带
    return yaml.safe_load((_HERMES_HOME / "config.yaml").read_text(encoding="utf-8")) or {}


def _resolve_endpoint(cfg: dict) -> Optional[Dict[str, str]]:
    """从 Hermes 配置解析审核模型的 endpoint。返回 {url, model, api_key}；解析不了返回 None。"""
    rv = cfg.get("memory_review") or {}
    aliases = cfg.get("model_aliases") or {}
    providers = cfg.get("providers") or {}

    if rv.get("alias"):
        a = aliases.get(rv["alias"]) or {}
        model, prov_name = a.get("model"), a.get("provider")
        base_url, key_ref = a.get("base_url"), a.get("key_env") or a.get("api_key")
    elif rv.get("provider"):
        prov_name, model = rv["provider"], rv.get("model")
        p = providers.get(prov_name) or {}
        base_url, key_ref = p.get("base_url"), p.get("key_env") or p.get("api_key")
    else:
        # 默认：model_aliases 第一项
        for name, a in (aliases or {}).items():
            if isinstance(a, dict) and a.get("model"):
                model, prov_name = a["model"], a.get("provider")
                base_url = a.get("base_url")
                key_ref = a.get("key_env") or a.get("api_key")
                if not base_url:
                    p = providers.get(prov_name) or {}
                    base_url = p.get("base_url")
                    key_ref = p.get("key_env") or p.get("api_key")
                break
        else:
            return None

    if not model or not base_url:
        return None

    key = ""
    if isinstance(key_ref, str) and key_ref:
        m = re.fullmatch(r"\$\{(\w+)\}", key_ref.strip())
        env_name = m.group(1) if m else key_ref
        key = os.environ.get(env_name, "") if env_name else key_ref
    return {"url": base_url.rstrip("/") + "/chat/completions", "model": model, "api_key": key}


def _call_reviewer(endpoint: dict, prompt: str, timeout_s: int) -> Optional[dict]:
    body = json.dumps({
        "model": endpoint["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 200,
    }).encode("utf-8")
    req = urllib.request.Request(endpoint["url"], data=body, headers={
        "Content-Type": "application/json",
        **({"Authorization": f"Bearer {endpoint['api_key']}"} if endpoint["api_key"] else {}),
    })
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage") or None
    if usage:
        logger.info("memory-review: 审核调用 token usage=%s", json.dumps(usage))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    verdict = json.loads(m.group(0)) if m else None
    return verdict, usage


def _memory_files_snapshot() -> str:
    parts = []
    for name in ("MEMORY.md", "USER.md"):
        p = _MEMORIES_DIR / name
        try:
            parts.append(f"=== {name} ===\n" + p.read_text(encoding="utf-8")[:6000])
        except OSError:
            parts.append(f"=== {name} ===（不存在或读不了）")
    return "\n".join(parts)


def _on_pre_tool_call(tool_name: str = "", args: Optional[Dict[str, Any]] = None,
                      **kwargs: Any) -> Optional[Dict[str, str]]:
    if tool_name not in _REVIEWABLE_TOOLS or not isinstance(args, dict):
        return None
    ops = args.get("operations")
    if not isinstance(ops, list) or not ops:
        return None
    key = _ops_key(args)
    origin = "?"
    try:
        from tools.skill_provenance import get_current_write_origin
        origin = get_current_write_origin()
    except Exception:
        try:
            origin = str(kwargs.get("session_id") or "?")
        except Exception:
            pass
    logger.info("memory-review: 拦截到 %s 写入 (origin=%s, ops=%d, key=%s)", tool_name, origin, len(ops), key)

    # approve 通行证：hash 命中即放行（一次性，用完即焚）
    try:
        pass_file = _plugin_dir() / "passes.json"
        passes = json.loads(pass_file.read_text(encoding="utf-8")) if pass_file.exists() else {}
        if key in passes:
            passes.pop(key)
            pass_file.write_text(json.dumps(passes, ensure_ascii=False), encoding="utf-8")
            _receipt("approved-pass", key, "人工批准通行证", origin, args.get("target", "memory"))
            return None
    except Exception:
        pass

    cfg = {}
    try:
        cfg = _load_hermes_config()
    except Exception:
        pass  # fail open：连配置都读不了就放行
    rv = cfg.get("memory_review") or {}
    if rv.get("enabled") is False:
        return None
    try:
        endpoint = _resolve_endpoint(cfg)
        if endpoint is None:
            return None  # 没配置审核模型：放行（部署者没选模型 = 未启用）
        prompt = (
            f"{_RULES}\n\n=== 现有记忆 ===\n{_memory_files_snapshot()}\n\n"
            f"=== 提案写入 ===\ntarget={args.get('target', 'memory')}\n"
            f"{json.dumps(ops, ensure_ascii=False, indent=1)}"
        )
        verdict, usage = _call_reviewer(endpoint, prompt, int(rv.get("timeout_s", 25)))
        if not verdict:
            _receipt("fail-open", key, "审核模型无有效返回", origin, args.get("target", "memory"), usage)
            return None  # fail open
        decision = str(verdict.get("decision", "")).strip().lower()
        reason = str(verdict.get("reason", "")).strip()[:300]
        if decision == "reject":
            _purge_superseded(args, origin, "reject")
            _receipt("reject", key, reason, origin, args.get("target", "memory"), usage)
            return {"action": "block",
                    "message": f"memory-review 拒绝本次写入：{reason or '未说明'}。请按理由修正后重试，或放弃这条记忆。"}
        if decision == "defer":
            if rv.get("defer_blocks", True) and _save_pending(args, key, reason, origin):
                _purge_superseded(args, origin, "defer")
                _receipt("defer", key, reason, origin, args.get("target", "memory"), usage)
                return {"action": "block",
                        "message": (f"memory-review 转人工复核（已存 pending，id={key}）：{reason or '审核模型拿不准'}。"
                                    f"用户可用 /memory-review approve {key} 放行（我随后重发免审落盘），或 reject {key} 丢弃。")}
            _receipt("defer-pass", key, reason, origin, args.get("target", "memory"))
            return None  # defer_blocks=false：放行
        _purge_superseded(args, origin, "approve")
        _receipt("approve", key, reason, origin, args.get("target", "memory"), usage)
        return None  # approve → 放行
    except Exception:
        _receipt("fail-open", key, "审核异常 fail open", origin, args.get("target", "memory"))
        logger.warning("memory-review 审核失败，fail open 放行", exc_info=True)
        return None  # 任何异常：放行，交给 cleanup 兜底


# ---------------------------------------------------------------------------
# /memory-review 命令：defer 清单管理 + 裁决回执查询
# ---------------------------------------------------------------------------

def _handle_slash(raw_args, **kwargs) -> str:
    # gateway 约定 handler 收整个参数串（str），不是 argv 列表
    argv = raw_args.split() if isinstance(raw_args, str) else list(raw_args or [])
    pdir = _plugin_dir()

    # 裸命令 → 直接给待复核清单 + 子命令指引。
    # 有意不用 hermes_cli.plugin_choices.ask_choice：插件命令的 clarify 在桌面端会落到
    # session_server_requests 的 srq- 请求上，而桌面端提交走 canonicalRedirect → clarify.respond，
    # 两套注册表对不上，卡片会一直挂在「提交中」（详情见 README「已知上游限制」）。
    # 纯文本清单在所有平台（桌面 / 微信 / Telegram）表现一致，也不受会话 busy 影响。
    if not argv:
        return _list_output(verbose=False) + "\n\n" + _USAGE_HINT

    cmd = argv[0].lower()
    if cmd in ("list", "pending", "ls"):
        return _list_output(verbose=True)

    if cmd == "clean":
        items = _pending_items()
        if not items:
            return "pending 目录为空，没有可清扫的提案。"
        removed = []
        for f, it in items:
            try:
                f.unlink()
                removed.append(str(it.get("id", f.stem)))
                _receipt("cleaned", str(it.get("id", f.stem)), "手动清扫 pending", str(it.get("origin", "?")), str(it.get("target", "?")))
            except Exception:
                pass
        return f"已清扫 {len(removed)} 条 pending：{', '.join(removed)}"

    if cmd == "approve":
        if not argv[1:]:
            return "用法: /memory-review approve <序号|id ...>（如 approve 1 3，或 approve all）"
        keys = _resolve_ids(argv[1:])
        if not keys:
            return "没有可批准的提案。用 /memory-review list 查看。"
        done, missing = [], []
        for key in keys:
            f = pdir / f"{key}.json"
            if not f.exists():
                missing.append(key)
                continue
            try:
                item = json.loads(f.read_text(encoding="utf-8"))
                pass_file = pdir / "passes.json"
                passes = json.loads(pass_file.read_text(encoding="utf-8")) if pass_file.exists() else {}
                passes[key] = datetime.now().isoformat(timespec="seconds")
                pass_file.write_text(json.dumps(passes, ensure_ascii=False), encoding="utf-8")
                f.unlink()
                _receipt("human-approve", key, "人工批准 pending 提案", item.get("origin", "?"), item.get("target", "?"))
                done.append(key)
            except Exception as exc:
                missing.append(f"{key}({exc})")
        msg = (f"已批准 {len(done)} 条：{', '.join(done)}。通行证已发——"
               f"让 agent 重新发起这些记忆写入，同样的 operations 会免审落盘。") if done else "没有批准任何提案。"
        if missing:
            msg += f"\n未处理：{', '.join(missing)}"
        return msg

    if cmd == "reject":
        if not argv[1:]:
            return "用法: /memory-review reject <序号|id ...>（如 reject 1 3，或 reject all）"
        keys = _resolve_ids(argv[1:])
        if not keys:
            return "没有可丢弃的提案。"
        done, missing = [], []
        for key in keys:
            f = pdir / f"{key}.json"
            if not f.exists():
                missing.append(key)
                continue
            try:
                item = json.loads(f.read_text(encoding="utf-8"))
                f.unlink()
                _receipt("human-reject", key, "人工丢弃 pending 提案", item.get("origin", "?"), item.get("target", "?"))
                done.append(key)
            except Exception as exc:
                missing.append(f"{key}({exc})")
        msg = f"已丢弃 {len(done)} 条：{', '.join(done)}。" if done else "没有丢弃任何提案。"
        if missing:
            msg += f"\n未处理：{', '.join(missing)}"
        return msg

    if cmd == "stats":
        rec = pdir / "receipts.jsonl"
        counts: dict[str, int] = {}
        total = 0
        if rec.exists():
            for line in rec.read_text(encoding="utf-8").splitlines():
                try:
                    v = json.loads(line).get("verdict", "?")
                    counts[v] = counts.get(v, 0) + 1
                    total += 1
                except Exception:
                    pass
        if not total:
            return "还没有裁决记录。"
        return f"累计裁决 {total} 次：" + "，".join(f"{k}={v}" for k, v in sorted(counts.items()))

    if cmd == "recent":
        rec = pdir / "receipts.jsonl"
        if not rec.exists():
            return "还没有裁决记录。"
        rows = []
        for line in reversed(rec.read_text(encoding="utf-8").splitlines()[-10:]):
            try:
                r = json.loads(line)
                rows.append(f"{r['ts'][5:16]} [{r['verdict']}] {str(r['origin'])[:14]} {str(r['reason'])[:60]}")
            except Exception:
                continue
        return "最近裁决（新→旧，最多 10 条）：\n" + "\n".join(rows) if rows else "还没有裁决记录。"

    return _slash_help()


_USAGE_HINT = (
    "裁决：approve <序号|id> 放行 / reject <序号|id> 丢弃\n"
    "其他：list 详细清单 · stats 统计 · recent 最近 10 条 · clean 清空 pending\n"
    "序号可连写：approve 1 3 5"
)


def _list_output(verbose: bool = True) -> str:
    items = _pending_items()
    if not items:
        return "pending 目录为空，没有等待人工复核的提案。"
    rows = []
    index = {}
    for i, (f, it) in enumerate(sorted(items, key=lambda x: str(x[1].get("ts", ""))), start=1):
        pid = str(it.get("id", f.stem))
        index[str(i)] = pid
        try:
            ops = it.get("args", {}).get("operations", [])
            first = next((str(o.get("content", o.get("old_text", "")))[:60] for o in ops if isinstance(o, dict)), "?")
            ts = str(it.get("ts", ""))[5:16].replace("T", " ")
            if verbose:
                rows.append(f"{i}. {pid}  {ts}  {str(it.get('origin', ''))[:16]}  {first}…\n"
                            f"     理由: {it.get('reason', '')}")
            else:
                rows.append(f"{i}. {pid}  {first}")
        except Exception:
            rows.append(f"{i}. {pid}  （提案文件解析失败）")
    # 序号 → id 的映射交给下一次调用复用（跨进程无状态，写进 remind 旁边的固定文件）
    try:
        (_plugin_dir() / "index.json").write_text(
            json.dumps({"map": index, "ts": datetime.now().isoformat(timespec="seconds")},
                       ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    head = f"待复核 {len(rows)} 项：" if verbose else f"待复核 {len(rows)} 项（用 list 看详细理由）："
    return head + "\n" + "\n".join(rows)


def _resolve_ids(tokens: list) -> list:
    """把 '1'/'3' 这类型号解析成 pending id；'all' = 全部；也接受直接给的 id 或 id 前缀。"""
    items = _pending_items()
    ordered = [str(it.get("id", f.stem)) for f, it in
               sorted(items, key=lambda x: str(x[1].get("ts", "")))]
    out = []
    for tok in tokens:
        t = tok.strip()
        if not t:
            continue
        if t.lower() == "all":
            out.extend(ordered)
        elif t.isdigit() and 1 <= int(t) <= len(ordered):
            out.append(ordered[int(t) - 1])
        else:  # 直接给 id / 前缀
            hits = [pid for pid in ordered if pid.startswith(t)]
            out.extend(hits if hits else [t])
    seen, uniq = set(), []
    for pid in out:
        if pid not in seen:
            seen.add(pid)
            uniq.append(pid)
    return uniq


def _slash_help() -> str:
    return ("用法: /memory-review [list|approve <序号|id>|reject <序号|id>|clean|stats|recent]\n"
            "  list    待人工复核的 defer 提案（带序号与审核理由）\n"
            "  approve 放行提案并发通行证（agent 重发即落盘）；可批量：approve 1 3 / approve all\n"
            "  reject  丢弃提案；可批量：reject 1 3 / reject all\n"
            "  clean   清空全部 pending（记 cleaned 回执）\n"
            "  stats   累计裁决统计\n"
            "  recent  最近 10 条裁决")


def _on_transform_tool_result(tool_name: str = "", result: Any = None, status: str = "",
                              **kwargs: Any) -> Optional[str]:
    """搭车通道：前台 memory() 调用结束时，若积压了后台 fork 的 reject/defer 回执，
    在工具结果尾部追加一行提示（pre_tool_call 纯放行没有传话渠道，只能在这里带字）。"""
    if tool_name != "memory" or not isinstance(result, str) or status not in ("", "ok", "success"):
        return None
    note = _unread_background_notes()
    return result + note if note else None


def _on_pre_llm_call(**kwargs: Any):
    """每轮注入：pending > 0 且过冷却时，往用户消息尾带一行待复核提醒。

    返回 {"context": ...} = 注入；None = 不注入。任何异常静默吞掉（提醒失败不该影响对话）。"""
    try:
        note = _pending_notice()
        return {"context": note} if note else None
    except Exception:
        return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_command("memory-review", handler=_handle_slash, args_hint="[pending|approve|reject|clean|stats|recent]",
                         argument_mode="options",
                         description="记忆审核 defer 提案管理：pending/approve/reject/clean/stats/recent")
