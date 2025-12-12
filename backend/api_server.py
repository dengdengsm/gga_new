import json
import os
import shutil
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import glob
import re
from datetime import datetime
import time
import uuid

# --- 引入你的核心模块 ---
from router import RouterAgent
from graphrag import LightGraphRAG
from codez_gen import CodeGenAgent
from code_revise import CodeReviseAgent
from utils import quick_validate_mermaid

# --- 配置 ---
PROJECTS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.projects"))
DEFAULT_PROJECT = "default"

# --- 全局项目管理器 ---
class ProjectManager:
    def __init__(self):
        self.current_project = DEFAULT_PROJECT
        self.ensure_project_exists(DEFAULT_PROJECT)
    
    def get_project_dir(self, project_name: str = None):
        if project_name is None:
            project_name = self.current_project
        return os.path.join(PROJECTS_ROOT, project_name)

    def ensure_project_exists(self, project_name: str):
        p_dir = os.path.join(PROJECTS_ROOT, project_name)
        os.makedirs(os.path.join(p_dir, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(p_dir, "graph_db"), exist_ok=True)
        
        hist_file = os.path.join(p_dir, "history.json")
        if not os.path.exists(hist_file):
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump([], f)
        return p_dir

    def list_projects(self):
        if not os.path.exists(PROJECTS_ROOT):
            return []
        return [d for d in os.listdir(PROJECTS_ROOT) if os.path.isdir(os.path.join(PROJECTS_ROOT, d))]

    def switch_project(self, project_name: str):
        if project_name not in self.list_projects():
            raise ValueError(f"Project {project_name} does not exist")
        self.current_project = project_name
        return self.get_project_dir(project_name)

project_manager = ProjectManager()

# --- 初始化 FastAPI ---
app = FastAPI(title="Smart Mermaid Backend (Project Managed)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. 初始化 Agents ---
print("🚀 [Backend] 正在启动后端引擎，加载 Agents...")
default_graph_db = os.path.join(project_manager.get_project_dir(DEFAULT_PROJECT), "graph_db")

try:
    rag_engine = LightGraphRAG(persist_dir=default_graph_db)
    router_agent = RouterAgent(model_name="deepseek-chat", learn_mode=True)
    code_gen_agent = CodeGenAgent(model_name="deepseek-chat")
    code_revise_agent = CodeReviseAgent(
        mistake_file_path="./knowledge/experience/mistakes.json", 
        model_name="deepseek-chat"
    )
    print("✅ [Backend] 引擎加载完毕！")
except Exception as e:
    print(f"❌ [Backend] 引擎加载失败: {e}")


# --- 任务状态管理 ---
tasks = {}

def process_upload_background(task_id: str, file_location: str, project_name: str):
    """后台任务：处理文件并构建图谱"""
    # 【关键修改】先睡 1 秒，确保主线程已经把 HTTP Response 发送给前端了
    # 避免抢占 CPU 导致 socket hang up
    time.sleep(1)
    
    try:
        tasks[task_id] = {"status": "processing", "message": "正在深度解析内容..."}
        print(f"🔄 [Task {task_id}] 开始后台处理: {os.path.basename(file_location)}")
        
        # 执行耗时操作
        rag_engine.build_graph(file_location)
        
        tasks[task_id] = {"status": "success", "message": "图谱构建完成"}
        print(f"✅ [Task {task_id}] 处理完成")
    except Exception as e:
        tasks[task_id] = {"status": "error", "message": str(e)}
        print(f"❌ [Task {task_id}] 处理失败: {e}")


# --- 2. Request Models ---

class GenerateRequest(BaseModel):
    text: str
    diagramType: str = "auto"
    aiConfig: Optional[Dict[str, Any]] = None

class FixRequest(BaseModel):
    mermaidCode: str
    errorMessage: str

class PasswordRequest(BaseModel):
    password: str

class ConfigUpdateRequest(BaseModel):
    apiKey: str
    apiUrl: str
    modelName: str

class ProjectCreateRequest(BaseModel):
    name: str

class ProjectSwitchRequest(BaseModel):
    name: str

class HistoryEntry(BaseModel):
    id: Optional[str] = None
    query: str
    code: str
    diagramType: str = "auto"
    timestamp: Optional[str] = None

# --- 3. Routes ---

# === 项目管理接口 ===

@app.get("/api/projects")
async def list_projects():
    return {
        "projects": project_manager.list_projects(), 
        "current": project_manager.current_project
    }

@app.post("/api/projects")
async def create_project(req: ProjectCreateRequest):
    if not re.match(r'^[a-zA-Z0-9_-]+$', req.name):
        return {"status": "error", "message": "项目名称只能包含字母、数字、下划线和连字符"}
    
    if req.name in project_manager.list_projects():
        return {"status": "error", "message": "项目已存在"}
    
    project_manager.ensure_project_exists(req.name)
    return {"status": "success", "message": f"项目 {req.name} 已创建"}

@app.post("/api/projects/switch")
async def switch_project(req: ProjectSwitchRequest):
    try:
        if req.name == project_manager.current_project:
            return {"status": "success", "current": req.name, "message": "Already on this project"}

        new_dir = project_manager.switch_project(req.name)
        print(f"🔄 [Project] 切换至: {req.name}")
        
        new_graph_db = os.path.join(new_dir, "graph_db")
        rag_engine.reload_db(new_graph_db)
        
        return {"status": "success", "current": req.name}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === 历史记录接口 ===

@app.get("/api/history")
async def get_history():
    p_dir = project_manager.get_project_dir()
    hist_file = os.path.join(p_dir, "history.json")
    try:
        if os.path.exists(hist_file):
            with open(hist_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception:
        return []

@app.post("/api/history")
async def add_history(entry: HistoryEntry):
    p_dir = project_manager.get_project_dir()
    hist_file = os.path.join(p_dir, "history.json")
    
    new_item = entry.dict()
    if not new_item.get("id"):
        new_item["id"] = str(int(time.time() * 1000))
    if not new_item.get("timestamp"):
        new_item["timestamp"] = datetime.now().isoformat()
        
    try:
        current_data = []
        if os.path.exists(hist_file):
            with open(hist_file, "r", encoding="utf-8") as f:
                try: current_data = json.load(f)
                except: current_data = []
        
        current_data.insert(0, new_item)
        
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
        return {"status": "success", "entry": new_item}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/history/{entry_id}")
async def delete_history(entry_id: str):
    p_dir = project_manager.get_project_dir()
    hist_file = os.path.join(p_dir, "history.json")
    try:
        if os.path.exists(hist_file):
            with open(hist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            new_data = [item for item in data if item.get("id") != entry_id]
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
@app.delete("/api/history")
async def clear_history():
    p_dir = project_manager.get_project_dir()
    hist_file = os.path.join(p_dir, "history.json")
    try:
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === 系统配置接口 ===
@app.post("/api/system/config")
async def update_system_config(config: ConfigUpdateRequest):
    print(f"🔄 [System] 收到配置更新请求: {config.modelName} @ {config.apiUrl}")
    try:
        config_dict = config.dict()
        if 'router_agent' in globals(): router_agent.reload_llm_config(config_dict)
        if 'code_gen_agent' in globals(): code_gen_agent.reload_llm_config(config_dict)
        if 'code_revise_agent' in globals(): code_revise_agent.reload_llm_config(config_dict)
        return {"status": "success", "message": "AI配置已热更新"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === 文件上传接口 (修复版) ===

# 【关键修改】去掉 async，让它在线程池中运行，防止阻塞事件循环
@app.post("/api/upload")
def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    同步上传接口 (Thread Pool)：
    1. 使用 shutil 高效保存文件
    2. 立即返回任务 ID
    3. 后台延时执行分析
    """
    try:
        upload_dir = os.path.join(project_manager.get_project_dir(), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_location = os.path.join(upload_dir, file.filename)
        
        # 【关键修改】使用 shutil.copyfileobj 代替 await file.read()
        # 这样不会一次性把大文件读入内存，也避免了 async 阻塞
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
            
        task_id = str(uuid.uuid4())
        print(f"📂 [Upload] 收到文件: {file.filename}, 分配任务 ID: {task_id}")
        
        tasks[task_id] = {
            "status": "pending",
            "message": "已加入处理队列...",
            "filename": file.filename,
            "timestamp": time.time()
        }
        
        background_tasks.add_task(
            process_upload_background, 
            task_id, 
            file_location, 
            project_manager.current_project
        )
        
        return {
            "status": "success", 
            "message": "文件上传成功，正在后台分析",
            "taskId": task_id,
            "filename": file.filename
        }
    except Exception as e:
        print(f"🔥 Upload Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return {"status": "error", "message": "任务不存在或已过期"}
    return task

# === 核心生成接口 ===
@app.post("/api/generate-mermaid")
async def generate_mermaid(request: GenerateRequest):
    user_query = request.text
    print(f"\n⚡ [Generate] 收到请求: {user_query[:50]}... (Project: {project_manager.current_project})")

    try:
        print("   -> 正在检索知识库...")
        context = rag_engine.search(user_query, top_k=3)
        
        print("   -> Router 正在制定策略...")
        route_res = router_agent.route_and_analyze(user_content=context, user_target=user_query)
        prompt_file = route_res.get("target_prompt_file", "flowchart.md")
        logic_analysis = route_res.get("analysis_content", "")
        
        print("   -> 正在生成代码...")
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file)
        
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
            try:
                code_revise_agent.record_mistake(initial_code, error_msg, final_code)
            except: pass
        else:
            print("   ✅ 校验通过")
            try: router_agent.learn_from_success(user_query, final_code)
            except: pass

        return {"mermaidCode": final_code, "error": None}

    except Exception as e:
        print(f"🔥 [Generate] 处理异常: {e}")
        return {"mermaidCode": "", "error": str(e)}

@app.post("/api/fix-mermaid")
async def fix_mermaid(request: FixRequest):
    try:
        fixed_code = code_revise_agent.revise_code(
            request.mermaidCode, error_message=request.errorMessage
        )
        return {"fixedCode": fixed_code, "error": None}
    except Exception as e:
        return {"fixedCode": request.mermaidCode, "error": str(e)}

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