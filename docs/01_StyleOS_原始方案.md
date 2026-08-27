# StyleOS 原始方案（v1 归档）

> **归档说明**：本文是 StyleOS / 文风编译器的原始完整方案，2026-08-27 定稿。其架构判断（四类记忆隔离、非参数式蒸馏、StyleCard 继承、确定性 DAG、五层评测）全部继续有效。
> 后续修订以 [`00_方案总览.md`](00_方案总览.md) 为准，主要增量是：交付层（Pack/多形态编译）设计、与 openclaw-media 的复用对接、路线图前置一个零基础设施的 v0。

---

# 建议做成一个"文风编译器"，而不是提示词库

你现在需要的并不是若干个"去 AI 味 Prompt"，而是一套可以持续积累语料、抽取风格、形成记忆、按赛道调用，并能在 Mac 与腾讯云终端统一运行的**非训练式语言风格系统**。

可以暂定名为：

> **StyleOS / 文风编译器**
> 一套面向多文体、多作者、多终端的非参数式风格蒸馏、检索、改写与审计系统。

这里需要先澄清"蒸馏"的含义：

* 传统知识蒸馏通常涉及教师模型、学生模型和参数训练。
* 你当前阶段不训练模型，因此更准确的技术名称是：
  * **非参数式风格蒸馏**
  * **运行时风格编译**
  * **基于语料的显式风格建模**

它蒸馏的不是模型参数，而是将大量隐性文风转换成一份**可执行、可组合、可检索、可审计的 StyleCard**。

---

# 一、研究检索后的核心判断

最新研究基本支持这样一条路线：

| 研究方向 | 对本项目的启示 |
| --- | --- |
| EMNLP 2025 对个人隐性文风模仿的系统评估 | 仅给模型几篇范文做 in-context imitation，对细微、个人化、非正式文风仍不稳定，不能把"多塞几篇参考文"当成完整方案。 |
| ACL 2026 Style-Eliciting Prompts | 相较于让模型自由概括"这是什么风格"，以固定维度和问题逐项诱导风格特征，更具有可解释性和实用性；自由生成的风格描述还容易带入模型偏见或无依据概括。 |
| CAT-LLM 中文长文本风格迁移 | 将文风显式整理为可插拔的 Text Style Definition，并从词语和句子层面分析，是中文文章风格迁移的一条有效路线。 |
| ZeroStylus 长文本风格迁移 | 长文不能只逐句润色，需要同时控制句子结构、段落结构和段间逻辑；该工作采用句子—段落双层模板，而且不依赖微调。它目前是 arXiv 预印本，应当作为工程启发，而不是未经复核的性能保证。 |
| EMNLP 2025 解耦式多 Agent 风格迁移 | 将内容保持、风格迁移、自检与迭代修复拆开，比一个模型一次性完成全部工作更适合复杂文风。 |
| NAACL 2025 风格迁移评估 | 不能只测"像不像"，必须同时测风格一致性、内容保持和自然度，人工评估仍然是重要部分。 |
| DSPy，ICLR 2024 | 可以把语言处理流程定义成模块化的文本转换图，并在有评测集后优化提示词和模块组合，适合作为后期自动优化层。 |

因此，本项目的最佳平衡点不是"大 Prompt"，也不是立即微调模型，而是：

> **显式 StyleCard + 分层语料检索 + 内容/风格双库隔离 + 确定性改写流水线 + 多维审计 + 人工反馈闭环。**

---

# 二、总体架构

```text
Mac 终端 A ─┐
Mac 终端 B ─┼─> 本地采集器 ─> 内容哈希 / 去重 / 清洗 ─┐
腾讯云终端 ─┘                                         │
                                                     ▼
                                              统一语料入口
                                                     │
                 ┌───────────────────────────────────┼──────────────────────┐
                 ▼                                   ▼                      ▼
          原始文件对象库                       规范化文档库              来源与权限库
       PDF / MD / 视频 / 对话              章节、段落、句子、说话人       作者、时间、授权
                 │                                   │                      │
                 └──────────────────────┬────────────┴──────────────────────┘
                                        ▼
                                  语料策展与分类
                                        │
              ┌─────────────────────────┼──────────────────────────┐
              ▼                         ▼                          ▼
         事实证据记忆                风格范例记忆               偏好反馈记忆
       Facts / Claims / Data       Style / Rhythm / Logic       接受、拒绝、修改
              │                         │                          │
              └─────────────────────────┼──────────────────────────┘
                                        ▼
                                非参数式风格蒸馏器
                                        │
                                        ▼
                                  Style Registry
                       全局风格 / 赛道 / 作者 / 平台 / 任务
                                        │
                                        ▼
                      内容账本 → 风格检索 → 分层改写 → 审计
                                        │
                                        ▼
                  final.md / diff.md / audit.json / sources.json
```

