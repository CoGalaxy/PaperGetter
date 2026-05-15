# Paper Get Agent

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

AI 驱动的论文审查工具：输入一篇 PDF，自动完成**方法论提取 → 因果链主张 → 靶向验证 → 六维度局限性分析 → 综合总结**，输出结构化报告。提供 CLI 和 Web 两种使用方式。

## 设计理念

传统论文审阅依赖人工逐段阅读。Paper Get Agent 将审阅流程建模为多 Agent 流水线，每个 Agent 独立调用 LLM 完成特定任务：

| Agent | 目标 | 做法 |
|-------|------|------|
| **Parser** | PDF → 结构化文档 | PyMuPDF 提取全文 + LLM 识别章节标题 |
| **Extractor** | 提取方法论与核心主张 | 两阶段：Pass 1 方法骨架 → Pass 2 因果链主张 + 去重 |
| **Validator** | 靶向验证观点自洽性 | 为每条 claim 生成 toy script → 沙箱执行 → LLM 对照判断 |
| **Analyzer** | 多维度局限性审查 | 方法 / 实验 / 理论 / 可复现性 / 泛化性 / 伦理 |
| **Summarizer** | 总结提炼 | 每条 claim 一句话摘要 + 整体 2-3 段论文总结 |

> 不做完整复现，而是靶向生成最小可运行代码来检查核心逻辑的自洽性。不对论文打分，只呈现分析结果供用户判断。

## 快速开始

### 1. 安装

```bash
pip install -e .
```

### 2. 配置

编辑 `config.yaml`，至少填写 API key：

```yaml
llm:
  api_base: "https://api.deepseek.com"
  api_key: "sk-your-key-here"
  models:
    extraction: "deepseek-v4-pro"
    code_generation: "deepseek-v4-flash"
    parsing: "deepseek-v4-flash"
    comparison: "deepseek-v4-flash"
    limitation: "deepseek-v4-pro"
    summarization: "deepseek-v4-pro"
```

也支持环境变量 `LLM_API_KEY`。

### 3. CLI 运行

```bash
python main.py paper.pdf                 # 全流程
python main.py paper.pdf --skip-validate  # 跳过验证（推荐日常使用）
python main.py paper.pdf -o reports/      # 指定输出目录
```

输出：
- `output/<标题>_<日期>.md` — Markdown 报告
- `output/<标题>_<日期>.json` — 结构化数据

### 4. Web 界面

```bash
python -m web.server
# 打开 http://localhost:8000
```

- **主页** — 拖拽上传 PDF，实时进度（含 LLM 流式输出），历史任务
- **报告页** — 结构化渲染：方法论卡片、因果链手风琴、验证对照、局限性着色、LaTeX 公式、总结
- **设置页** — 可视化编辑 `config.yaml`（6 个 Agent 模型指派、温度、沙箱参数等）
- 一键下载 Markdown / 打印彩色 PDF

## 流水线架构

```
PDF ──→ [Parser] ──→ Paper ──→ [Extractor] ──→ Methodologies
                                     │            + Claims (因果链)
                                     │
                                     ├──→ [Validator] ──→ 每条 claim
                                     │        │              ├── LLM 生成 toy code
                                     │        │              ├── 沙箱执行
                                     │        │              └── LLM 对照判断
                                     │
                                     ├──→ [Analyzer] ──→ 6 维度局限性
                                     │
                                     └──→ [Summarizer] ──→ 逐 claim 摘要
                                              │              + 整体总结
                                              ↓
                                     AnalysisReport
                                              ↓
                                    Markdown + JSON + Web
```

### 各组件

| 组件 | 文件 | LLM 调用 | 职责 |
|------|------|---------|------|
| **Parser** | `parser/parser.py` | 2 次（元信息 + 标题识别） | PyMuPDF 提取全文 + LLM 提取作者/venue/DOI 等元信息 + LLM 识别章节标题，输出 `Paper` |
| **Extractor** | `extractor/extractor.py` | 2 次（Pass 1 方法 + Pass 2 主张） | 提取方法论骨架（步骤/公式/创新点）→ 因果链主张 + 前提展开 + 去重合并 + 原文溯源；智能按章节重要性分配上下文预算 |
| **Validator** | `validator/validator.py` | 每 claim 2 次 | 生成 toy script → 沙箱执行 → LLM 对照判断 (supported / partially / not) |
| **Analyzer** | `analyzer/analyzer.py` | 1 次 | 6 维度局限性审查，含严重性评级和建议 |
| **Summarizer** | `summarizer/summarizer.py` | 1 次 | 每条 claim 一句话摘要 + 整篇论文 2-3 段总结，结合发表年代语境 |
| **Sandbox** | `sandbox/sandbox.py` | — | Docker 隔离执行（fallback subprocess），网络隔离，内存限制 |
| **Orchestrator** | `orchestrator/graph.py` | — | 串联 5 阶段，实时进度回调，报告渲染与导出 |

### LLM 客户端

`llm/client.py` — OpenAI 兼容接口，按任务自动切换模型，自动适配两类模型：

- **Reasoner 模型**（deepseek-v4-pro 等）— 不支持 `response_format`/`tool_choice`，采用 prompt 注入 JSON Schema + 多策略正则提取
- **通用模型**（deepseek-v4-flash 等）— 使用 `response_format: json_object`，失败时回退 reasoner 策略
- 支持流式输出 (`stream=True` + `on_chunk` 回调)，供 Web 前端实时展示 LLM 输出

