# memory-review

Hermes 插件：为 `memory()` 写入装一道 **LLM 审核闸**。每次写入，把提案全文 + 磁盘上
MEMORY.md/USER.md 的当前内容 + 浓缩版规则表发给一个已经配置在 Hermes 里的审核模型，
返回三态裁决：

| 裁决 | 行为 |
|---|---|
| `approve` | 放行 |
| `reject` | 拦截，理由回给模型（模型可见，可改写后重试） |
| `defer` | 默认拦截并转人工复核（`defer_blocks: false` 改为放行） |

> **这是质量过滤器，不是安全边界。** 它是 fail open 的：审核模型超时、连不上、
> 返回解析不了，写入照常放行。它的价值在于拦掉大多数坏写入，不是保证任何东西。

English: [README.md](README.md)

## 拦什么、不拦什么

| 面 | 拦？ | 说明 |
|---|---|---|
| `memory()` 调用，含后台 fork | ✅ | 主要目标。后台 fork 被拦时通过回执机制搭车告知前台（见「兼容性」）。 |
| `skill_manage` | ❌ | 有意不拦：写差技能不占常驻提示词预算，由 memory-cleanup 兜底。 |
| 直接改文件（`write_file` / `patch` 改 MEMORY.md） | ❌ | 合规的人工通道。插件看不到，也不该看到。 |
| `retain` / `consolidation`（memory provider） | ❌ | provider 侧的风险口径是「污染 recall」，不是「改坏 MEMORY.md」。 |

fail open 的触发条件：审核模型超时、连接失败、响应格式错误、没配模型、或
`enabled: false`。插件永不 raise —— 在 `pre_tool_call` 里 raise 等于 fail closed。

## 怎么判

每次调用把完整的 operations、当前 MEMORY.md/USER.md 快照、以及六条浓缩规则发给审核模型：

1. **保留价值** —— 一次性调试细节、PR 号、SHA、临时路径、任务进度 → reject。
2. **可推导性** —— 能从权威来源低成本重建的裸事实 → reject（重建会丢决策理由的除外）。
3. **重复** —— 与现有条目等价 → reject；新增细节 → 给合并建议；事实已变 → 修订原条目。
4. **成本** —— 会话临时状态 → reject。
5. **写法** —— 祈使句（「永远/必须…」）→ reject，要求改陈述句；一条捆多个主题 → reject，要求拆分。
6. **归属** —— 关于用户的进 USER.md，环境事实进 MEMORY.md；放错 target → reject。

审核模型读得到磁盘上的记忆现状，所以能判重复、能判预算。判不准时它 defer 而不是猜。
同一 origin 的改写重提会自动作废旧的 pending 提案（`old_text` 完全一致或相似度 ≥0.6），
所以「被拒—改写—重提」的循环不会堆积僵尸提案。

## 安装

把插件目录放进 Hermes 插件目录，然后在 `config.yaml` 里：

```yaml
plugins:
  enabled:
    - memory-review

memory_review:
  alias: workbuddy      # 一个 model_aliases 条目；或 provider: <名字> + model: <名字>
  timeout_s: 30
  defer_blocks: true    # false = defer 改为放行而非拦截
  # enabled: false      # 临时停用开关，不用动 plugins.enabled
```

审核模型从 Hermes 自己的配置解析 —— 零新增凭据。key 解析支持字面量、`${VAR}` 引用、
`key_env` 名称三种形式；key 只进内存，绝不写日志、绝不落盘。**建议选便宜快的小模型**：
作者本机用 deepseek-v4.1-flash，实测约 1.7 秒/条。

## 日常使用

交互全部是纯文本 + 序号（没有交互菜单 —— 原因见「兼容性」）。斜杠命令：

| 命令 | 作用 |
|---|---|
| `/memory-review list` | 列出待人工复核的 defer 提案（序号、id、时间、来源、内容摘要、理由） |
| `/memory-review approve <序号\|id>` | 发一次性哈希通行证；agent 重发相同 operations 时免审落盘 |
| `/memory-review reject <序号\|id>` | 丢弃该提案 |
| `/memory-review approve 1 3` / `reject all` | 按序号批量裁决 |
| `/memory-review stats` / `recent` | 累计裁决统计 / 最近 10 条回执 |
| `/memory-review clean` | 清空待复核队列 |

approve **不会直接改 MEMORY.md**：插件只发哈希通行证，落盘仍走 `memory()` 原路
（保留原子 batch、去重、用量统计）。通行证一次性，用完即焚。

## 兼容性

- **桌面端（apps/desktop）：插件命令里的交互菜单不可用。** 插件有意只输出纯文本，
  把交互交给宿主（GUI 面板或消息平台按钮）。根因在上游（插件命令里的 `ask_choice`
  在桌面端会挂住 120 秒，会话 busy 时直接返回 `None`），修它需要改 Hermes 源码，
  不是插件能解决的。
- **审核发生在参数校验之前。** 连畸形的 payload 也会过审 —— 这是有意的：
  审核给出的 reject 理由模型看得到，可以据此修正 payload。
- **后台 fork 的回执靠搭车播报。** 后台 fork 被拦时，block message 只活在它自己的会话里，
  前台看不到。插件因此搭车在前台下一次成功的 `memory()` 结果上（`transform_tool_result`），
  追加一行「N 条未读审核回执」。前台调用报错时不消费回执游标；纯放行的调用没有传话渠道。
- **提醒走每轮注入**，不改系统前缀：`pre_llm_call` 加一行「N 条待复核」，默认 30 分钟冷却
  （`remind_cooldown_s` 可调），条数变化立即再提醒。这样提示词前缀缓存不受影响。

## 配套使用

- [memory-cleanup](https://github.com/Loo1015/hermes-memory-kit) —— MEMORY.md 的定期瘦身。
  闸和 diet 是互补的：闸拦住垃圾进不来，cleanup 收回已经进来的预算。cleanup 应用阶段直接写文件、
  不走 `memory()`，所以它那批 remove 为主的改动不会被本闸反复重新审视。
- [memory-write-discipline](https://github.com/Loo1015/hermes-memory-kit) —— 在写之前
  先决定事实该归哪里，减少闸需要审的量。

## 已知边界

- fail open 是设计选择，不是缺陷：闸的价值在拦截大多数坏写入，不在 100% 可用。
  漏过去的由 memory-cleanup 兜底。
- 闸判断的是审核模型能看到的东西。事实错误但表述自信的写入可能通过；
  真正有价值但表述别扭的写入可能被 defer。人工回复核队列就是纠偏回路。