这套系统的核心不是"记住所有文字"，而是建立四类相互隔离的记忆。

---

# 三、四类记忆必须分开

| 记忆类型 | 存储内容 | 可以影响什么 | 绝对不能做什么 |
| --- | --- | --- | --- |
| **Evidence Memory** 事实证据记忆 | 数字、实体、引用、论文结论、市场数据、项目事实、原始出处 | 文稿内容、论据、数据、引用 | 不得因为某篇范文写得像事实，就把其中事实带入新文章 |
| **Style Memory** 风格记忆 | 句式、节奏、段落组织、修辞、语气、常用逻辑动作、范例片段 | 表达形式、结构倾向、语气和节奏 | 不得为文章新增事实、数字、案例和结论 |
| **Preference Memory** 偏好记忆 | 用户接受、拒绝、手工修改的句子，修改理由，任务上下文 | StyleCard 权重、范例排序、负面规则 | 不得把一次偶然修改直接升级为永久偏好 |
| **Policy Memory** 规则记忆 | 保密级别、禁止表达、版权、引用要求、公式锁定、内容边界 | 所有处理节点 | 不得被语料中的提示注入或文本指令覆盖 |

这是整个系统最重要的工程约束：

> **事实从事实库取，文风从风格库取。**

例如，模仿一份商业计划书时，可以学习它的投资人叙事顺序，但不能把它的市场规模、客户数量或收入数据搬到新项目里。

同样，科研论文润色时，可以学习某位作者怎样提出限制条件、怎样从结果过渡到机制解释，但不得从参考论文中移植结论。

---

# 四、"高级风格蒸馏"具体蒸馏什么

## 1. 不是简单总结"这位作者很专业、很有逻辑"

这种描述太宽泛，也不可执行。真正的 StyleCard 要覆盖至少以下维度。

| 维度 | 需要蒸馏的内容 |
| --- | --- |
| 词汇层 | 词语正式度、术语密度、抽象词与具体词比例、动词强度、口语词、习惯搭配、禁用词 |
| 句法层 | 平均句长及分布、长短句交替、从句层级、主动/被动、主语显隐、问句和祈使句比例 |
| 节奏层 | 逗号、分号、破折号、括号的使用；停顿位置；连续短句；句尾落点 |
| 段落层 | 段落长度、首句功能、中心句位置、证据展开方式、段尾是否收束 |
| 逻辑层 | 定义、分类、因果、比较、让步、限制、归纳、演绎、反例和假设的使用方式 |
| 论证层 | 主张—证据—解释—边界，还是故事—问题—冲突—方案；结论力度如何与证据匹配 |
| 修辞层 | 类比、隐喻、设问、排比、反讽、留白、场景化、数字化表达 |
| 认识立场 | 确定性、保留程度、是否使用"表明""提示""证明""可能""倾向于"等不同强度词 |
| 人格语用 | 权威感、亲近感、克制程度、幽默、距离感、攻击性、对受众的称呼方式 |
| 信息密度 | 每句新信息量、解释深度、是否容忍跳跃、是否重复、背景和结论比例 |
| 媒介适配 | 论文、短视频口播、公众号、融资材料、邮件、演讲稿的不同表达规则 |
| 受众适配 | 专家、投资人、普通观众、学生、客户、管理层对应的知识假设 |
| 版式习惯 | 标题层级、列表频率、公式、引用、加粗、案例框、图表说明 |
| 多语言风格 | 中英文术语对应、翻译腔、中文句法是否被英文结构侵入、术语锁定 |
| 负面特征 | 空泛铺垫、假对比、模板化总结、过度解释、价值口号、重复改写同一意思 |
| 条件性规则 | 哪种句式在标题适用、在摘要不适用；短视频可设问，科研结果段则应克制 |

## 2. "去 AI 味"应当被定义成一套负面 StyleCard

它不应等价于删除几个词，也不应以规避 AI 检测器为目标。

需要重点识别的是：

* 没有信息增量的开场，如"在当今快速发展的时代"。
* 不存在真实对立时，强行使用"不是 A，而是 B"。
* 机械的"首先、其次、再次、最后"。
* 每一段都采用近乎相同的句长和结构。
* 重复解释读者已经知道的概念。
* 为了显得深刻而制造抽象名词。
* "不仅……更……"和"这不仅是……更是……"的高频堆叠。
* 无依据的"具有重要意义""值得深入探讨""提供全新视角"。
* 把弱证据写成"证明""揭示了本质""普遍适用"。
* 每段末尾都总结一次，全文末尾再总结一次。
* 过度对称的三段论和标题。
* 先否定一种从未有人主张的解释，再提出自己的解释。
* 用近义词连续重述同一观点，表面丰富，实际没有新增信息。
* 自媒体中持续使用营销式高唤醒词，导致人物显得不真实。
* 商业材料中用口号替代市场数据和商业逻辑。
* 论文中把解释性语言写成教科书式定义，破坏专业读者默认的知识前提。

