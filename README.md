# Paper Get Agent

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

AI 驱动的论文快速审查 Agent：输入一篇 PDF 论文，自动完成**观点提炼**、**靶向验证**、**局限性分析**三阶段审查，输出结构化的 Markdown + JSON 报告。

## 设计理念

传统论文审阅依赖人工逐段阅读，效率低且容易遗漏关键细节。Paper Get Agent 将审阅流程建模为多阶段 LLM 流水线：

| 阶段 | 目标 | 做法 |
|------|------|------|
| **观点提炼** | 快速抓住论文核心贡献 | LLM 从全文中提取方法论（步骤、公式、创新点）与核心主张（含前提假设和置信度评估） |
| **靶向验证** | 用最小代价检查观点自洽性 | 为每条 claim 生成 30 秒内可跑完的 toy script，沙箱执行后 LLM 对照执行结果与主张 |
| **局限性分析** | 指出论文薄弱环节 | 从方法、实验、理论、可复现性、泛化性、伦理 6 个维度系统审查 |

> 不做完整复现实验，而是靶向生成最小可运行代码来验证核心逻辑的自洽性。

## 快速开始

### 1. 安装

```bash
pip install -e .
```

### 2. 配置 API Key

编辑 `config.yaml`：

```yaml
llm:
  api_base: "https://api.deepseek.com"
  api_key: "sk-your-key-here"
  models:
    extraction: "deepseek-v4-pro"      # 观点提取 — 强推理模型
    code_generation: "deepseek-v4-flash"  # 代码生成 — 快速模型
    parsing: "deepseek-v4-flash"          # 标题识别
    comparison: "deepseek-v4-flash"       # 验证对照
    limitation: "deepseek-v4-pro"      # 局限性分析 — 强推理模型
```

也支持环境变量 `LLM_API_KEY` 和 `LLM_API_BASE`。

### 3. 运行

```bash
python main.py paper.pdf                    # 全流程：提取 + 验证 + 分析
python main.py paper.pdf --skip-validate    # 跳过代码验证（仅提取 + 分析）
python main.py paper.pdf -o reports/        # 指定输出目录
```

输出两个文件：
- `output/<标题>_<日期>.md` — 可读 Markdown 报告
- `output/<标题>_<日期>.json` — 完整结构化数据

## 流水线架构

```
PDF ──→ [Parser] ──→ Paper ──→ [Extractor] ──→ Methodologies + Claims
                                    │
                                    ├──→ [Validator] ──→ 每条 claim
                                    │        │              ├── LLM 生成 toy code
                                    │        │              ├── 沙箱执行
                                    │        │              └── LLM 对照判断
                                    │
                                    └──→ [Analyzer] ──→ 6 维度局限性

                                              ↓
                                     AnalysisReport
                                              ↓
                                    Markdown + JSON
```

### 各组件职责

- **Parser** (`parser/parser.py`) — PyMuPDF 提取全文 + LLM 识别章节标题 + 表格提取，输出结构化 `Paper`
- **Extractor** (`extractor/extractor.py`) — LLM 结构化提取方法论（名称、步骤、公式、创新点）与核心观点（类型、主张、前提假设、置信度）
- **Validator** (`validator/validator.py`) — 为每条 claim 生成 Python toy script → 沙箱执行 → LLM 对照执行结果与主张，输出 supported / partially_supported / not_supported
- **Analyzer** (`analyzer/analyzer.py`) — 从 method / experiment / theory / reproducibility / generalization / ethics 六维度审查局限
- **Sandbox** (`sandbox/sandbox.py`) — Docker 隔离执行（不可用时 fallback 到 subprocess），网络隔离、内存限制
- **Orchestrator** (`orchestrator/graph.py`) — 串联四阶段流水线，实时进度回调，综合评分，导出 Markdown + JSON

## 项目结构

```
paper_get_agent/
├── config.yaml                       # 模型指派 & 沙箱配置
├── main.py                           # CLI 入口 (Click + Rich)
├── src/paper_get_agent/
│   ├── models/paper.py               # Pydantic 数据模型 (Paper/Claim/Methodology/Limitation/...)
│   ├── llm/client.py                 # OpenAI 兼容客户端，自动适配 reasoner/general 模型
│   ├── parser/parser.py              # PDF 解析 → 结构化 Paper
│   ├── extractor/extractor.py        # LLM 方法论与观点提取
│   ├── validator/validator.py        # 靶向代码验证
│   ├── analyzer/analyzer.py          # 多维度局限性分析
│   ├── sandbox/sandbox.py            # Docker/subprocess 代码沙箱
│   └── orchestrator/graph.py         # 流水线编排 + 超时 + 报告渲染
├── tests/
└── papers/                           # 待分析论文存放
```

## 数据模型

### 核心输出结构

```
AnalysisReport
├── paper: PaperMeta          # 标题 / 作者 / DOI / 摘要
├── methodologies: [Methodology]
│   ├── name, category, overview
│   ├── procedure: [step, ...]
│   ├── key_formulas: [latex, ...]
│   └── innovations: [point, ...]
├── claims: [Claim]
│   ├── type: theoretical | empirical | comparative | design
│   ├── statement, context
│   ├── assumptions: [前提, ...]
│   └── confidence: 0.0-1.0
├── validations: [ValidationResult]
│   ├── verdict: supported | partially_supported | not_supported | unverifiable
│   ├── generated_code, execution_output
│   └── evidence
├── limitations: [Limitation]
│   ├── category: method | experiment | theory | reproducibility | generalization | ethics
│   ├── severity: low | medium | high | critical
│   └── description, suggested_fix
└── overall_score: 0.0-10.0
```

## 支持的 LLM

通过 OpenAI 兼容接口对接，在 `config.yaml` 中自由切换：

| 提供商 | 推理模型 | 通用模型 | API Base |
|--------|---------|---------|----------|
| DeepSeek | `deepseek-v4-pro` | `deepseek-v4-flash` | `api.deepseek.com` |
| 阿里 Qwen | `qwen3-max` | `qwen3-plus` | `dashscope.aliyuncs.com` |
| 月之暗面 | `kimi-k2` | `kimi-k2` | `api.moonshot.cn` |
| AIHubMix / One-API | 按网关配置 | 按网关配置 | 网关地址 |

客户端自动适配两类模型：
- **Reasoner 模型**（不支持 `response_format` / `tool_choice`）→ prompt 注入 JSON Schema + 正则提取
- **通用模型** → `response_format: json_object`，失败时回退 reasoner 策略

## 验证策略

对每条 claim 的验证方式取决于其类型：

| Claim 类型 | 验证方式 | 超时 |
|-----------|---------|------|
| theoretical | 数值模拟验证不等式/bound 的 tightness | 30s |
| empirical | 合成数据对比核心 idea vs baseline | 30s |
| comparative | 构造边界条件检查结论是否成立 | 30s |
| design | 实现最小原型验证逻辑 | 30s |

## License

MIT
