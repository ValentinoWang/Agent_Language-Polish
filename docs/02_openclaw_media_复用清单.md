# openclaw-media 复用清单

> 盘点对象：`ValentinoWang/openclaw-media`，分支 `codex/pipeline-audit-p0-p2-20260827`（HEAD `0138eff`），2026-08-27 全库审读。
> 结论先行：**那边已经存在一条完整的"去AI味"改写生产链路**（`selfmedia/style/`），StyleOS 不必从零造轮子——v0.1 的工程主体是"把这条单一场景链路泛化 + 补上它缺失的 StyleCard 层"。
> 本文所有路径相对 openclaw-media 仓库根目录。

---

## 1. 已经有什么（按对 StyleOS 的价值排序）

### 1.1 `selfmedia/style/` —— 完整的去AI味改写链路 ⭐⭐⭐

单一能力 `style_polish`（飞书标签【润色】【去AI味】【网感】等的归一目标）：

- **请求契约**（`contract.py`，frozen dataclass）：`raw_text / platform / content_type / goal / account / tone / must_keep / avoid / variants(1..5)`——`must_keep`/`avoid` 正是内容账本锁定项的雏形。
- **上下文装配**（`context_loader.py`）：账号长期记忆 + 达人档案 + 平台机制 + 反AI腔禁语 + 近期复盘教训，聚合为 `StyleContext`。
- **反AI腔禁语表**（`assets/anti_patterns.yaml`）：18 条（"在当今时代/赋能/打造闭环/深度融合/具有重要意义/值得一提的是/不仅如此/总而言之/综上所述/不难发现/让我们一起…"）。**已全部并入本仓库 `packs/global/deai.negative.zh.yaml` 的对应条件式规则**。
- **代码级硬校验**（`validators.py::validate_version_text`）：`must_keep` 缺失、`avoid` 出现、平台 `forbidden_claim_patterns` 命中——三重子串扫描，命中即拒。
- **四维评分**（`service.py`）：`naturalness / voice / clarity / fact_fidelity`，1–5 整数强校验，聚合取最小值（保守打分）。
- **产物落盘**：`data/media_vault/tenants/<t>/style_polish_runs/<run_id>/{request,context,result,feedback_record}.json`。
- **润色 prompt 本体**（`service.py:182-197`）值得整段借鉴的两条：约束 3 反对机械口语化（"不要为了口语化机械添加'说实话''其实'"）；约束 5 表述强度守恒（"不得把演示、相关或参考结果升级成已证实的控制、诊断或疗效"）——后者就是学术/商业态最需要的规则。

### 1.2 `selfmedia/creator_profiles/` —— 证据化画像的现成形状 ⭐⭐⭐

达人档案抽取流水线（爬取→解析→LLM候选→**人工确认**→落盘）。其 LLM 输出形状是每字段一个四元组：

```json
{"value": "", "evidence": [], "confidence": 0, "reason": ""}
```

配套规则："Do not invent facts"、"证据不足就留空+低置信+写明原因"、候选/确认两段式（`generate_candidate_run` / `confirm_candidate_run`）。**本仓库 StyleCard 的 `evidence_rules` 结构与 distill pack 的"证据规则表 + 待人工确认清单"即按此形状设计**。注意：CreatorProfile 是身份画像（学历/领域/角色/人设边界），不是文风画像——文风维度是 StyleOS 的净增量。

### 1.3 其他直接可用件