这些不能被一概设为禁用词。正确方式是为规则增加：

```yaml
pattern: "不是 A，而是 B"
policy: conditional
allow_when:
  - A 是正文已经出现的真实竞争解释
  - B 有明确证据支撑
reject_when:
  - A 只是为了制造修辞冲突而临时虚构
```

---

# 五、蒸馏流程

## 第一步：语料接入

建议采用以下开源组合：

| 语料 | 推荐工具 | 用法定位 |
| --- | --- | --- |
| PDF、DOCX、PPTX、HTML、图片、音频等 | **Docling** | 作为主解析器，保留版面、阅读顺序、表格、公式和结构化表示。 |
| 科研论文 PDF | **GROBID** | 专门提取论文标题、作者、摘要、章节、参考文献、引文和 TEI XML 结构。 |
| 简单办公文件快速转 Markdown | **MarkItDown** | 作为轻量级备选转换器，不把它作为复杂 PDF 的唯一解析器。 |
| 视频、网页视频 | **yt-dlp** | 在来源授权且平台条款允许的前提下抓取音视频或字幕。 |
| 音视频转写 | **faster-whisper** | 本地转写，便于在 Mac 或腾讯云运行。 |
| 对话 | 自定义解析器 | 必须保存说话人、对象、关系、渠道、上下文和是否为最终稿，不能只保存一句裸文本 |

## 第二步：规范化

每一个输入都转换为统一的 `CanonicalDocument`：

```yaml
document_id: sha256:...
source_type: pdf | md | transcript | dialogue | video
author_id: ...
track: academic | self_media | business
genre: paper_intro | short_video | pitch_deck
language: zh-CN
channel: journal | douyin | wechat | investor_meeting
audience: expert | general | investor
created_at: ...
rights:
  owner: ...
  usage: private_style_reference
segments:
  - segment_id: ...
    type: paragraph
    rhetorical_role: evidence
    speaker: null
    text: ...
provenance:
  file_hash: ...
  page: 12
  timestamp: null
```

对话和视频要额外保存：

* 谁在说。
* 对谁说。
* 是正式发言、私聊、采访还是表演性口播。
* 是否经过剪辑。
* 语气、停顿、重音和口头填充词。
* 原始口语与最终字幕之间的差异。

一个人对导师、投资人、粉丝和朋友的语言风格并不相同，因此不能将所有语料混成一个"作者平均风格"。

## 第三步：语料策展

不是所有语料都应该进入风格库。每个文档需要经过：

1. 作者归属检查。
2. 是否为最终发布版本。
3. 是否包含大量引用或他人代写内容。
4. 是否代表目标赛道。
5. 是否具有明确受众和渠道。
6. 是否有授权。
7. 是否存在模板污染、广告污染或机器生成污染。
8. 是否与该作者当前风格仍然一致。

## 第四步：双重特征提取

### 确定性统计特征

由代码直接计算：

* 句长分布，而不仅是平均句长。
* 段落长度分布。
* 标点使用频率。
* 连接词、代词和情态词。
* 高频 n-gram。
* 词汇丰富度。
* 专业术语比例。
* 问句、感叹句、祈使句比例。
* 引用、数字、案例、类比密度。
* 标题和列表使用。
* 首句与段尾的常见结构。

### LLM 语义特征

由模型抽取：

* 段落承担什么修辞功能。
* 作者如何建立权威。
* 如何处理不确定性。
* 如何从事实过渡到判断。
* 如何表达异议和限制。
* 是否喜欢先给结论，还是先铺设问题。
* 情绪曲线如何变化。
* 作者与受众之间的距离。
* 哪些表达属于稳定风格，哪些只是内容导致的偶发现象。

每一条模型抽取的风格规则都不能裸存，应保存证据：

```yaml
rule_id: academic.claim_strength.017
description: "结论通常限定在当前参数范围内，不扩展为普遍规律"
scope:
  track: academic
  sections: [results, discussion]
support_count: 14
confidence: 0.91
evidence_ids:
  - doc_012#p34
  - doc_021#p18
counterexamples:
  - doc_030#p07
status: human_approved
```

## 第五步：对比式蒸馏

仅分析"目标作者有什么"还不够，还要比较：

