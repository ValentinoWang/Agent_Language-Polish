# Packs —— 即插即用交付物目录

**本项目的硬性约定：每个写作模块开发到最后，必须收口成这里的一个 Pack。没有 Pack，模块就不算完成。**
Pack 的字段契约见 [`schemas/pack_manifest.schema.yaml`](../schemas/pack_manifest.schema.yaml)，交付形态决策的完整论证见 [`docs/00_方案总览.md`](../docs/00_方案总览.md)。

## 现在就能用的（status: usable）

| Pack | 干什么 | 打开这个文件复制 |
| --- | --- | --- |
| `global.deai` | 把 AI 味草稿改成人味，事实零改动 | [`global/prompt.deai_rewrite.zh.md`](global/prompt.deai_rewrite.zh.md) |
| `distill` | 把博主 3–10 篇语料蒸馏成 StyleCard | [`distill/prompt.style_distill.zh.md`](distill/prompt.style_distill.zh.md) |
| `imitate` | 以指定风格创作/改写（含无卡降级用法） | [`imitate/prompt.style_imitate.zh.md`](imitate/prompt.style_imitate.zh.md) |
| `self_media` | 选题+信息点 → 可开拍口播脚本 | [`self_media/prompt.script_writing.zh.md`](self_media/prompt.script_writing.zh.md) |

**典型串联用法**：`distill` 蒸出某博主的 StyleCard（人工批准）→ 写脚本走 `self_media`（人设槽贴卡）或通用创作走 `imitate` → 手头已有 AI 味稿子且不需要贴人，直接 `global.deai`。

## 规划中的（status: planned）

| Pack | 范围 | 上线版本 |
| --- | --- | --- |
| `academic` | 论文分章节润色、审稿回复、中英互译防翻译腔 | v0.1 |
| `business` | BP/路演稿/口播三态分治、陈述定级只降不升 | v0.1 |

## 公共规则

- [`global/deai.negative.zh.yaml`](global/deai.negative.zh.yaml)：**去AI味负面规则的唯一事实源（SSOT）**，约 20 条条件式规则。所有 Pack 引用它；各赛道在 StyleCard 里用同名 id 覆盖 policy，不许另建第二份清单（教训来自 openclaw-media 审计 CPC-07：两份黑名单各自维护必然漂移）。

## 修改 Pack 的规矩

1. 改的是"源"：负面规则改 `deai.negative.zh.yaml`，风格改 StyleCard，模块流程改该 Pack 的 prompt；**不要**只在某个下游形态（如以后编译出的 SKILL.md）上打补丁。
2. prompt 文本的任何实质变化：升 `pack.yaml` 的 version，记 changelog。
3. 新 Pack 上线（status → usable）之前，对照 `pack.yaml` 的 `dod` 清单逐项打勾。
