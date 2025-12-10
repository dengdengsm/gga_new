import json
import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# --- 引入你的核心模块 ---
# 确保这些文件都在同一目录下
from router import RouterAgent
from graphrag import LightGraphRAG
from codez_gen import CodeGenAgent
from code_revise import CodeReviseAgent
from utils import quick_validate_mermaid

# --- 初始化 FastAPI ---
app = FastAPI(title="Smart Mermaid Backend (Sync Version)")

# 允许跨域 (解决前端直连端口的问题)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. 初始化 Agents ---
print("🚀 [Backend] 正在启动后端引擎，加载 Agents...")

# 确保必要的目录存在
os.makedirs("./.local_graph_db", exist_ok=True)
os.makedirs("./.uploaded_docs", exist_ok=True)

# 初始化核心对象
try:
    # 知识图谱引擎
    rag_engine = LightGraphRAG(persist_dir="./.local_graph_db")
    
    # 路由智能体 (开启学习模式)
    router_agent = RouterAgent(model_name="deepseek-chat", learn_mode=True)
    
    # 代码生成智能体
    code_gen_agent = CodeGenAgent(model_name="deepseek-chat")
    
    # 代码修复智能体
    code_revise_agent = CodeReviseAgent(
        mistake_file_path="./knowledge/experience/mistakes.json", 
        model_name="deepseek-chat"
    )
    print("✅ [Backend] 引擎加载完毕！")
except Exception as e:
    print(f"❌ [Backend] 引擎加载失败: {e}")
    # 不中断程序，防止因为没key直接崩掉，但实际调用会报错

# --- 2. 定义请求体结构 ---

class GenerateRequest(BaseModel):
    text: str
    diagramType: str = "auto"
    # 接收前端传来的其他配置参数 (虽然这里主要用 text)
    aiConfig: Optional[Dict[str, Any]] = None
    accessPassword: Optional[str] = None
    selectedModel: Optional[str] = None

class FixRequest(BaseModel):
    mermaidCode: str
    errorMessage: str
    aiConfig: Optional[Dict[str, Any]] = None

class PasswordRequest(BaseModel):
    password: str

# --- 3. 业务接口定义 ---

# === 接口 A: 文件上传 (构建图谱) ===
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    接收前端上传的文件，保存并调用 RAG 构建图谱
    """
    try:
        # 保存文件
        file_location = f"./.uploaded_docs/{file.filename}"
        with open(file_location, "wb+") as file_object:
            file_object.write(file.file.read())
            
        print(f"📂 [Upload] 收到文件: {file.filename}，开始构建图谱...")
        
        # 调用 rag.py 的 build_graph
        # 注意：文件较大时这里会阻塞一段时间
        rag_engine.build_graph(file_location)
        
        print(f"✅ [Upload] 图谱构建完成")
        return {"status": "success", "message": f"图谱构建成功: {file.filename}"}
    except Exception as e:
        print(f"❌ [Upload] 失败: {e}")
        return {"status": "error", "message": str(e)}

# === 接口 B: 核心生成 (同步闭环模式) ===
@app.post("/api/generate-mermaid")
async def generate_mermaid(request: GenerateRequest):
    """
    核心接口：RAG -> Router -> CodeGen -> Check -> Revise -> Return JSON
    """
    user_query = request.text
    print(f"\n⚡ [Generate] 收到请求: {user_query[:50]}...")

    try:
        # 1. RAG 检索
        print("   -> 正在检索知识库...")
        context = rag_engine.search(user_query, top_k=3)
        
        # 2. Router 决策
        print("   -> Router 正在制定策略...")
        route_res = router_agent.route_and_analyze(user_content=context, user_target=user_query)
        prompt_file = route_res.get("target_prompt_file", "flowchart.md")
        logic_analysis = route_res.get("analysis_content", "")
        print(f"   -> 策略: {route_res.get('reason', '常规')} (使用模板: {prompt_file})")
        
        # 3. 生成代码 (调用同步方法)
        print("   -> 正在生成代码...")
        # 注意：这里我们调用原始的 generate_code 方法，不使用 _stream
        # 这样拿到的是完整的、带换行符的字符串
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file)
        
        # 4. 后端自动校验
        print("   -> 正在校验代码语法...")
        validation = quick_validate_mermaid(initial_code)
        
        final_code = initial_code
        
        if not validation['valid']:
            # --- 自动修复流程 ---
            error_msg = validation['error']
            print(f"   ❌ 校验失败: {error_msg[:50]}... 启动自动修复")
            
            attempt_history = [{"code": initial_code, "error": error_msg}]
            
            # 调用同步修复方法
            fixed_code = code_revise_agent.revise_code(
                initial_code, 
                error_message=error_msg, 
                previous_attempts=attempt_history
            )
            
            final_code = fixed_code
            print("   ✅ 自动修复完成")
            
            # 记录错题 (闭环学习)
            try:
                code_revise_agent.record_mistake(initial_code, error_msg, final_code)
            except Exception as e:
                print(f"   ⚠️ 错题记录失败: {e}")
        else:
            print("   ✅ 校验通过，代码完美")
            # 记录成功经验 (闭环学习)
            try:
                router_agent.learn_from_success(user_query, final_code)
            except: pass

        # 5. 返回结果
        # 直接返回字典，FastAPI 会自动处理成标准 JSON，换行符会被转义为 \n，前端能完美识别
        return {
            "mermaidCode": final_code,
            "error": None
        }

    except Exception as e:
        print(f"🔥 [Generate] 处理异常: {e}")
        return {
            "mermaidCode": "",
            "error": str(e)
        }

# === 接口 C: 手动修复 (同步模式) ===
@app.post("/api/fix-mermaid")
async def fix_mermaid(request: FixRequest):
    """
    前端点击'智能修复'按钮时调用
    """
    try:
        print(f"🔧 [Fix] 收到手动修复请求")
        fixed_code = code_revise_agent.revise_code(
            request.mermaidCode, 
            error_message=request.errorMessage
        )
        return {
            "fixedCode": fixed_code,
            "error": None
        }
    except Exception as e:
        print(f"❌ [Fix] 修复失败: {e}")
        return {
            "fixedCode": request.mermaidCode,
            "error": str(e)
        }

# === 接口 D: 辅助接口 (Mock) ===
@app.get("/api/models")
async def get_models():
    return {
        "success": True,
        "models": [
            {"id": "deepseek-chat", "name": "DeepSeek V3 (Server)", "description": "Backend Default"},
            {"id": "deepseek-reasoner", "name": "DeepSeek R1 (Reasoning)", "description": "High Intelligence"}
        ]
    }

@app.post("/api/verify-password")
async def verify_password(req: PasswordRequest):
    return {"success": True, "message": "Access Granted"}

# === 启动入口 ===
if __name__ == "__main__":
    # 监听所有IP的8000端口
    uvicorn.run(app, host="0.0.0.0", port=8000)