* 目标作者 vs 同赛道普通文本。
* 目标作者 vs 通用 LLM 输出。
* 已接受的改写 vs 被拒绝的改写。
* 早期作品 vs 当前作品。
* 论文摘要 vs 讨论部分。
* 视频口播 vs 公众号文章。
* 面向专家 vs 面向普通受众。

最后得到的不是"作者经常用长句"，而是：

> 在科研讨论部分，作者允许较长的因果链句；在结论段会主动压缩句子，并通过限制性短语降低结论强度；在自媒体口播中则使用较多短句和停顿。

这才是可调用的条件性风格。

---

# 六、StyleCard 应当采用继承结构

一个最终任务的有效风格，不来自一张卡，而是多层叠加：

```text
中文基础规则
    ↓
赛道规则：科研论文
    ↓
期刊规则：JFM
    ↓
作者规则：个人学术风格
    ↓
项目规则：VIV hysteresis
    ↓
章节规则：Discussion
    ↓
本次任务覆盖：保守润色，不改主张
```

冲突优先级建议设为：

```text
本次任务约束
> 项目规则
> 作者规则
> 渠道或期刊规则
> 赛道规则
> 全局规则
```

一个适合当前科研写作习惯的 StyleCard，可以写成：

```yaml
id: academic.user.jfm.zh.v1
inherits:
  - global.zh.professional
  - domain.academic.paper
  - venue.jfm
scope:
  languages: [zh-CN, en]
  genres: [paper, response_letter, technical_report]
voice:
  authority: restrained
  confidence: evidence_calibrated
  emotional_intensity: low
  reader_assumption: domain_expert
logic:
  preferred_moves:
    - claim_evidence_interpretation_limit
    - mechanism_supported_by_observation
    - explicit_scope_boundary
  avoid_moves:
    - invented_opposition
    - definition_of_common_domain_concepts
    - conclusion_before_evidence
epistemics:
  prefer:
    - "结果表明"
    - "与……相联系"
    - "在当前参数范围内"
    - "该结果支持……解释"
  restricted:
    - "证明"
    - "普遍"
    - "首次发现"
    - "预测"
    - "揭示本质"
    - "全新的模态"
  rule:
    restricted_terms_require_explicit_evidence: true
syntax:
  sentence_length: mixed
  paragraph_opening: direct
  excessive_parallelism: false
  false_contrast: false
negative_patterns:
  - id: x_is_not_y_but_z
    pattern: "不是.*而是"
    policy: allow_only_for_real_competing_hypotheses
  - id: empty_transition
    examples: ["值得注意的是", "众所周知", "总的来说"]
    policy: remove_when_no_logical_function
  - id: repeated_explanation
    policy: merge_or_delete
must_preserve:
  - numbers
  - units
  - equations
  - variables
  - citations
  - figure_references
  - table_references
  - branch_names
  - case_names
quality_gates:
  unsupported_new_claims: 0
  numeric_drift: 0
  citation_drift: 0
  terminology_drift: 0
  novelty_inflation: 0
```

---

# 七、三个首发领域包

## 1. 自媒体文稿包

它不能只是"更口语化"，而应包含：

* 平台：短视频、公众号、小红书、播客、直播、长视频。
* 时长或字数。
* 前 3 秒、前 15 秒和完整叙事的不同目标。
* 开头方式：冲突、问题、结果前置、场景、反常识。
* 口语节奏：换气点、停顿、短句、重音。
* 人物设定：专业感、亲近感、距离感、幽默程度。
* 情绪曲线：冷开场、建立信任、价值释放、情绪回落。
* 证据密度：案例、数字、经历、演示。
* 行动召唤的强度。
* 镜头、字幕、画面和口播是否分离。
* 标题与正文是否采用不同风格。
* 评论区回应风格。
* 避免"知识博主模板腔"和过度营销。

例如，青年数学教师可以建立：

```text
专业价值：数学、研究、解决难题
外在入口：清爽、年轻、镜头表现力
核心人格：高智感、温柔克制、不炫耀
关系感：愿意解释，但不讨好
商业表达：先建立理解和信任，再引导购买
```

这应当作为 `persona.math_teacher`，再分别叠加短视频、直播、课程销售等任务卡。

## 2. 科研论文包

需要处理：

* 摘要、引言、方法、结果、讨论、结论各自的功能。
* 主张与证据的绑定。
* 术语、符号、公式和引用锁定。
* 数值来源追踪。
* 结果描述与机制解释分离。
* 事实、解释、推测和未来工作分级。
* 期刊风格与作者风格的冲突处理。
* 图题、表题和正文一致性。
* 中译英时避免中文逻辑被机械映射。
* 避免夸大 novelty、universality、predictive ability。
* 支持 LaTeX 局部改写，不改命令和公式。
* 支持审稿意见回复、编辑信、补充材料和技术报告。