| 路径 | 给我们什么 | 集成成本 |
| --- | --- | --- |
| `common/llm_validation.py` | LLM 输出契约注册表：prompt↔契约↔profile（strict_structured / bounded_open）绑定，import 期冲突检测，校验失败带错误重试 | 低 |
| `common/llm_client.py` + `llm_settings.py` | 多 transport provider 抽象、`generate_json_from_parts(max_retries, validation_contract)`、SSE+watchdog、容量退避 | 低–中（需新增 Anthropic transport，现有三种均非 Claude API） |
| `media_vault/vault.py` | `media://` URI 寻址、8 字段 manifest（含 content_hash）、租户隔离（跨租户=not_found）、read/write/list/search | 低 |
| `common/content_cleaner.py` | OCR/转写/采集文本 LLM 去噪（断行、乱码、页码），带分块——论文 PDF 与 BP 文档预处理直接用 | 低 |
| `config/platform_mechanisms/*.json` | "规范载体"通用结构：`baseline_summary / core_signals / validation_targets / evidence_policy{S..D} / forbidden_claim_patterns[]`。小红书禁"保证爆款/必爆"与学术禁"无据首次发现"、商业禁"行业第一"同构 → 派生 `academic_norms` / `bp_norms` | 低 |
| `runtime/cli/selfmedia.py` | CLI 形态：argparse 子命令 + `--no-write / --dry-run / --smoke` 三档降级 + `--tenant-id` 强隔离 | 低 |
| `selfmedia/creation/platform_validator.py` | 零依赖纯函数规则校验器模板（标题长度、必备字段）→ 改造成期刊字数/BP 章节完整性校验 | 低 |
| `selfmedia/deconstruct/viral_content/src/runner.py` | 多阶段 LLM 流水线的阶段落盘 + `--resume-stage-json` 断点续跑，无编排框架依赖 | 低 |
| `selfmedia/deconstruct/viral_content/src/multi_signal_schema.py` | `DimensionAnalysis`（`extra="forbid"`，维度数量由证据决定）——风格特征提取的合同形状 | 中 |
| `selfmedia/context/media_context.py` | 作者长期记忆三写（JSONL+JSON+Markdown）、复盘→`proven_patterns`/`avoid_patterns` 沉淀、prompt 渲染带截断 | 中（剥离飞书分支） |
| `selfmedia/ingest/content_flow/` | URL→下载(yt-dlp/Playwright)→转写(DashScope ASR，含说话人分离)→OCR(tesseract)→分析 的 LangGraph DAG——自媒体语料接入直接复用 | 中 |
| `openclaw-tag-router/.../router/style_polish.py` | 中文标签字段解析器（`原文/平台/目标/必须保留/不能出现`），意图→目标映射（"去AI味"→"降低书面腔、模板腔和 AI 腔"） | 低 |
| `media-agent-cli/generate_product_clients.py` | 一份 JSON Schema 同时生成 Python TypedDict + TS 类型，契约不漂移 | 中（做 Web 时才需要） |

### 1.4 已在生产验证过的文风规则（已吸收进本仓库 packs）

- 口播："每句尽量不超过 22 个字，允许口语连接词和自然的不完整句，写完要能直接读出口不别扭"（`creation/llm_generator.py` 约束 19、`viral_content/src/prompt.py:91`）→ 进 `packs/self_media`。
- 禁"首先/其次/最后"连用、"总之/综上/值得一提的是"套话、连续三个以上排比、每句感叹号、无关热词堆叠 → 进 `packs/self_media` 第四步与 `deai.negative.zh.yaml`。
- 反空话："禁止'引发共鸣''戳中痛点'这种无信息量表达，必须写清哪类欲望/恐惧/身份叙事被什么句式/画面/情境触发"（`prompt.py:74` 约束 22）；禁止占位话术"未明确体现/待复核"（`analyzer.py`）→ 蒸馏与自检的措辞纪律。
- 账号声音优先：成稿必须贴 `account_profile` 可见的说话方式，缺语言样本时写明缺口但仍完成初稿（约束 30）→ `imitate` pack 的冲突与缺口处理。

---

## 2. 没有什么（= StyleOS 的净增量）

