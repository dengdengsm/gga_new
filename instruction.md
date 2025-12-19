# 🛠️ GGA 后端架构与内部逻辑指南

## 1. 架构概览 (Architecture Overview)

本项目基于 **FastAPI** 构建，采用 **多 Agent 协作 (Multi-Agent Collaboration)** 架构。后端不仅仅是一个简单的 API 转发器，而是一个拥有“记忆”、“自我修正”和“结构化推理”能力的智能系统。

### 核心技术栈

* **框架**: FastAPI (异步处理, BackgroundTasks)
* **LLM 驱动**: DeepSeek-V3 (核心逻辑/代码生成), Qwen-Long (长文档阅读), Qwen-VL (视觉分析)
* **RAG 引擎**: LightGraphRAG (自研金字塔图谱架构), ChromaDB (向量存储), NetworkX (图数据结构)
* **存储**: 本地文件系统 (以 Project 为单位隔离)

---

## 2. 核心模块与职责 (Core Modules)

系统被拆分为职责单一的 Agent 和服务模块：

| 模块文件 | 组件名称 | 核心职责 |
| --- | --- | --- |
| `api_server.py` | **Orchestrator** | 系统的总线。负责接收请求、任务调度、以及串联各个 Agent 的执行流（如生成->校验->修复闭环）。 |
| `router.py` | **RouterAgent** | **决策大脑**。分析用户意图，检索历史经验，决定使用哪种图表类型（Prompt），并提取结构化逻辑数据。 |
| `codez_gen.py` | **CodeGenAgent** | **执行者**。根据 Router 提供的结构化逻辑和指定的 Prompt 模板，生成 Mermaid/Graphviz 代码。支持“丰富度(Richness)”控制。 |
| `code_revise.py` | **CodeReviseAgent** | **修复专家**。当生成的代码报错时，利用 RAG（错题本）检索修复策略，并进行自我修正。 |
| `graphrag.py` | **LightGraphRAG** | **知识引擎**。实现了 V6.0 金字塔图谱架构。负责将文档转化为知识图谱，并提供基于图的检索能力。 |
| `document_reader.py` | **DocumentAnalyzer** | **全能阅读器**。统一接口，支持 PDF/Word (Qwen-Long) 和 图片 (Qwen-VL) 的深度内容提取。 |
| `project_manager.py` | **ProjectManager** | **管家**。管理多项目目录、文件状态记录以及文件系统的增删改查。 |

---

## 3. 核心运行流程详解 (Key Workflows)

### 3.1 标准图表生成流 (The Generation Pipeline)

这是用户输入文本或上传文件生成图表的核心路径：

1. **上下文构建 (`api_server.py` -> `build_file_context`)**:
* 检查 `ProjectManager` 中的文件记录。
* **Graph Mode**: 如果开启 RAG 图谱，调用 `LightGraphRAG.search()`，通过图谱游走获取核心概念和关系。
* **Direct Mode**: 如果未开启图谱，直接调用 `DocumentAnalyzer` 读取文件摘要。


2. **路由与策略制定 (`router.py`)**:
* `RouterAgent` 接收上下文和用户 Prompt。
* **经验检索**: 在内部向量库中搜索相似的历史成功案例（User Intent -> Past Strategy）。
* **决策**: 输出 JSON，包含目标图表类型（如 `flowchart.md`）和提取出的**结构化逻辑 (Structured Logic)**。


3. **代码生成 (`codez_gen.py`)**:
* 加载对应的 Prompt 模板（如 `prompt/code_gen/flowchart.md`）。
* 注入 **Richness (丰富度)** 指令，控制生成节点的数量和详细程度。
* 调用 LLM 生成初始 Mermaid 代码。


4. **自我修正闭环 (`api_server.py` -> `run_code_revision_loop`)**:
* **语法预检**: 调用 `utils.quick_validate_mermaid` 进行正则或逻辑校验。
* **自动修复**: 如果校验失败，调用 `CodeReviseAgent`。
* CodeRevise 检索 `mistakes.json` (错题本)。
* 结合报错信息和历史错题经验，重新生成代码。
* 此过程最多重试 3 次。