科研流程建议沿用：

```text
证据冻结
→ 主张—证据矩阵
→ 章节功能检查
→ 中文或英文语言重写
→ 数值/公式/引用回归
→ 学术语气审计
→ diff 交付
```

## 3. 商业计划书包

需要覆盖：

* 投资阶段：种子轮、天使轮、A 轮、产业投资、政府项目。
* 投资人最关心的问题顺序。
* 痛点是否有证据。
* 用户、客户和付款方是否区分。
* 市场规模中的事实、假设和推算是否分离。
* 产品能力与宣传表达是否分离。
* 商业模式、获客成本、毛利、回款周期。
* 竞争格局和护城河。
* 研发、销售、渠道和交付之间的关系。
* 财务表与文字叙述的一致性。
* 风险是否真实，而不是形式化列举。
* 团队经历是否与项目能力相关。
* 融资用途、里程碑和下一轮条件。
* 路演稿、BP 正文和演讲口播三种不同文风。

商业包必须强制标注：

```yaml
statement_type:
  - verified_fact
  - internal_data
  - external_estimate
  - management_assumption
  - forecast
  - aspiration
```

这样系统就不会把"计划达到"润色成"已经实现"。

---

# 八、可自然扩展的其他赛道

同一框架可以继续覆盖：

* 基金申请书、科研项目申请书。
* 学位论文和开题报告。
* 技术白皮书、测试报告、设计报告。
* 专利技术交底书。
* 政府申报材料。
* 企业战略备忘录和管理层汇报。
* 产品需求文档、系统设计文档。
* 课程讲义、培训材料、科普稿。
* 演讲稿、采访稿、播客脚本。
* 销售邮件、客户方案、客服话术。
* 新闻稿、品牌公关稿。
* 中英文翻译与风格本地化。
* 简历、个人陈述、推荐信。
* 合同说明、政策解读等高风险文本，但必须保留人工专业复核。

系统的分类不应该只有"科研、自媒体、商业"三种，而应使用多维标签：

```text
赛道 × 文体 × 渠道 × 受众 × 作者 × 人设 × 任务 × 风险级别
```

---

# 九、运行时 Agent 设计

不建议一开始做一个自由讨论的 Agent 群。更可靠的是**有明确输入输出结构的确定性 DAG**。

```text
1. Task Router          识别赛道、文体、受众、语言、风险、强度
2. Content Ledger Builder  提取并锁定实体、数字、公式、引用、主张、限制条件
3. Style Retriever      检索 StyleCard、正例、反例、历史接受修改
4. Structure Planner    决定是否保持结构，或进行段落重排
5. Paragraph Rewriter   先完成段落功能和逻辑结构迁移
6. Sentence Polisher    再处理句法、节奏、词汇和修辞
7. Fidelity Auditor     检查是否新增事实、改变数字、遗漏条件、误改引用
8. Style Auditor        检查目标风格与负面模式
9. Domain Auditor       按科研、自媒体或商业标准检查
10. Bounded Repair      最多进行 1—2 次针对性修复，禁止无限自循环
11. Exporter            输出正文、diff、审计记录和来源
```

工作流可以写成：

```python
classify_task
    -> build_content_ledger
    -> retrieve_style_bundle
    -> plan_structure
    -> rewrite_paragraphs
    -> polish_sentences
    -> check_fidelity
    -> check_style
    -> check_domain
    -> bounded_repair(max_rounds=2)
    -> export_receipt
```

其中每个节点都输出结构化文件：

```text
task_spec.json / content_ledger.json / retrieval_bundle.json / draft_v1.md
fidelity_report.json / style_report.json / domain_report.json
final.md / diff.md / audit.json
```

这种架构符合"架构、执行、质疑和验收相互分离，但所有角色都受同一份冻结合同约束"的使用方式。

---

# 十、检索不能只做普通向量搜索

风格检索应采用：

> **稠密语义检索 + 稀疏关键词检索 + 元数据过滤 + 可选重排序。**

Qdrant 当前支持 dense、sparse 和 multivector 检索，也支持基于 JSON payload 的条件过滤；其混合查询可以对多路结果进行融合。

风格检索过滤条件至少包括：

```yaml
track: academic
genre: paper_discussion
language: zh-CN
author_id: user
audience: domain_expert
channel: journal
quality: approved
source_status: final_version
time_range: current_style_period
```

每次只取少量高质量范例，例如：

* 2—3 个段落结构范例。
* 3—5 个句式和节奏范例。
* 2 个反例。
* 相关 StyleCard 规则。
* 最近被接受的修改记录。

