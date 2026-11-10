# Changelog

## Unreleased

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
