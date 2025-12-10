import json
import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# --- 引入你的核心模块 ---
from router import RouterAgent
from graphrag import LightGraphRAG
from codez_gen import CodeGenAgent
from code_revise import CodeReviseAgent
from utils import quick_validate_mermaid

# --- 初始化 FastAPI ---
app = FastAPI(title="Smart Mermaid Backend (Sync Version)")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. 初始化 Agents (全局单例) ---
print("🚀 [Backend] 正在启动后端引擎，加载 Agents...")

os.makedirs("./.local_graph_db", exist_ok=True)
os.makedirs("./.uploaded_docs", exist_ok=True)

# 初始化核心对象
try:
    rag_engine = LightGraphRAG(persist_dir="./.local_graph_db")
    
    # 路由智能体
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

# --- 2. 定义请求体结构 ---

class GenerateRequest(BaseModel):
    text: str
    diagramType: str = "auto"
    # 保留字段定义以防前端报错，但实际上我们现在依赖全局配置
    aiConfig: Optional[Dict[str, Any]] = None

class FixRequest(BaseModel):
    mermaidCode: str
    errorMessage: str

class PasswordRequest(BaseModel):
    password: str

# 新增：配置更新请求体
class ConfigUpdateRequest(BaseModel):
    apiKey: str
    apiUrl: str
    modelName: str

# --- 3. 业务接口定义 ---

# === 接口 X (新增): 系统配置热更新 ===
@app.post("/api/system/config")
async def update_system_config(config: ConfigUpdateRequest):
    """
    接收前端的 AI 配置，热更新所有 Agent 的底层 LLM
    """
    print(f"🔄 [System] 收到配置更新请求: {config.modelName} @ {config.apiUrl}")
    
    try:
        # 将 Pydantic 对象转为字典
        config_dict = config.dict()
        
        # 依次通知所有 Agent 更新
        # 注意：这里调用的是我们在 step 3,4,5 中新增的 reload_llm_config 方法
        if 'router_agent' in globals():
            router_agent.reload_llm_config(config_dict)
            
        if 'code_gen_agent' in globals():
            code_gen_agent.reload_llm_config(config_dict)
            
        if 'code_revise_agent' in globals():
            code_revise_agent.reload_llm_config(config_dict)
            
        return {"status": "success", "message": "AI配置已热更新"}
    except Exception as e:
        print(f"❌ [System] 配置更新失败: {e}")
        return {"status": "error", "message": str(e)}

# === 接口 A: 文件上传 ===
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_location = f"./.uploaded_docs/{file.filename}"
        with open(file_location, "wb+") as file_object:
            file_object.write(file.file.read())
        print(f"📂 [Upload] 收到文件: {file.filename}，开始构建图谱...")
        rag_engine.build_graph(file_location)
        print(f"✅ [Upload] 图谱构建完成")
        return {"status": "success", "message": f"图谱构建成功: {file.filename}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === 接口 B: 核心生成 ===
@app.post("/api/generate-mermaid")
async def generate_mermaid(request: GenerateRequest):
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
        
        # 3. 生成代码
        print("   -> 正在生成代码...")
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file)
        
        # 4. 后端自动校验
        print("   -> 正在校验代码语法...")
        validation = quick_validate_mermaid(initial_code)
        
        final_code = initial_code
        
        if not validation['valid']:
            error_msg = validation['error']
            print(f"   ❌ 校验失败: {error_msg[:50]}... 启动自动修复")
            attempt_history = [{"code": initial_code, "error": error_msg}]
            fixed_code = code_revise_agent.revise_code(
                initial_code, 
                error_message=error_msg, 
                previous_attempts=attempt_history
            )
            final_code = fixed_code
            print("   ✅ 自动修复完成")
            try:
                code_revise_agent.record_mistake(initial_code, error_msg, final_code)
            except Exception as e:
                print(f"   ⚠️ 错题记录失败: {e}")
        else:
            print("   ✅ 校验通过")
            try:
                router_agent.learn_from_success(user_query, final_code)
            except: pass

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

# === 接口 C: 手动修复 ===
@app.post("/api/fix-mermaid")
async def fix_mermaid(request: FixRequest):
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
        return {
            "fixedCode": request.mermaidCode,
            "error": str(e)
        }

# === 接口 D: 辅助接口 ===
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)