不要把整套语料直接塞进上下文。整库输入不仅成本高，还会混淆任务、作者、媒介和事实来源。

---

# 十一、推荐技术栈

## 当前轻量化版本

| 层 | 推荐方案 |
| --- | --- |
| 语言 | Python |
| 包与跨终端安装 | `uv` |
| 数据模型 | Pydantic |
| CLI | Typer |
| API | FastAPI |
| 原始文件 | 腾讯云 COS，或自建 MinIO |
| 元数据和版本 | PostgreSQL；单机开发可先 SQLite |
| 风格及语义检索 | Qdrant |
| 文档解析 | Docling |
| 学术 PDF | GROBID |
| 快速 Markdown 转换 | MarkItDown |
| 视频接入 | yt-dlp |
| 音频转写 | faster-whisper |
| 流程执行 | 初期使用普通 Python DAG |
| 提示词优化 | 有评测集后引入 DSPy |
| 可恢复人工审批 | 后期按需引入 LangGraph |
| 跟踪和评测 | 后期加入 Langfuse |
| Agent 接口 | CLI + REST + MCP |

`uv` 提供独立安装方式，并可以把 Python 包作为隔离的命令行工具安装到 PATH，适合作为多个 Mac 终端的统一安装入口。

MCP 适合做外部适配层，因为它为 AI 应用访问工具、数据资源和工作流提供了标准接口；但主系统仍应首先保证 CLI 和 HTTP API 可用，不能让核心能力依赖某一个聊天客户端。

LangGraph 支持可恢复执行和 human-in-the-loop，Langfuse 提供开源的跟踪、评测和调试能力；两者有价值，但不必放进第一个 MVP，以免初期基础设施过重。

---

# 十二、为什么暂时不把 Mem0、GraphRAG 或 HippoRAG 放在核心层

Mem0 的主要定位是为 Assistant 或 Agent 保存长期、个性化记忆，适合保存"用户偏好"和少量稳定事实，但不适合直接充当原始语料和论文证据的唯一可信存储。

GraphRAG 和 HippoRAG 更适合跨文档实体关联、多跳事实检索和知识整合。HippoRAG 使用知识图谱与 Personalized PageRank 进行关联检索；Microsoft GraphRAG 也明确提示图索引可能成本较高。

因此建议：

* **风格层第一阶段不用图。**
* **Preference Memory 可以后续接 Mem0。**
* **跨论文、市场报告和项目资料的事实推理，后续再引入 GraphRAG 或 HippoRAG。**
* 原始文件、规范化文档和 StyleCard 始终由自己的数据库与对象存储管理。

向量库和图数据库都应当是**可重建索引**，不能成为唯一真源。

---

# 十三、跨 Mac 与腾讯云的即插即用方式

## Mac 终端

预期使用方式：

```bash
uv tool install styleos
styleos init
styleos doctor
styleos ingest ~/Documents/style-corpus --track academic --profile user.academic
styleos ingest ./videos --track self_media --profile math_teacher.short_video
styleos distill --profile user.academic --version v1
styleos rewrite draft.md --profile user.academic.jfm --mode conservative
styleos review --run-id RUN_ID
styleos feedback --run-id RUN_ID --accept
styleos sync
```

建议支持三个改写强度：

| 模式 | 允许操作 |
| --- | --- |
| `conservative` | 不改结构和主张，只调整句法、重复、术语和节奏 |
| `balanced` | 允许合并拆分句子、调整段落内部顺序 |
| `strong` | 允许重建叙事和段落结构，但内容账本仍完全锁定 |

## 腾讯云端

第一阶段使用 Docker Compose 即可：

```text
styleos-api / styleos-worker / postgres / qdrant / grobid / object-storage-adapter
```

不建议一开始上 Kubernetes、Kafka 或复杂微服务。任务量不高时，可以直接使用 PostgreSQL 任务表和一个 Worker，减少 Redis、消息队列和集群维护。

## 分布式终端同步

每台终端运行轻量采集器：

```text
监听目录 → 计算 SHA-256 → 生成 manifest → 本地解析或上传
→ 中央端去重 → 写入 outbox → 网络恢复后同步
```

建议为数据设置三种模式：

```yaml
storage_mode:
  local_only: 原文不离开当前设备
  cloud_private: 加密上传至个人云端
  shared_profile: 仅上传批准后的抽象 StyleCard 和范例
```

StyleCard、配置和测试用例可以进私有 Git；原始语料、私密对话和视频不应进入 Git。

---

# 十四、MCP 暴露的工具

为了让不同终端或 Agent 调用，建议只暴露有限的高层工具：

```text
style_ingest / style_search / style_distill / style_profile_get
style_rewrite / style_review / style_compare / style_feedback / style_export
```

