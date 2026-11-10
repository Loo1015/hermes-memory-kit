# hermes-memory-plus

Hermes Agent 记忆写入纪律与清理路由。两个技能：一个管**往里写什么**，一个管**存量怎么整理**。

不是「让记忆更多」，是**让记忆不涨**。Hermes 的 `MEMORY.md` / `USER.md` 每轮注入，写进去的每个字都要长期付费；而上游已明确记忆溢出 *not a bug*、不做自动清理。所以这件事只能靠纪律 + 定期手动整理。

## 它解决什么

默认状态下有两个缺口：

1. **写入没规矩**。修完一个 bug 顺手把「阶段 3 完成」写进 MEMORY.md，占了永久的 prompt 预算，三个月后毫无用处。
2. **涨满了没人管**。官方不加自动压缩，MEMORY.md 满了就是满了，后续写入被拒。而你手边没有「什么时候该整理」的信号。

`memory-write-discipline` 补第 1 个，`memory-cleanup` 补第 2 个，中间用容量阈值连起来。

## 安装

**1. 装两个技能**

```bash
git clone https://github.com/<your-name>/hermes-memory-plus.git
cp -r hermes-memory-plus/skills/memory-write-discipline <SKILLS_DIR>/
cp -r hermes-memory-plus/skills/memory-cleanup           <SKILLS_DIR>/
```

`<SKILLS_DIR>` 用 `hermes config get skills_dir` 查，常见是 `~/.hermes/skills/`。**别照抄任何绝对路径**，本仓库里的路径只作占位示意。

确认：

```bash
hermes skills list | grep memory
```

应看到两行 `enabled`。

**2. 核对字符上限**

```bash
hermes config get memory.memory_char_limit   # 默认 6000
hermes config get memory.user_char_limit     # 默认 4000
```

阈值按**比例**算，不写死数字：

| 占用 | 行为 |
|---|---|
| < 80% | 不管 |
| ≥ 80%（黄线） | 写了记忆就在回复末尾加一行提醒：哪一层 / 字符数 / 百分比 / 建议 |
| ≥ 95%（红线） | 提醒 + 下次写入前必须先腾出等量空间，否则不写 |

上限改了，两条线自动跟着走。这两个数字是**本方案自定义的操作阈值，不是平台规格**。系统只在 100% 处硬拦（且检查的是整个 batch 的最终值），80 / 95 是给人留的提前量和缓冲。

**3. 加一行开机指令（不能省）**

技能**不是确定性通道**——模型按 description 自行决定要不要加载，没有任何强制触发机制。所以必须在**每轮注入的层**（`SOUL.md`，或全局 `AGENTS.md`）里放一行：

```markdown
写记忆前后看一眼容量：≥80% 在回复末尾提醒，≥95% 先腾空间再写。
存量整理走 memory-cleanup（dry-run + 用户审批），本机不自动清理。
```

没有这一行，两个 SKILL.md 就只是躺着的说明书。

**4. （可选）首次跑一次 dry-run**

```bash
# 在会话里说：
用 memory-cleanup 对我的 MEMORY.md 和 USER.md 做一次 dry-run，产出核对清单，先别改。
```

它会生成 5 个产物（inventory / relocation-plan / proposed-* / review-checklist），你审完再决定是否 Apply。**Apply 之前不会动 live 文件**，这是技能自己的硬约束。

## 两个技能的边界

| | memory-write-discipline | memory-cleanup |
|---|---|---|
| 时机 | 每次写之前 | 存量该整理了 |
| 动作 | 判断「存不存 / 归哪层 / 怎么写」 | 路由 + 压缩，**不是删除** |
| 默认 | 直接给结论 | dry-run，等你审批 |
| 作用 | 防涨 | 降存量 |

`memory-cleanup` 的核心是**路由**（routing pass, not a deletion pass）：每条事实移到最小的正确归宿——用户事实 → USER.md，人设规则 → SOUL.md，项目规则 → 项目 AGENTS.md，流程 → 技能，长尾事实 → provider。删只发生在确实陈旧或重复的情况下。

## 已知坑

**① `memory()` 只有 `add` / `patch` / `remove`，没有 `replace`。**
调 `replace` 会报错并提示改用 `patch`。

**② `patch` 替换的是 span，不是整条。**
只传开头一句当 `old_text`，旧尾巴会留在后面，越改越长，而且返回 success。重写整条必须把完整条目作为 `old_text`。

**③ 只有精确去重，没有语义去重。**
`Voce Rick speed 1.55` 和 `voce rick velocità 1.55` 算两条。技能里 §3 第 ③ 问要求写入前主动检索相似条目，不能指望工具拦。

**④ 写入立刻落盘，但下个会话才进 system prompt。**
记忆是冻结快照，当轮看不到自己刚写的东西。

**⑤ 日期标签默认不加。**
不是审美。日期一旦存在，下游就容易拿它当淘汰判据（「超 N 天 → 陈旧 → 删」），而一堆**又老又硬**的约束（系统级损坏、绕行路径、禁改配置）越老越不能删。另外它会破坏 `patch` 寻址、制造精确去重挡不住的重复、占永久预算。真要记时效就写在句末并写死。

**⑥ 中文按字符计，不按字节。**
`D:\...\MEMORY.md` 的字节数会虚高约 3 倍（中文 1 字 = 3 字节）。用 `memory()` 回报的 `current/limit`，别用 `os.path.getsize`。

**⑦ 别用自动提案批量改记忆。**
本方案基于实测：后台 fork 自动生成的记忆提案会写坏内容，且它只能写、不能验证（无 shell）。所有清理必须人在环。

## 目录

```
skills/
  memory-write-discipline/SKILL.md   # 原创，MIT
  memory-cleanup/SKILL.md            # fork，MIT，署名见 THIRD-PARTY.md
LICENSE
THIRD-PARTY.md
```

## 许可

MIT。细则见 `LICENSE` 与 `THIRD-PARTY.md`。
