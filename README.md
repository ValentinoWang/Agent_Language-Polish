# StyleOS · 文风编译器

StyleOS 是面向自媒体、科研论文与商业材料的非训练式文风系统。它把“怎么说”蒸馏成可版本化的 StyleCard，把“说什么”冻结成 ContentLedger，再通过可审计流水线输出 `final.md + diff.md + audit.json`。

## 当前工程状态

本分支已经从方案仓推进为 **v0.3-ready `0.3.0rc1`**：

- 六个 Pack 均具备 Prompt、Skill 编译、CLI、FastAPI 与本地 MCP 调用合同；
- 内容账本区分硬锁和语义锁；硬锁做确定性回归，语义不确定时阻断自动通过；
- 负面规则按 deterministic / statistical / semantic / human 四级检测；
- 语料 → draft StyleCard → 人工批准 → 改写 → 审计 → 反馈 → Trace 的垂直闭环已实现；
- Pack 专属评测、Wilson 置信区间、优化数据分布守卫和隐私优先 TraceSink 已实现；
- DSPy、图检索和微调只能在真实数据条件满足后启动，代码不会伪造样本或轨迹。

“工程完成”与“实证成熟”分开记录。正式盲测、授权作者 Pilot、300 条成对反馈和 30 天轨迹仍需真实运行产生，因此当前版本是 release candidate，而不是虚标的 production-validated v0.3.0。

## 安装与第一条链路

```bash
uv tool install .
styleos doctor
styleos pack lint
styleos schema-export

styleos distill corpus/a.md corpus/b.md \
  --profile-id self_media.demo.douyin.zh.v1 \
  --track self_media --channel douyin --audience general \
  --output profiles/demo.style_card.yaml

styleos profile approve profiles/demo.style_card.yaml \
  --approved-by reviewer@example

styleos rewrite draft.md --pack self_media \
  --profile profiles/demo.style_card.yaml \
  --mode balanced --output-root runs
```

默认 `provider=offline` 使用保守的规则基线，不会调用外部模型。使用外部模型前显式选择 `--provider openai` 或 `--provider anthropic`，并配置密钥和当前模型名。

## 质量门禁（本地 CI）

常规门禁只在本地执行，不依赖云端 Actions 分钟数；合并前必跑：

```bash
bash scripts/ci.sh              # 完整门禁：lint + 测试/覆盖率 + pack lint + schema/skill 编译 + 构建
bash scripts/install-hooks.sh   # 安装 pre-push 钩子（推送前自动跑快速档）
```

GitHub Actions 仅保留手动触发入口（workflow_dispatch），且复用同一脚本。

## 交付界面

```bash
styleos pack build --output .claude/skills
styleos serve
uv tool install '.[mcp]'
styleos-mcp
styleos readiness
```

## 文档

- `docs/00_方案总览.md`：设计背景与 Pack 决策；
- `docs/01_StyleOS_原始方案.md`：原始研究方案；
- `docs/02_openclaw_media_复用清单.md`：复用边界；
- `docs/03_开发计划_v0-v0.3.md`：修订后的执行合同、完成情况与证据门槛。
- `docs/04_开发对照审计_20260828.md`：实现对照方案的符合性审计、缺陷清单与 local CI 说明。
- `docs/05_开发对照复审_20260828.md`：P1/P2 修复的第二轮复审——逐项核验、假阴性用例重跑与剩余改进。

## 三条红线

1. 事实从 ContentLedger 取，文风从 StyleCard 取；
2. 规则只有一个源，但每条规则按适合的检测级别进入执行与审计，不强迫语义规则退化成正则；
3. 自动化测试通过不等于真实用户验证，任何成熟度升级都必须有对应证据。