不要把数据库写入、删除原始文件、自动批准 StyleCard 等底层操作直接暴露给模型。

例如：

```json
{
  "tool": "style_rewrite",
  "arguments": {
    "input": "draft.md",
    "profile": "academic.user.jfm",
    "mode": "conservative",
    "locks": ["numbers", "equations", "citations", "figure_references"],
    "output": ["final.md", "diff.md", "audit.json"]
  }
}
```

---

# 十五、即插即用的 Prompt 组块

运行时提示不应是一整段无法维护的大 Prompt，而应由七个独立组块编译。

```text
[BLOCK 1: TASK CONTRACT]     任务类型、赛道、受众、渠道、字数、语言、改写强度。
[BLOCK 2: CONTENT LEDGER]    必须保留的实体、数字、公式、引用、主张、限制和因果关系。
[BLOCK 3: STYLE CARD]        当前任务生效的词汇、句法、逻辑、修辞、人格和负面规则。
[BLOCK 4: DOMAIN PACK]       科研、自媒体、商业计划书等领域专属要求。
[BLOCK 5: RETRIEVED EXEMPLARS] 少量正例、反例和已接受修改，不提供无关完整文档。
[BLOCK 6: OPERATION RULES]   允许拆句、合句、重排或删减的范围；禁止新增事实。
[BLOCK 7: OUTPUT CONTRACT]   只输出正文，或同时输出 diff、问题列表和审计报告。
```

一个通用编译模板可以是：

```text
你是受约束的语言编辑器，不是事实生成器。
【任务】{task_spec}
【内容账本】以下内容均为冻结项，不得新增、删除、替换、扩大或改变因果关系：{content_ledger}
【风格规范】{effective_style_card}
【领域规则】{domain_pack}
【参考范例】范例仅用于学习表达形式，不得继承其中的事实：{retrieved_exemplars}
【负面规则】{negative_patterns}
【允许操作】{allowed_operations}
【禁止操作】{forbidden_operations}
【验收条件】
1. 数字、实体、公式、符号、引用和限定条件保持一致。
2. 不产生来源文本中不存在的新事实。
3. 不使用空泛总结替代具体分析。
4. 每处实质性调整都能在 diff 中定位。
5. 无法确认的内容保留原文并标记，不自行补全。
【输出】{output_schema}
```

这样每一个"块"都可以独立升级，不需要每次重写整套提示词。

---

# 十六、评测体系

"像不像人写的"不能作为唯一指标。建议建立五层评测。

## 1. 硬约束检查

必须程序化验证：

* 数字是否改变。
* 单位是否改变。
* 实体、变量、分支名是否改变。
* 公式和 LaTeX 命令是否损坏。
* 引用是否新增、遗漏或错配。
* 图表编号是否改变。
* 商业事实是否从"计划"变成"已完成"。
* 科研结论是否扩大适用范围。

目标应当是：

```text
锁定内容保持率：100%
无来源新增事实：0
公式和引用损坏：0
```

## 2. 内容保持

检查：

* 是否遗漏原有信息。
* 是否改变因果方向。
* 是否把相关性写成因果。
* 是否把假设写成结论。
* 是否把局部结果扩展成普遍结论。

## 3. 风格匹配

同时使用：

* 统计特征距离。
* StyleCard 规则命中率。
* 目标作者与通用输出的对比判断。
* 正反例排序。
* LLM Judge，但不能只依赖一个 Judge。

## 4. 自然度和领域质量

* 自媒体：能否顺畅口播，人物是否一致，是否有真实信息增量。
* 科研：是否符合章节功能，主张强度是否匹配证据。
* 商业：投资逻辑是否完整，事实和预测是否分离。

## 5. 人工成对偏好

每次比较：

```text
A：普通 one-shot "去 AI 味"结果
B：StyleOS 结果
```

记录：选 A、选 B 或相当；哪一句更好；修改原因；是否只对当前任务有效；是否应升级为永久规则。

建议的初始验收线：

* 锁定项全部通过。
* 不以降低事实准确性换取文风。
* 在每个赛道的固定盲测集上，人工对 StyleOS 的偏好率显著高于普通 Prompt 基线。
* 每个输出都有可回溯的 StyleCard 版本、范例来源、模型配置和审计结果。

"AI 检测器分数"最多作为辅助观察项，不能作为优化目标。

---

# 十七、推荐的代码仓库结构

```text
styleos/
├── apps/            # cli / api / mcp
├── core/            # ingest / normalize / curate / distill / retrieve / rewrite / evaluate / feedback
├── adapters/        # docling / grobid / markitdown / whisper / object_storage / model_providers
├── schemas/         # document / style_card / content_ledger / audit
├── packs/           # global / self_media / academic / business
├── profiles/
├── prompts/
├── evaluations/
├── migrations/
├── infra/           # docker-compose.yml / mac
└── tests/
```