1. **文风特征提取器**：没有任何模块从样本文本里蒸馏句长分布、标点习惯、口癖、段落节奏——现有链路的"风格"全靠 LLM 隐式感知 `account_profile.markdown`。
2. **StyleCard 实体**：不存在风格卡；`feedback.py` 明确 `creative_pattern_promotion: "manual_only"`，从不自动沉淀风格模式；`assets/example_seed.jsonl` 是自我声明的空壳。
3. **whisper/faster-whisper**：完全没有。转写唯一走阿里云 DashScope ASR（`fun-asr`），且代码硬性拒绝其他 provider——原方案"faster-whisper 本地转写"的假设在那边不成立，v0.2 需二选一（云端沿用 DashScope / 本地自建 faster-whisper）。
4. **MCP / FastAPI / Typer**：零命中。HTTP 用 stdlib `ThreadingHTTPServer`，CLI 全 argparse。
5. **文档语料入口**：ingest 只吃 URL（抖音/小红书/B站/直链视频），没有 markdown/PDF/DOCX 本地文件入口——论文与 BP 的接入要新建（Docling/GROBID 路线不变）。
6. **Claude API**：providers 只配了 `openclaw_codex`（openclaw agent 子进程），代码另支持 openai 两种 transport；Anthropic 需新增。

---

## 3. 架构定位：为什么 StyleOS 独立成仓

`selfmedia/style/validators.py:9-12` 有一条护栏：

```python
FORBIDDEN_STYLE_SSOT_NAMES = {
    "creator_voice.yaml": "账号人格必须来自 media_context / media_memory / CreatorProfile",
    "pattern_bank.jsonl": "表达模式必须来自 CreativePattern，不允许另建 pattern bank",
}
```

openclaw-media 明令禁止在库内另建风格事实源——这是架构洁癖而非技术限制，但它决定了 StyleCard 不能"顺手"长在那边。加上 StyleOS 要覆盖科研与商业两个与自媒体运营无关的赛道，结论：

> **StyleOS 独立成仓（本仓库）作为跨赛道风格 SSOT；openclaw-media 是第一个宿主。**
> 对接三点：① 负面规则卡作为共享 SSOT 回灌，合并其两份漂移的黑名单（正是其审计 CPC-07 的修法建议）；② human_approved 的 StyleCard 渲染进 `style_polish` 的 context 与 creation 链约束 30 的账号声音槽位；③ 自媒体语料接入复用其 `content_flow`，不重建下载与转写。

---

## 4. 三个必须绕开的坑（原样照抄会翻车）

1. **仓外绝对路径**：`media_context.py:21`、`context_loader.py:16`、`media_model/contract.py:9` 等硬编码 `/home/ubuntu/docs/ai-harness/...`（本地不存在的契约文件）。复用任何模块前先把契约路径参数化。
2. **手写 YAML 解析器**：`context_loader.py::_read_yaml_mapping` 是 30 行自制解析，只支持顶层 key 与一层列表。StyleOS 直接用 pyyaml。
3. **pydantic v1 API 跑在 v2 上**：`viral_content` 的 schemas 全用 `@validator/@root_validator/parse_obj/.dict()`，靠 v2 deprecation 兼容层运行。StyleOS 新代码一律 v2 原生（`@field_validator / model_validate / model_dump`）。

## 5. 两条要继承的工程教训（来自其 4215 行流水线审计）

1. **CPC-07（P1）**：风格链与创作链各维护一份反AI腔黑名单 → 集合漂移；且创作链的黑名单只活在 prompt 里，没有代码校验。修法="单一 SSOT + 规则双投影（既进 prompt 又进 validator）"——本仓库从第一天执行：`deai.negative.zh.yaml` 是唯一规则源，v0.1 编译器同时生成 prompt 注入与校验清单。
2. **Prompt 约束必须有测试锚**：该分支多数"像人"修复是无测试引用的 prompt 字符串，唯一正例是 `tests/selfmedia/style/test_style_polish.py:143`（断言 prompt 含关键句"像给朋友发一段 30 秒语音"）。StyleOS v0.1 起：每条关键约束句都要有"构建出的 prompt 确实包含它"的断言。