* **经验反哺**: 如果修复成功，CodeRevise 会自动提炼本次错误特征和修复策略，写入错题本（Double-Loop Learning）。



### 3.2 LightGraphRAG 构建流 (The Pyramid Construction)

`graphrag.py` 实现了一套复杂的图谱构建算法，旨在解决传统 RAG 碎片化的问题：

* **Phase 0: 切片**: 同时生成 **Big Chunks** (1500 tokens) 和 **Small Chunks** (500 tokens)。
* **Phase 1: 主干提取 (Layer 1 Backbone)**: 使用 Qwen-Long 读取全文，提取最顶层的核心实体和关系，构建图谱骨架。
* **Phase 2: 中层填充 (Layer 2 Intermediate)**: 并发处理 Big Chunks，将局部实体挂载到骨架上，丰富图谱结构。
* **Phase 3: 细节下钻 (Layer 3 Drill-down)**: 识别图谱中的高权重节点（Focus Targets），并发扫描 Small Chunks，提取高密度的细节关系。
* **Phase 4: 图谱优化 (Optimization)**: LLM 审视孤立节点和碎片，执行合并（Merge）、连接（Connect）或删除操作，确保图谱连通性。

### 3.3 GitHub 智能分析流 (GitHub Analysis)

`api_server.py` 中的 `process_github_background` 任务：

1. **Loader**: 使用 `git_loader.py` 克隆仓库。
2. **Tree Gen**: 生成目录树结构。
3. **Smart Select**: 智能筛选核心代码文件（过滤非代码文件，限制数量）。
4. **Deep Read**: 调用 `DocumentAnalyzer` 对选中的每个代码文件进行深度阅读，提取类、函数和依赖关系。
5. **Synthesis**: 将目录树 + 核心文件分析结果组合成由上至下的 Context。
6. **Pipeline**: 送入上述的“标准生成流”生成架构图。

---

## 4. 关键算法与机制 (Key Mechanisms)

### A. 双环学习机制 (Double-Loop Learning)

系统具有两条学习路径，使其越用越强：

1. **Router 经验池 (`router.json`)**: 当图表生成成功且语法校验通过时，Router 会提炼 "用户意图" -> "图表设计策略" 的映射，并在下次遇到类似需求时召回。
2. **CodeRevise 错题本 (`mistakes.json`)**: 当代码修复成功后，Agent 会提炼 "报错特征" -> "修复手法" 的映射。

### B. 动态丰富度控制 (Dynamic Richness)

在 `codez_gen.py` 中，根据前端滑块传来的 `0.0 - 1.0` 的浮点数，动态注入 Prompt 指令：

* **< 0.3**: 强制 High-Level Summary，限制节点数量 < 10。
* **0.4 - 0.7**: 标准逻辑，清晰展示结构。
* **> 0.8**: 源码级保真度，展示所有细节。

### C. 统一文档分析 (Unified Document Analysis)

`document_reader.py` 封装了复杂的逻辑：

* 如果是 **URL**，自动下载处理。
* 如果是 **图片**，动态切换 `model_name` 为 `qwen-vl-max`，使用视觉 Prompt 提取空间逻辑。
* 如果是 **文档/代码**，使用 `file-extract` 协议上传至 DashScope，利用 Qwen-Long 的长上下文能力进行提取。

---

## 5. 数据存储结构 (Data Persistence)

系统数据存储在 `.projects/` 目录下，结构如下：

```text
.projects/
  ├── default/                  # 默认项目
  │   ├── uploads/              # 上传的原始文件
  │   ├── graph_db/             # GraphRAG 数据 (NetworkX JSON + Pickle)
  │   ├── history.json          # 生成历史记录
  │   └── files.json            # 文件状态索引
  ├── project_b/                # 其他项目
  │   └── ...

```

* **热更新**: `api_server.py` 提供了 `/api/projects/switch` 接口，切换项目时会调用 `rag_engine.reload_db`，自动保存当前内存图谱并加载新项目的图谱，实现无缝切换。
