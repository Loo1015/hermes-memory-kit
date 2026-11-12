# Changelog

## Unreleased

- `plugins/memory-review` **0.4.0 → 0.6.1**（三连迭代，均过离线回归 M01–M12 + S01–S22）：
  - **0.5.0 — 原因**：MEMORY.md 被系统环境资料淤积（23 条里 21 条是运维手册/历史故障/项目状态），旧 `_RULES` 还写着「环境事实进 MEMORY.md」，与末尾的例外条款自相矛盾，审核闸实际在放行淤积。**内容**：`_RULES` 重写为「系统环境记忆从严」并声明为唯一实时政策源（README 只概述、不再维护第二份规则副本）；固定判定顺序 = 增删改效果 → 作用域归属 → MEMORY 全局例外 → 重复与写法；MEMORY 唯一例外须同时满足「正常查阅前会犯具体严重错误 + 跨任务 + 无及时交付的专门归宿」，「实测过/坑大/难重建」不再构成常驻资格。另修复 defer 分支 `_purge_superseded` 会删掉刚保存提案自身的控制流 bug（隔离沙盒复现：saved=True → purged_count=1 → 文件消失；修法为 defer 落点排除当前 key）。
  - **0.6.0 — 原因**：reject 会真丢内容——后台 fork 的提案被拒后无人负责把「该进技能/项目 AGENTS.md」的部分送过去，而这类内容恰恰有保存价值。**内容**：裁决分类改为 **defer = 有价值但错位**（pending 兼作人工路由收件箱），**reject = 任何层都不该存**（重复/临时状态/可重建裸值/过期/空指针/纯写法问题）；target 错层从 reject 改判 defer；混合批按主要内容裁决。双语 README 裁决表同步。
  - **0.6.1 — 原因**：真实审核模型（deepseek-v4.1-flash）对 22 个合成 fixture 的语义抽样暴露 5 个系统性落点偏移（说了「应归项目记录」仍 reject、错层仍 approve、把 remove 去重条款套到 add、低频当减分项、混合批落点错）和 1 个截断放行 bug（reason 超长被 max_tokens=200 截断 → JSON 解析失败 → 生产 fail-open 放行坏写入）。**内容**：`_RULES` 新增「5b 落点自检」六条（decision 必须与 reason 一致）；「approve 去重」显式限定仅 remove；「target 错层不属写法问题」；reason 限 50 字；`_call_reviewer` 对截断 JSON 按正则抢救 decision（只认三枚举，抢救不出才 fail open）。复测确认系统性失配全部消除；剩余为小模型运行间方差（同 prompt、temperature=0 仍漂移），如实写入 README 已知边界，方差对策（三投多数决/更强模型/机械前置检查）留档未内置。
- `plugins/memory-review` **0.6.2**：公开代码去掉作者宿主的兜底默认路径，`HERMES_HOME` 未设置时回落标准的 `~/.hermes`（设置时行为不变）；`skills/memory-write-discipline` 文档中的宿主路径同步改为 `$HERMES_HOME` 写法。
- `skills/memory-write-discipline` **1.1.0 → 1.2.0**：MEMORY.md 例外入口新增「系统环境记忆从严解释」清单（环境配置/路径/启动链/故障史/性能测量/项目状态默认归按需资料；只收事前保护；低频不减分、高频不准入；指针不自动准入），与插件 `_RULES` 口径一致。
- README（中英）：闸的三态描述更新为路由收件箱语义（defer ≠ 拿不准的垃圾站，reject ≠ 丢弃该进其他体系的内容）；已知边界补截断抢救与小模型方差两条。

## Unreleased (2026-11-10/11)

- 仓库更名 `hermes-memory-skills` → `hermes-memory-kit`：memory-review 插件加入后，内容不再只是技能。旧名自动重定向。
- 新增 `plugins/memory-review`：针对 `memory()` 写入的 LLM 审核闸（approve / reject 附理由 / defer 转人工），fail open，复用 Hermes 已配置模型，零新增凭据。含双语插件 README。
- 仓库级 README 中英双语重写为「工具集」定位：三层结构（闸/纪律/瘦身）+ 两种维护策略 + 安装指引；插件级细节移入 `plugins/memory-review/README*.md` 并互链。
- README（中英）：新增「discipline 的作用范围」一节——明确 discipline 只规定写入规则，Hermes 的写入不受它强制控制（会话内顺手写基本不经过它，后台提案完全不经它）；定位是写入质量参考，不是写入闸门。
- README（中英）：新增「MEMORY 的两种维护方式」——路线 A（任写 + cleanup 事后筛 + 80% 黄线硬触发）与路线 B（`memory.write_approval` 全量审核）的取舍；作者采用 A。
- README（中英）：已知坑补 3 条实测项——凭会话冻结快照写 `patch` `old_text` 会失败（附原子回滚实例）、黄线提醒只在 `memory()` 写入后检查（后台写入绕过检查点）、`old_text` 须与磁盘条目逐字一致（事实可能混在别的条目里）。
- README（中英）：闸线一节改为「知道技能不会自己生效」——删掉往 SOUL.md 塞一行提醒的建议（那只是又一条每轮付费、同样不保证执行的文字），真正的机制保证只有源码钩子或 `memory.write_approval`。
- 仓库更名 `hermes-memory-plus` → `hermes-memory-skills`：原名易被误认为插件或项目，实为技能集合。旧名保留重定向。
- README 拆为中英双语：`README.md`（英文，主页）+ `README.zh-CN.md`（中文），互相链接。
- `LICENSE` 恢复为纯 MIT 正文，GitHub 许可证探测可正确识别为 MIT；第三方署名统一移入 `THIRD-PARTY.md`。

## 1.1.0

- `memory-write-discipline`: 新增 §0.5「写后容量提醒」——写入后按 80% / 95% 两档决定是否提醒、是否必须先腾空间。
- `memory-write-discipline`: §0 明确计数口径为字符而非字节，并指出中文文件字节数会虚高约 3 倍，应以 `memory()` 回报的 `current/limit` 为准。
- `memory-write-discipline`: §4 改为「日期标签默认不加」，给出三项代价（破坏 `patch` 寻址 / 制造精确去重挡不住的重复 / 长期占预算）与决定性理由（日期一旦存在易被下游当作淘汰闸门，而老约束不能按年龄淘汰）。
- `memory-cleanup`: 来源标记移入 frontmatter（`upstream` 字段）；三处本地适配改动详见 `THIRD-PARTY.md`。

## 1.0.0

- 首版：`memory-write-discipline`（原创）+ `memory-cleanup` v0.1.2（fork）。
