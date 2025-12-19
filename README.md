# 智能图表生成器 (Smart Diagram Generator)

本项目是一个全栈应用，旨在通过结合强大的后端处理能力（Python/FastAPI）和现代化的前端界面（Next.js/React）来智能地生成和编辑 Mermaid 图表。

本项目前端改自smart-mermaid项目，感谢大佬的技术支持

## 🚀 快速开始

请按照以下步骤快速设置和运行项目。本项目分为 **后端 (Backend)** 和 **前端 (Frontend)** 两个部分，需要分别配置和启动。

### 1. 环境要求

在开始之前，请确保您的系统已安装以下软件：

* **Git**: 用于克隆项目代码。
* **Anaconda/Miniconda**: 用于管理 Python 环境和依赖。
* **Python**: **3.13 版本**（用户指定）。
* **Node.js**: **22 版本** 或更高 (LTS)。
* **npm/yarn/pnpm**: Node.js 包管理器。

### 3\. 后端设置 (Python/FastAPI)

后端服务负责处理核心的业务逻辑和依赖（如 LangChain、OpenAI 等）。

**技术栈概览:** Python, FastAPI, Uvicorn, LangChain, OpenAI, HuggingFace。

1.  **创建和激活 Conda 环境**

    使用 Conda 创建一个 Python 3.13 的虚拟环境并激活它：

    ```bash
    conda create -n gga_env python=3.13
    conda activate gga_env
    ```

2.  **安装 Python 依赖**

    进入 `backend` 目录，安装 `requirements.txt` 中列出的所有依赖：

    ```bash
    cd backend
    pip install -r requirements.txt
    ```

4.  **启动后端服务**

    使用 Uvicorn 启动 FastAPI 应用。默认端口通常是 8000：

    ```bash
    python api_server.py
    ```

    如果启动成功，您将在终端看到服务运行在 `http://127.0.0.1:8000` 或类似地址。

### 4\. 前端设置 (Next.js)

前端应用是用户界面，使用 Next.js 和 React 构建。

**技术栈概览:** Next.js, React, Tailwind CSS, Mermaid, Excalidraw。

1.  **安装 Node.js 依赖**

    返回项目根目录，然后进入 `smart-mermaid` 目录，安装 Node.js 依赖：

    ```bash
    cd .. # 如果您当前在 backend 目录
    cd smart-mermaid
    npm install  # 或者使用 yarn / pnpm install
    ```

3.  **启动前端应用**

    使用 `dev` 脚本启动 Next.js 开发服务器：

    ```bash
    npm run dev
    ```

    前端应用通常运行在 `http://localhost:3000`。

### 5\. 完成！

一旦后端服务（默认 8000 端口）和前端应用（默认 3000 端口）都成功启动，您就可以在浏览器中访问：

🌐 **http://localhost:3000**

开始使用您的智能图表生成器！

```
