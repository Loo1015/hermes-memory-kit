# 第三方组件署名

## memory-cleanup

- **来源**：TechNickAI/hermes-skills
  `https://github.com/TechNickAI/hermes-skills`
- **原始路径**：`skills/productivity/memory-cleanup/SKILL.md`
- **原始版本**：`0.1.2`
- **许可**：MIT
- **状态**：**冻结 fork，不追上游**

### 关于版本指纹的如实说明

无法提供准确的上游 commit SHA。核实结果：

- 查 `skills/productivity/memory-cleanup/SKILL.md` 的历史 commit，返回 **0 条**。
- 查上游 `main` 分支完整文件树（154 项，HEAD `ffb1586`，2026-11-09），**已无 `memory-cleanup` 任何文件**。

即：该技能要么已从上游移除，要么曾以不同路径存在。本仓库保留它的原因是它本身有用，而不是与上游保持同步。本文件不编造 commit 指纹。

如果你知道准确出处，请提 issue 补充。

### 本 fork 的改动（3 处，均在 `SKILL.md` 内）

| 行 | 改动 | 原因 |
|---|---|---|
| 16 | `related_skills` 由 `[recall, multi-review]` 改为 `[]` 并加注 | 上游依赖的两个技能在目标环境未安装；留空避免加载时悬空引用 |
| 309 | 第 6 步由「调用 multi-review」改为「交用户逐项确认」 | 同上；保留人工审批闸门，只是换成不依赖外部技能的方式 |
| 424 | 验收清单同步改为「用户已逐项确认」 | 步骤 6 改动的连带修正 |

除上述三处，其余内容与原版一致。**没有删除任何原始条款**，包括「This is not a deletion pass」这一核心原则。

### 上游改动不会被自动继承

MIT 许可不要求跟随上游维护，本 fork 也不打算追。代价是：上游的 bug 修复不会自动到达这里。如果你要对照上游，按上面的仓库地址自行比对——本仓库不承诺同步。

## memory-write-discipline

**非第三方**。为本仓库原创（MIT），不是任何现有技能的衍生。

设计上参考了以下公开资料，但未复制其文本：

- Hermes Agent 官方文档（Persistent Memory / Working with Skills / Skill Authoring）
- Marchy02/hermes-memory-suite 的 `memory-discipline` 决策树（每轮都要的进 MEMORY、项目细节进 FACT_STORE、3+ 步流程转 SKILL、临时进度不存）
- alone-tree/hermes-skills 的 `memory-management` 五层模型（SOUL / USER / MEMORY / skills / AGENTS）与 DO NOT Save 负面清单

观点上的区别：本技能不采用「按年龄淘汰」（7-Day Test 一类），理由见 SKILL.md §4。

---

两份 `SKILL.md` 均为 MIT。原版权声明与许可条款保留，见根目录 `LICENSE`。
