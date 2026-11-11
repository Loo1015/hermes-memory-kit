# Hermes Memory Kit

**中文** · [English](README.md)

让 [Hermes Agent](https://hermes-agent.nousresearch.com/docs) 的长期记忆保持**小而诚实**的工具集：一道写入闸、一套瘦身流程、以及判断事实归属的纪律。

> 这是一个**记忆工具集**——一个插件加两个技能。不碰 Hermes 内部机制，也不内置自动清理：上游 Hermes 把记忆溢出当作预期行为，不是 bug。

---

## 为什么有这个

Hermes 每轮都把 `MEMORY.md` 和 `USER.md` 注入系统提示词。三个后果，默认行为都不处理：

1. **写进去的东西永远付费。**「阶段 3 完成」和「试了 8080 端口，通了」会在之后的每条消息里占用预算，直到年底。
2. **没有任何东西判断事实是否属于这里。**一次性的调试细节和机器级硬约束，写进去之后长得一模一样。
3. **满了就是满了。**没有自动压缩。写入开始失败时你才发现，而且是在任务中间。

记忆质量不是容量问题，是**路由**问题。这个工具集在三层上解决它：

| 层 | 工具 | 何时生效 |
|---|---|---|
| **闸** | `plugins/memory-review`——每次 `memory()` 写入的 LLM 审核 | 写入落盘前 |
| **纪律** | `skills/memory-write-discipline`——供 agent 自行判断的价值/归属/加载门槛 | 写入时（概率性） |
| **瘦身** | `skills/memory-cleanup`——盘点 → 迁移方案 → 批准后应用 | 记忆已经膨胀后 |

三者互相衔接：纪律减少需要过闸的量，闸拦掉纪律漏掉的大多数，cleanup 收回两者都漏掉的预算。单靠任何一个都不等于「记忆干净了」。

---

## 内容

### `plugins/memory-review`——闸

针对 `memory()` 写入的 LLM 审核闸。每次写入连同磁盘上的 MEMORY.md/USER.md 快照和浓缩规则表发给审核模型（复用 Hermes 已配置的模型），三态裁决：放行 / 附理由拒绝 / 转人工。

- **零新增凭据**：审核模型从 `model_aliases` / `providers` 解析；key 只进内存不落盘。
- **fail open 是设计选择**——它是质量过滤器，不是安全边界。配置与细节：[`plugins/memory-review/README.zh-CN.md`](plugins/memory-review/README.zh-CN.md)（[English](plugins/memory-review/README.md)）。
- **限制如实写明**：桌面端插件命令的交互菜单不可用（纯文本输出）；后台 fork 的拦截靠搭车回执播报；改写重提自动作废旧提案。

### `skills/memory-write-discipline`——纪律（原创）

即使不安装也有四段值得读：

- **§1 三道闸。**价值 / 归属 / 加载。最关键的一条：*不许用后面的闸否决前面的闸*——「不值得每轮付费」不能否决一个本来就属于作用域文件的事实。
- **§3 四个问题。**价值、可推导性、重复、成本。负面清单（PR 号、SHA、临时路径、任务进度）是这四问的实例，不是独立规则。
- **§4 写法。**陈述句，不用祈使句。`User prefers concise replies` ✓ / `Always respond concisely` ✗——祈使句会被重读为活指令，覆盖用户当下真正的要求。
- **§5 工具机制。**`patch` 替换的是*一段文字*，不是整条。只传开头一句，旧尾巴还在——文件变大，调用照样返回成功。

还包括**日期标签**策略及默认不加的理由：时间戳是一个信号，但破坏 `patch` 寻址、制造精确去重挡不住的重复，而且决定性的一点——诱导下游代码把**年龄当作过期依据**，对随时间越老越值钱的硬约束来说恰好相反。

### `skills/memory-cleanup`——瘦身（fork）

TechNickAI 的 `memory-cleanup` v0.1.2 的 MIT fork。核心原则值得原样引用：*"This is not a deletion pass. It is a routing pass."*

作为**冻结 fork 维护，不跟上游**——上游已不再提供此文件。三处本地适配见 [`THIRD-PARTY.md`](THIRD-PARTY.md)，未删任何原始规则。

---

## MEMORY 的两种维护策略

技能层无法机械强制，策展需要策略：

**策略 A：自由写入 + 闸 + 事后清理（作者采用）**

- 让 `memory()` 自由写；审核闸（插件）+ 纪律（技能，概率性）提升质量
- 80% 黄线是**硬触发**：工具回报 `current/limit` ≥ 80% 时，agent 当轮必须加一行提醒并建议 cleanup dry-run
- 代价是「窗口污染」：两次 cleanup 之间，坏条目持续占用每轮提示词预算。写入率低、水位低时，这个代价很小

**策略 B：逐条审批（`memory.write_approval: true`）**

- 机械强制：所有 memory/skills 写入进待审目录等人工
- 代价：审核被推迟到你**已经没有当初写入上下文**的时刻——隔天批量批准做出最差的判断；定时/后台任务的写入持续堆积

**一句话取舍**：B 的问题不在审核本身，在审核时机。写入率低就选 A，把黄线当闸。纪律无论选哪个都留着。

---

## 安装

**1. 插件**——把 `plugins/memory-review/` 复制进 Hermes 插件目录，然后在 `config.yaml`：

```yaml
plugins:
  enabled:
    - memory-review

memory_review:
  alias: <model_aliases 里一个便宜快的模型>
  timeout_s: 30
  defer_blocks: true
```

完整配置和日常命令：[`plugins/memory-review/README.zh-CN.md`](plugins/memory-review/README.zh-CN.md)。

**2. 技能**

```bash
git clone https://github.com/Loo1015/hermes-memory-kit.git
cp -r hermes-memory-kit/skills/memory-write-discipline <SKILLS_DIR>/
cp -r hermes-memory-kit/skills/memory-cleanup           <SKILLS_DIR>/
```

`<SKILLS_DIR>` 来自 `hermes config get skills_dir`（通常 `~/.hermes/skills/`）。**不要照抄任何人的绝对路径，包括作者的。**

验证：

```bash
hermes skills list | grep memory
```

两行都应显示 `enabled`。

**3. 分清什么被强制、什么没有**

- **插件是机械的**：每次 `memory()` 调用都被代码拦截，无一例外。
- **技能不是确定性通道**：模型按 description 自行决定是否加载；装好后它们仍只是磁盘上的文档。不要往 SOUL.md 塞提醒来掩盖这一点——那只是又一条每轮付费的文字，同样没有保证。

**4. 可选首跑**——会话内对 agent 说：

> 对我的 MEMORY.md 和 USER.md 跑一次 memory-cleanup dry-run，产出审核材料，先别改任何东西。

---

## 阈值

按比例设计，跟随你的配置而不是写死数字：

| 占用 | 行为 |
|---|---|
| < 80% | 无 |
| ≥ 80%（黄） | 回复末尾加一行：哪层、字符数、百分比、建议 |
| ≥ 95%（红） | 警告 + 下次写入前**必须**在同一原子批次里腾出等量空间 |

这些是**本项目自定的运行阈值，不是平台行为**。Hermes 只在 100% 硬拒（且检查整个批次的最终状态）。80/95 存在的理由：要在还有余量思考时开始压缩，而不是在被拒时。

---

## 已知的坑

全部实测，非推测：

1. **`memory()` 只有 `add` / `patch` / `remove`，没有 `replace`。**调 `replace` 报错并指向 `patch`。
2. **`patch` 替换一段。**`old_text` 只传部分 → 旧尾巴保留，条目变长，照样返回成功。重写一条需要**完整条目**做 `old_text`。
3. **只有精确去重，没有语义去重。**近重复要自己先查。
4. **写入立即落盘，但下一轮才进系统提示词。**记忆是冻结快照，本回合读不回自己写的东西。
5. **按字符计，不按字节。**中文为主的记忆文件字节数虚高约 3 倍。用工具回报的 `current/limit`，别用 `os.path.getsize`。
6. **不要基于后台提案批量改记忆。**没有 shell 的 fork 能写不能验；实测有自动生成的记忆改动损坏内容。留人工在环上。
7. **指针不等于送达。**「存在 Hindsight 里了」只证明内容可存可查，不证明 prefetch 会在需要时召回它。
8. **凭会话内快照写 `patch` 的 `old_text` 会失败。**patch 前永远读磁盘文件。（实测：一个 3 操作原子批次因此整体回滚。）
9. **黄线检查只在 `memory()` 写入后触发。**后台 fork 写入完全绕过检查点。要主动检查，跑 `hermes memory status`。
10. **`patch` 的 `old_text` 必须与磁盘条目逐字一致。**要改的事实可能混在另一条里——凭印象写 `old_text` 通常就是匹配失败。

---

## 什么时候不用它

- 你希望记忆自由增长、偏好检索而非策展——用 memory provider（Hindsight、Mem0……），跳过本工具集。
- 一次性 profile，或记忆文件又小又新。
- 期待自动化。闸跟着写入走；没有任何东西自己清理记忆——cleanup 是主动调用的。

---

## 文件结构

```
plugins/
  memory-review/                      写入闸（插件 + 斜杠命令）
    __init__.py · plugin.yaml
    README.md · README.zh-CN.md
skills/
  memory-write-discipline/SKILL.md    原创，MIT
  memory-cleanup/SKILL.md             TechNickAI v0.1.2 的 fork，MIT
README.md · README.zh-CN.md           本文件（英文）+ 中文说明
THIRD-PARTY.md                        署名 + 本地改动
CHANGELOG.md · LICENSE
```

---

## 历史

最初叫 `hermes-memory-plus`（一个技能对），改名 `hermes-memory-skills`，审核闸插件加入后更名 `hermes-memory-kit`——内容不再只是技能。旧名在 GitHub 上自动重定向。
