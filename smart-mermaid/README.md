# Smart Mermaid: AI 驱动的文本转 Mermaid 图表工具

Smart Mermaid 是一个将自然语言文本转换为 Mermaid 代码并渲染为图表的 Web 应用。支持常见 Mermaid 图表类型（如流程图、序列图、甘特图、状态图等），提供标准渲染与手绘风渲染两种模式，并内置代码修复与优化能力。

## 访问体验

[https://smart-mermaid.aizhi.site](https://smart-mermaid.aizhi.site)

提示（演示环境）：默认每日 5 次免费额度（基于浏览器本地按日计数），用于功能体验。演示环境使用服务端配置的上游 API Key，稳定性与速率取决于上游服务。如需更高配额或稳定性，可在设置中配置自有密钥，或联系作者沟通。

<img src="https://github.com/user-attachments/assets/8d123b76-e402-435a-9d20-1231e78ce8c1" width="200px">

<img src="https://github.com/user-attachments/assets/c41a6245-f169-4ede-afad-c2e9f5955343" width="200px">

## 功能概览

- 文本转图表：将文本转换为符合 Mermaid 规范的代码，可自动或手动选择图表类型。
- 流式生成（可选）：基于 SSE 增量返回内容，编辑器可实时显示生成片段。
- 双渲染器：
  - Mermaid 渲染器（SVG）：支持缩放、平移、重置、全屏与 SVG 下载。
  - Excalidraw 渲染器（手绘风格）：基于转换结果渲染，支持 PNG 下载。
- 代码辅助：复制、AI 智能修复（/api/fix-mermaid）、一键方向切换（TD/LR）。
- 优化能力：AI 优化（/api/optimize-mermaid）与优化建议（/api/optimize-mermaid/suggestions），可一键应用或输入自定义指令。
- 文件导入：支持 `.txt`、`.md`、`.docx` 提取文本后生成图表。
- 历史记录：本地存储历史条目，可回看与回填。
- 使用限制与解锁：默认每日 5 次（本地存储计数）。通过访问密码验证或自定义 AI 配置可解除限制。
- 模型选择：可通过环境变量 `AI_MODELS` 提供候选列表；未配置则使用默认模型。

## 效果预览

![PixPin_2025-05-23_11-25-46](https://github.com/user-attachments/assets/7ad74f73-68f3-499f-bcb4-f2b3e67336e8)

*图：Smart Mermaid 操作界面与生成的图表*

## 快速上手

1. 输入或上传文本（支持 `.txt`/`.md`/`.docx`）。
2. 选择图表类型（或保持自动）与模型，可按需开启“实时生成”。
3. 点击“生成图表”，右侧展示 Mermaid 代码与渲染结果。
4. 如渲染报错，用“AI 修复”或手动调整；需要更佳布局可“继续优化”或切换 TD/LR。
5. 导出：Mermaid 渲染器下载 SVG；Excalidraw 渲染器下载 PNG。

## 架构与依赖（概览）

- Next.js 15（App Router），React 19
- UI：shadcn/ui、Radix UI；主题：next-themes
- 样式：Tailwind CSS v4
- 渲染：`mermaid`、`@excalidraw/excalidraw`、`@excalidraw/mermaid-to-excalidraw`
- 文件解析：`mammoth`（.docx）
- AI 调用：OpenAI 兼容接口；SSE 用于增量处理
- 本地数据：`localStorage`（历史记录与用量计数）

## 部署

### Docker

```bash
# 克隆项目
git clone https://github.com/liujuntao123/smart-mermaid.git
cd smart-mermaid

# 一键启动
docker-compose up -d

# 本地访问
# http://localhost:3000
```

### 本地开发

要求：Node.js 18+，npm 或 yarn。

```bash
git clone https://github.com/yourusername/smart-mermaid.git
cd smart-mermaid
npm install
```

在项目根目录创建 `.env.local`：

```plaintext
# 服务端 AI 配置（建议在服务器环境设置）
AI_API_URL=https://api.openai.com/v1
AI_API_KEY=在此处填入您的API密钥
AI_MODEL_NAME=gpt-3.5-turbo

# 可选：候选模型列表，格式：id:name:desc,id2:name2:desc2
# AI_MODELS=

# 客户端
NEXT_PUBLIC_MAX_CHARS=20000
NEXT_PUBLIC_DAILY_USAGE_LIMIT=5

# 可选：访问密码（验证通过可解除额度限制）
ACCESS_PASSWORD=设置您的访问密码
```

启动与访问：

```bash
npm run dev
# http://localhost:3000
```

生产环境：

```bash
npm run build
npm run start
```

## 使用与权限

- 演示额度：默认每日 5 次（基于本地存储按日计数）。
- 解除限制：
  - 验证访问密码（与服务端 `ACCESS_PASSWORD` 一致）。
  - 在设置中填写自有 AI 服务（`apiUrl`/`apiKey`/`modelName`）。
- 历史与用量均存于浏览器本地；服务器不持久化用户输入或生成内容。

## 已知限制

- 生成/优化质量依赖上游模型；复杂图可能需要手动微调。
- 上游返回不总是严格代码块，接口已做容错提取，仍可能需要少量清理。
- 用量限制按浏览器与设备独立计算，不共享。

## 贡献与反馈

欢迎通过 Issues 反馈问题与建议，或提交 PR 参与共建。

<img src="https://github.com/CecilPenn/stars/blob/main/svgs/smart-mermaid.svg">

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=liujuntao123/smart-mermaid&type=Date)](https://www.star-history.com/#liujuntao123/smart-mermaid&Date)

如果这个项目对你有帮助，欢迎点亮 ⭐️。
