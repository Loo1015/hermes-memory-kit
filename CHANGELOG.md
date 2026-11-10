# Changelog

## Unreleased

- README（中英）：新增「discipline 的作用范围」一节——明确 discipline 只规定写入规则，Hermes 的写入不受它强制控制（会话内顺手写基本不经过它，后台提案完全不经它）；定位是写入质量参考，不是写入闸门。
- README（中英）：新增「MEMORY 的两种维护方式」——路线 A（任写 + cleanup 事后筛 + 80% 黄线硬触发）与路线 B（`memory.write_approval` 全量审核）的取舍；作者采用 A。
- README（中英）：已知坑补 3 条实测项——凭会话冻结快照写 `patch` `old_text` 会失败（附原子回滚实例）、黄线提醒只在 `memory()` 写入后检查（后台写入绕过检查点）、`old_text` 须与磁盘条目逐字一致（事实可能混在别的条目里）。
- README（中英）：闸线说明从「SOUL.md 或全局 AGENTS.md」改为仅 `SOUL.md`，并标注只是提高概率、非机制保证。
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
