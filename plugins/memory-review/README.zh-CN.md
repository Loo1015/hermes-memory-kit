# memory-review

Hermes 插件：为 `memory()` 写入装一道 **LLM 审核闸**。每次写入，把提案全文 + 磁盘上
MEMORY.md/USER.md 的可见快照 + `_RULES` 政策发给一个已经配置在 Hermes 里的审核模型，
返回三态裁决：

| 裁决 | 行为 |
|---|---|
| `approve` | 放行 |
| `reject` | 拦截并丢弃，理由回给模型（前台或后台 fork 可据此改写重提） |
| `defer` | 默认拦截并转人工路由：有价值但不属常驻层的内容进 pending 收件箱，由人挪到正确位置（`defer_blocks: false` 改为放行） |

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

唯一实时政策源是 [`_RULES`](__init__.py)；本节只概述，不维护另一份规则正文。
每次调用把该政策、完整 operations 和 MEMORY.md/USER.md 可见快照发给审核模型，依次判断：

1. 先看整批 add/patch/remove 的实际增删改效果，包括删除安全。
2. 再按作用域归属：项目资料归项目，稳定跨任务用户偏好归 USER.md。
3. 再过 MEMORY.md 的严格全局例外门；普通系统环境资料归权威配置、项目记录或按需技能。
4. 最后检查重复、声明式和单主题写法。

两态的分界是**内容还有没有保存价值**，不是内容属于哪一层：

- `reject` = 在任何层都不该存：与可见条目重复、临时状态/任务进度/补丁交接、一次性调试细节、
  PR 号/SHA、已过期或被证伪、可从权威来源一行查到的裸值（端口/路径/安装位置）、空指针「详见 X」，
  以及纯写法问题（祈使句、多主题捆绑 —— 按理由改写重提即可，不算丢内容）。
- `defer` = 有保存价值但错位：该进技能、项目 AGENTS.md、项目记录或权威配置文档的；`target`
  放错的（全局偏好写进 MEMORY、单项目规则写成全局）；影响准入或删除安全的关键事实未明。
  落点是 pending，**pending 兼作人工路由收件箱**。
- 整批混合时：含实质性的「值得留」内容 → `defer`（人工路由时丢掉无价值部分）；整批都无处可存 → `reject`。

`reject`/`defer` 都只建议归属，不表示已完成迁移。同一 origin 的改写重提可清理旧 pending（`old_text` 完全一致
或相似度 ≥0.6）；清理会保留本次刚保存的 defer 提案。

## 安装

插件代码只在 gateway 启动时加载；磁盘改动在下次重启后生效，不会热更新已运行的网关。

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
| `/memory-review list` | 列出 defer 收件箱（序号、id、时间、来源、内容摘要、理由；理由里带建议归属） |
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
- **审核输出被 max_tokens 截断时不再直接 fail open**（v0.6.1）：JSON 不完整但 decision
  可辨认时，按正则抢救 decision（只认 approve/reject/defer 三个枚举值），抢救不出才放行。
- **小模型审核员存在运行间方差**：temperature=0 不保证同 prompt 同裁决，边界样本
  （错层 target、自述例外）实测会在 approve/defer/reject 间抖动。规则文本只能压系统性偏差，
  压不掉随机性；方差对策（更强审核模型 / 三投多数决）见仓库 issue 讨论，未内置。
- **pending 兼作路由收件箱**：`defer` 会把「有价值但错位」的内容攒在 `pending/memory-review/`，
  需要定期 `/memory-review list` 清理（路由完后 `reject <id>` 关单）。队列不落 MEMORY.md，不占常驻预算；
  同一内容同哈希不会重复堆积（同一 id 覆盖写），改写重提会清掉相似旧提案。
- 审核模型只看到政策、operations，以及每份磁盘记忆文件的前 6,000 字符；看不到外部技能/
  项目正文或迁移证明。提案声称「技能 X 已覆盖」不等于已核实。模型判断可能出错，人工复核
  用于纠正准入/删除安全的关键不确定。
- 可解析但未知的 `decision` 目前会落到 `approve` 回执；这是已知的 fail-open 边界，
  不是新增第四种合法裁决。
