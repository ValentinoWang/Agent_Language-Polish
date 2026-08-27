# Agent_Language-Polish · StyleOS 文风编译器

面向自媒体脚本、科研论文、商业计划书的**非训练式风格系统**：语料蒸馏成 StyleCard，事实与风格双库隔离，按指定风格创作/改写，全程去AI味且事实零改动。

**核心约定：每个写作模块最后都收口成一个即插即用 Pack**——同一份源（StyleCard + 负面规则卡 + 领域包）编译出 Prompt 模板（v0，已交付）、Claude Code Skill + CLI（v0.1）、MCP 工具（v0.2）三种形态。

## 现在就能用

复制即用，零依赖，任何模型对话框都行：

| 场景 | 模板 |
| --- | --- |
| AI 味稿子改人味（事实不动） | [`packs/global/prompt.deai_rewrite.zh.md`](packs/global/prompt.deai_rewrite.zh.md) |
| 博主语料 → StyleCard 蒸馏 | [`packs/distill/prompt.style_distill.zh.md`](packs/distill/prompt.style_distill.zh.md) |
| 指定风格创作/改写 | [`packs/imitate/prompt.style_imitate.zh.md`](packs/imitate/prompt.style_imitate.zh.md) |
| 选题 → 可开拍口播脚本 | [`packs/self_media/prompt.script_writing.zh.md`](packs/self_media/prompt.script_writing.zh.md) |

串联：`distill` 蒸卡（人工批准）→ `imitate` / `self_media` 带卡写作。

## 文档导航

- [`docs/00_方案总览.md`](docs/00_方案总览.md) —— **从这里读**：交付形态决策、Pack 契约、各模块交付规范、路线图
- [`docs/01_StyleOS_原始方案.md`](docs/01_StyleOS_原始方案.md) —— 原始完整方案归档（架构/四类记忆/蒸馏流程/评测体系）
- [`docs/02_openclaw_media_复用清单.md`](docs/02_openclaw_media_复用清单.md) —— 已有代码盘点与复用策略
- [`schemas/`](schemas/) —— StyleCard / 内容账本 / Pack manifest 三个契约
- [`packs/README.md`](packs/README.md) —— Pack 使用入口与修改规矩

## 三条铁律

1. **事实从事实库取，文风从风格库取**——范例只学形，不学实。
2. **去AI味负面规则只有一个事实源**：[`packs/global/deai.negative.zh.yaml`](packs/global/deai.negative.zh.yaml)，条件式规则，不是禁词表，不以 AI 检测器为目标。
3. **改源不改产物**：所有交付形态由源编译而来，禁止在下游形态上单独打补丁。