## 数据模型

### Claim — 因果链结构

每条主张以因果链组织，回答五个问题：

```
Claim
├── problem: str            # 针对什么问题
├── method_applied: str     # 应用了什么方法
├── mechanism: str          # 为什么有效（因果逻辑，核心字段）
├── result: str             # 产生了什么效果
├── condition: str          # 在什么前提下成立
├── summary: str            # 一句话摘要（Summarizer 生成）
├── context: str            # 原文支撑段落（附章节编号引用）
├── source_sections: [str]  # 来源章节，如 ["第3节: Experiments"]
├── assumptions: [str]      # 隐含前提
├── confidence: float       # 可靠性 0-1
└── related_method_ids: [str]  # 关联的方法论
```

如果原文对某个环节未论述，LLM 会标注 `缺失：原文未论述` 而非编造。每条主张可追溯到原文段落。

### 完整报告结构

```
AnalysisReport
├── paper: PaperMeta          # 标题/作者/年份/arXiv/DOI/摘要
├── methodologies: [Methodology]
│   ├── name, category, overview
│   ├── procedure: [step, ...]
│   ├── key_formulas: [latex, ...]
│   └── innovations: [point, ...]
├── claims: [Claim]           # 因果链主张
├── validations: [ValidationResult]
│   ├── verdict: supported | partially | not_supported | unverifiable
│   └── generated_code, execution_output, evidence
├── limitations: [Limitation]
│   ├── category: method | experiment | theory | reproducibility | generalization | ethics
│   ├── severity: low | medium | high | critical
│   └── description, suggested_fix
└── summary: str              # 整体总结（2-3 段）
```

## 项目结构

```
paper_get_agent/
├── config.yaml                       # 模型指派 & 沙箱 & parser 配置
├── main.py                           # CLI 入口 (Click + Rich 实时面板)
├── src/paper_get_agent/
│   ├── models/paper.py               # Pydantic 数据模型 + 中文标签映射
│   ├── llm/client.py                 # OpenAI 兼容客户端（流式/结构化/自适应）
│   ├── parser/parser.py              # PDF → Paper（PyMuPDF + LLM 元信息提取 + 标题识别）
│   ├── extractor/extractor.py        # 两阶段提取：方法骨架 → 因果链主张 + 去重 + 原文溯源 + 智能裁剪
│   ├── validator/validator.py        # 靶向验证：生成代码 → 沙箱执行 → 对照
│   ├── analyzer/analyzer.py          # 6 维度局限性分析
│   ├── summarizer/summarizer.py      # 逐 claim 摘要 + 整体总结（含年代语境）
│   ├── sandbox/sandbox.py            # Docker/subprocess 代码沙箱
│   └── orchestrator/graph.py         # 流水线编排 + 报告渲染 + 导出
├── web/                              # Web 前端
│   ├── server.py                     # FastAPI 应用 (17 个端点 + SSE)
│   ├── job_manager.py                # 内存任务管理 + 后台线程执行
│   ├── config_api.py                 # 配置读写 + Pydantic 校验 + API key 脱敏
│   └── static/index.html             # SPA (Alpine.js + Tailwind + MathJax)
├── papers/                           # 待分析 PDF
└── output/                           # 生成报告
```

## Web 前端技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 后端 | FastAPI + uvicorn | Pydantic 模型直接复用，SSE 原生支持 |
| 实时通信 | Server-Sent Events | 单向推送进度 + LLM 流式输出，浏览器原生 `EventSource` |
| 前端 | Alpine.js + Tailwind CSS CDN | 零构建步骤，无 npm，单 HTML 文件 |
| 公式渲染 | MathJax 3 | `$$...$$` 块级公式，服务器端不参与渲染 |
| PDF 导出 | `@media print` CSS | 浏览器打印 → 另存为 PDF，保留着色标签和卡片样式 |

## 支持的 LLM

通过 OpenAI 兼容接口对接，在 `config.yaml` 中自由切换：

| 提供商 | 推理模型 | 通用模型 | API Base |
|--------|---------|---------|----------|
| DeepSeek | `deepseek-v4-pro` | `deepseek-v4-flash` | `api.deepseek.com` |
| 阿里 Qwen | `qwen3-max` | `qwen3-plus` | `dashscope.aliyuncs.com` |
| 月之暗面 | `kimi-k2` | `kimi-k2` | `api.moonshot.cn` |

6 个 Agent 各自可指派不同模型，按任务特点选择：提取/分析/总结用推理模型，解析/代码生成/对照用通用模型。

## 已知局限

- **元信息提取**：作者/venue/DOI 依赖 LLM 从首页识别，部分排版特殊的论文可能提取不全。不可用时回退 regex。
- **代码验证**：目前为实验性功能，toy script 成功率不稳定。Web 端默认关闭，CLI 通过 `--skip-validate` 跳过。
- **单用户设计**：Web 后端使用内存存储，重启丢失任务历史。多用户场景需引入持久化层。
- **长论文处理**：采用按重要性分级裁剪策略——核心章节保留全文，背景/附录压缩。极长论文的尾部章节仍可能被压缩。

## License

MIT
