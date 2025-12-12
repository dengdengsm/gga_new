import json
import os
import shutil
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
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
        
        # 确保 history.json 存在
        hist_file = os.path.join(p_dir, "history.json")
        if not os.path.exists(hist_file):
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump([], f)
                
        # 【新增】确保 files.json 存在 (用于持久化文件列表)
        files_record = os.path.join(p_dir, "files.json")
        if not os.path.exists(files_record):
            with open(files_record, "w", encoding="utf-8") as f:
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

    # 【新增】文件记录操作辅助函数
    def get_file_records(self):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        try:
            if os.path.exists(record_path):
                with open(record_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
        except:
            return []

    def add_file_record(self, record: dict):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        records.insert(0, record) # 最新在前
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def update_file_status(self, file_id: str, status: str, message: str):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        updated = False
        for rec in records:
            if rec.get("id") == file_id:
                rec["status"] = status
                rec["message"] = message
                updated = True
                break
        if updated:
            with open(record_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

    def remove_file_record(self, file_id: str):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        records = [r for r in records if r.get("id") != file_id]
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

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


# --- 任务状态管理 (内存缓存 + 持久化更新) ---
tasks = {}

def process_upload_background(task_id: str, file_location: str, project_name: str):
    """后台任务：处理文件并构建图谱"""
    time.sleep(2) # 等待主线程响应完成
    
    try:
        tasks[task_id] = {"status": "processing", "message": "正在深度解析内容..."}
        # 【持久化】更新状态为处理中（其实上传时已经是pending，这里可以是processing）
        project_manager.update_file_status(task_id, "processing", "正在深度解析内容...")
        
        print(f"🔄 [Task {task_id}] 开始后台处理: {os.path.basename(file_location)}")
        
        # 执行耗时操作
        rag_engine.build_graph(file_location)
        
        tasks[task_id] = {"status": "success", "message": "图谱构建完成"}
        # 【持久化】更新状态为成功
        project_manager.update_file_status(task_id, "success", "图谱构建完成")
        print(f"✅ [Task {task_id}] 处理完成")
        
    except Exception as e:
        tasks[task_id] = {"status": "error", "message": str(e)}
        # 【持久化】更新状态为失败
        project_manager.update_file_status(task_id, "error", str(e))
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

# === 【新增】文件列表接口 ===
@app.get("/api/files")
async def list_files():
    """获取当前项目已上传的文件列表"""
    return project_manager.get_file_records()

@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    """删除文件记录 (物理删除可选，这里先做逻辑删除)"""
    project_manager.remove_file_record(file_id)
    return {"status": "success"}

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

# === 文件上传接口 (持久化版) ===

@app.post("/api/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    异步上传 + 线程池写入 + 持久化记录
    """
    try:
        upload_dir = os.path.join(project_manager.get_project_dir(), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_location = os.path.join(upload_dir, file.filename)
        
        # 分块写入磁盘
        with open(file_location, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                await run_in_threadpool(f.write, chunk)
            
        task_id = str(uuid.uuid4())
        print(f"📂 [Upload] 收到文件: {file.filename}, 分配任务 ID: {task_id}")
        
        # 1. 内存任务记录 (短期轮询)
        tasks[task_id] = {
            "status": "pending",
            "message": "已加入处理队列...",
            "filename": file.filename,
            "timestamp": time.time()
        }
        
        # 2. 【持久化】写入 files.json (长期存储)
        file_record = {
            "id": task_id,
            "filename": file.filename,
            "status": "pending",
            "message": "已加入处理队列...",
            "timestamp": datetime.now().isoformat(),
            "size": 0 # 这里如果能获取大小更好，暂时置0
        }
        project_manager.add_file_record(file_record)
        
        # 3. 触发后台任务
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