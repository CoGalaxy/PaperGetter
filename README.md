# Paper Get Agent

论文快速理解与验证智能体。

对一篇论文，自动完成：

1. **观点提炼** — 提取核心主张（理论型 / 实验型 / 对比型 / 设计型）
2. **代码化验证** — 为每条主张生成 toy script，沙箱执行并对照结论
3. **局限性分析** — 从方法、实验、理论、可复现性、泛化性、伦理 6 个维度审视

> 不做完整复现，而是靶向生成最小可运行代码来验证观点的逻辑自洽性。

## 快速开始

### 1. 安装

```bash
conda activate vllm
pip install -e .
```

### 2. 配置 API Key

编辑 `config.yaml`，填入你的 API key：

```yaml
llm:
  api_base: "https://api.deepseek.com/v1"   # DeepSeek / AIHubMix / One-API
  api_key: "sk-your-key"
  models:
    extraction: "deepseek-reasoner"           # 观点提取用推理模型
    code_generation: "deepseek-chat"          # 代码生成用通用模型
    limitation: "deepseek-reasoner"           # 局限性分析用推理模型
```

也可以环境变量：

```bash
export LLM_API_KEY="sk-your-key"
export LLM_API_BASE="https://api.deepseek.com/v1"
```

### 3. 分析论文

```bash
python main.py papers/test.pdf                # 全流程
python main.py papers/test.pdf --skip-validate  # 跳过代码验证
python main.py papers/test.pdf -o reports/       # 指定输出目录
```

输出：`output/<标题>_<日期>.md` + `.json`。

## 支持模型

通过 OpenAI 兼容接口对接，在 `config.yaml` 中切换：

| 提供商 | 推理模型 | 通用模型 | 接口域名 |
|--------|---------|---------|---------|
| DeepSeek | `deepseek-reasoner` | `deepseek-chat` | `api.deepseek.com` |
| 阿里 Qwen | `qwen3-max` | `qwen3-plus` | `dashscope.aliyuncs.com` |
| 月之暗面 | `kimi-k2` | `kimi-k2` | `api.moonshot.cn` |
| 统一网关 | 按网关配置 | 按网关配置 | 网关地址 |

## 流水线架构

```
PDF → [Parser] → 结构化 Paper → [Extractor] → Claims 列表
                                    ↓
                               [Validator] → 每条 claim → toy code → 沙箱执行 → 对照
                                    ↓
                               [Analyzer] → 6 维度局限性审查
                                    ↓
                               Markdown / JSON 报告
```

## 项目结构

```
paper_get_agent/
├── config.yaml                 # 模型 & 沙箱配置
├── main.py                     # CLI 入口
├── src/paper_get_agent/
│   ├── models/paper.py         # Pydantic 数据模型
│   ├── llm/client.py           # OpenAI 兼容客户端
│   ├── parser/parser.py        # PDF 解析 → 结构化
│   ├── extractor/extractor.py  # LLM 观点提取
│   ├── validator/validator.py  # 靶向代码验证
│   ├── analyzer/analyzer.py    # 局限性分析
│   ├── sandbox/sandbox.py      # Docker/子进程沙箱
│   └── orchestrator/graph.py   # 流水线编排 + 报告生成
├── tests/
└── papers/                     # 待分析论文
```

## 验证模式

不试图复现完整实验。对每条 claim 生成一个目标明确的 toy script：

| Claim 类型 | 验证方式 | 超时 |
|-----------|---------|------|
| 理论型 | 数值模拟验证不等式/界的 tightness | 30s |
| 实验型 | 合成数据对比核心 idea vs baseline | 30s |
| 对比型 | 构造边界条件检查结论是否成立 | 30s |
| 设计型 | 实现最小原型验证逻辑 | 30s |

## 依赖

- Python >= 3.11
- PyMuPDF（PDF 解析）
- OpenAI SDK + Instructor（LLM 调用）
- Pydantic v2（数据模型）
- Click + Rich（CLI）
- Docker（可选，沙箱执行）