---

# 十八、当前阶段明确不做什么

为了兼顾效果和工程难度，v0.1 应明确排除：

1. 不训练或微调模型。
2. 不构建庞大的知识图谱。
3. 不让所有聊天自动进入永久记忆。
4. 不将事实库和风格库混为一个向量库。
5. 不把整篇参考语料塞进 Prompt。
6. 不使用无限循环的 Agent 自我修改。
7. 不让模型自行批准新的永久偏好。
8. 不把某一个 AI 检测器当作质量标准。
9. 不对未经授权的私人语料进行作者仿写。
10. 不为追求文风而修改数字、引用、公式和原始结论。
11. 不先建设复杂前端；先把 CLI、API、审计链和数据结构做正确。
12. 不把 Qdrant、Mem0 或图数据库当成唯一真源。

---

# 十九、分阶段实施路线

## v0.1：最小可用"文风编译器"

范围锁定为：文本/Markdown/DOCX/PDF；自媒体、科研、商业计划书三个领域包；StyleCard 抽取、人工批准和版本管理；事实库与风格库隔离；混合检索；分层改写；数字、引用、公式和实体锁定；CLI 与 REST API；`final + diff + audit` 三件套。

## v0.2：多媒体和多终端

加入：视频、音频、对话；Mac 文件夹监听；腾讯云中心端；断网队列与内容哈希同步；MCP 工具；接受/拒绝反馈；作者、渠道、受众条件化风格。

## v0.3：自动优化和高级记忆

在积累足够人工接受/拒绝样本后加入：DSPy 提示词和模块优化；LangGraph 人工审批与中断恢复；Langfuse 跟踪和评测；事实层 GraphRAG 或 HippoRAG；Style Knowledge Graph；必要时基于高质量成对修改数据进行轻量微调。

模型训练应当是**反馈数据成熟后的结果**，而不是项目的起点。

---

# 最终路线判断

四条可能路线中：

| 路线 | 效果稳定性 | 工程难度 | 当前判断 |
| --- | ---: | ---: | --- |
| 一个大型"去 AI 味"Prompt | 低 | 低 | 只能做临时基线 |
| 直接把大量范文塞入上下文 | 中低 | 低 | 容易混风格、混事实、成本高 |
| 立即微调模型 | 潜力高 | 高 | 当前数据和评测体系尚不成熟 |
| **StyleCard + 双库检索 + 分层改写 + 审计** | **高** | **中等** | **当前最优路线** |

最值得先做的不是一个"万能改写 Agent"，而是四个基础件：

> **统一语料格式、可执行 StyleCard、内容账本、可审计改写 DAG。**

这四部分稳定后，自媒体、科研论文、商业计划书以及后续新增赛道，本质上都只是增加新的 Domain Pack，而不需要重建底层系统。

---

## 参考文献

1. EMNLP 2025 Findings — 个人隐性文风模仿评估: https://aclanthology.org/2025.findings-emnlp.532/
2. ACL 2026 Findings — Style-Eliciting Prompts: https://aclanthology.org/2026.findings-acl.2039/
3. CAT-LLM 中文长文本风格迁移: https://arxiv.org/abs/2401.05707
4. ZeroStylus 长文本风格迁移: https://arxiv.org/abs/2505.07888
5. EMNLP 2025 Findings — 解耦式多 Agent 风格迁移: https://aclanthology.org/2025.findings-emnlp.1166/
6. NAACL 2025 SRW — 风格迁移评估: https://aclanthology.org/2025.naacl-srw.41/
7. DSPy (ICLR 2024): https://openreview.net/forum?id=sY5N0zY5Od
8. Docling: https://github.com/docling-project/docling
9. GROBID: https://github.com/kermitt2/grobid
10. MarkItDown: https://github.com/microsoft/markitdown
11. yt-dlp: https://github.com/yt-dlp/yt-dlp
12. faster-whisper: https://github.com/SYSTRAN/faster-whisper
13. Qdrant: https://github.com/qdrant/qdrant
14. uv tools: https://docs.astral.sh/uv/concepts/tools/
15. MCP: https://modelcontextprotocol.io/
16. LangGraph: https://github.com/langchain-ai/langgraph
17. Mem0: https://github.com/mem0ai/mem0
18. HippoRAG (NeurIPS 2024): https://proceedings.neurips.cc/paper_files/paper/2024/hash/6ddc001d07ca4f319af96a3024f6dbd1-Abstract-Conference.html
