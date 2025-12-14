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
from document_reader import DocumentAnalyzer  # 【新增】

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
                
        # 确保 files.json 存在 (用于持久化文件列表)
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

    # 文件记录操作辅助函数
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
    doc_analyzer = DocumentAnalyzer() # 【新增】直接文档分析器
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
        project_manager.update_file_status(task_id, "processing", "正在深度解析内容...")
        
        print(f"🔄 [Task {task_id}] 开始后台处理: {os.path.basename(file_location)}")
        
        # 执行耗时操作
        rag_engine.build_graph(file_location)
        
        tasks[task_id] = {"status": "success", "message": "图谱构建完成"}
        project_manager.update_file_status(task_id, "success", "图谱构建完成")
        print(f"✅ [Task {task_id}] 处理完成")
        
    except Exception as e:
        tasks[task_id] = {"status": "error", "message": str(e)}
        project_manager.update_file_status(task_id, "error", str(e))
        print(f"❌ [Task {task_id}] 处理失败: {e}")


# --- 2. Request Models ---

class GenerateRequest(BaseModel):
    text: str
    diagramType: str = "auto"
    aiConfig: Optional[Dict[str, Any]] = None
    useGraph: bool = True # 【新增】是否使用知识图谱

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

# === 文件列表接口 ===
@app.get("/api/files")
async def list_files():
    """获取当前项目已上传的文件列表"""
    return project_manager.get_file_records()

@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    """删除文件记录"""
    project_manager.remove_file_record(file_id)
    return {"status": "success"}

# === 图谱数据接口 ===
@app.get("/api/graph/data")
async def get_graph_data():
    """获取当前知识图谱的实时数据 (Nodes, Links)"""
    return rag_engine.get_graph_snapshot()

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

# === 文件上传接口 (持久化版 + AutoBuild控制) ===

@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    autoBuild: bool = Form(True) # 【新增】默认自动构建
):
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
        print(f"📂 [Upload] 收到文件: {file.filename}, ID: {task_id}, AutoBuild: {autoBuild}")
        
        # 状态初始化：如果不自动构建，状态直接为 uploaded
        initial_status = "pending" if autoBuild else "uploaded"
        initial_msg = "已加入处理队列..." if autoBuild else "文件已保存 (待分析)"
        
        # 1. 内存任务记录 (短期轮询)
        tasks[task_id] = {
            "status": initial_status,
            "message": initial_msg,
            "filename": file.filename,
            "timestamp": time.time(),
            "location": file_location # 记录路径方便后续查找
        }
        
        # 2. 【持久化】写入 files.json (长期存储)
        file_record = {
            "id": task_id,
            "filename": file.filename,
            "status": initial_status,
            "message": initial_msg,
            "timestamp": datetime.now().isoformat(),
            "location": file_location, # 新增
            "size": 0 
        }
        project_manager.add_file_record(file_record)
        
        # 3. 触发后台任务 (仅当 autoBuild 为 True)
        if autoBuild:
            background_tasks.add_task(
                process_upload_background, 
                task_id, 
                file_location, 
                project_manager.current_project
            )
        
        return {
            "status": "success", 
            "message": "文件上传成功" + ("，正在后台分析" if autoBuild else "，等待使用"),
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

# === 核心生成接口 (增强版：支持 useGraph) ===
@app.post("/api/generate-mermaid")
async def generate_mermaid(request: GenerateRequest):
    user_query = request.text
    use_graph = request.useGraph
    
    print(f"\n⚡ [Generate] 收到请求: {user_query[:50]}... (Project: {project_manager.current_project}, UseGraph: {use_graph})")

    try:
        context = ""
        
        if use_graph:
            print("   -> 模式: 知识图谱 RAG")
            # 1. Lazy Build: 检查是否有未构建的文件 (status='uploaded')
            # 简单策略：只检查当前项目记录中的第一个 'uploaded' 文件
            records = project_manager.get_file_records()
            target_file = next((r for r in records if r.get("status") == "uploaded"), None)
            
            if target_file:
                print(f"   -> 发现未构建文件: {target_file['filename']}，开始现场构建...")
                file_path = target_file.get("location")
                if not file_path:
                     file_path = os.path.join(project_manager.get_project_dir(), "uploads", target_file['filename'])
                
                if os.path.exists(file_path):
                    # 同步阻塞构建
                    try:
                        project_manager.update_file_status(target_file['id'], "processing", "生成时自动构建中...")
                        rag_engine.build_graph(file_path) 
                        project_manager.update_file_status(target_file['id'], "success", "图谱构建完成")
                        print("   ✅ 现场构建完成")
                    except Exception as build_e:
                        print(f"   ❌ 现场构建失败: {build_e}")
                        project_manager.update_file_status(target_file['id'], "error", str(build_e))
                else:
                    print(f"   ⚠️ 文件不存在: {file_path}")

            # 2. 知识检索
            print("   -> 正在检索知识库...")
            context = rag_engine.search(user_query, top_k=3)
            
        else:
            print("   -> 模式: 直接文档分析 (Document Reader)")
            # 1. 找到最新上传的文件
            records = project_manager.get_file_records()
            if not records:
                print("   -> 没有找到文件，回退到纯文本模式")
                context = ""
            else:
                # 默认取第一个文件
                target_file = records[0]
                file_path = target_file.get("location")
                if not file_path:
                     file_path = os.path.join(project_manager.get_project_dir(), "uploads", target_file['filename'])
                
                if os.path.exists(file_path):
                    print(f"   -> 正在读取文档: {target_file['filename']}")
                    # 全文分析 (不使用 GraphRAG)
                    analysis_result = doc_analyzer.analyze(file_path, prompt=None) 
                    context = f"User Uploaded Document Content Analysis:\n{analysis_result}"
                else:
                    print("   ⚠️ 文件路径无效")
                    context = ""

        # === 公共流程：Router -> Gen -> Revise ===
        
        print("   -> Router 正在制定策略...")
        route_res = router_agent.route_and_analyze(user_content=context, user_target=user_query)
        prompt_file = route_res.get("target_prompt_file", "flowchart.md")
        logic_analysis = route_res.get("analysis_content", "")
        
        print("   -> 正在生成代码...")
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file)
        
        # === 循环修复逻辑开始 ===
        current_code = initial_code
        max_retries = 3  # 最大重试次数
        attempt_history = []
        validation = {'valid': False, 'error': 'Not started'}

        print(f"   -> 正在校验代码语法 (最大重试 {max_retries} 次)...")

        for i in range(max_retries + 1):
            print(f"   🔍 [第 {i+1} 次校验] ...")
            validation = quick_validate_mermaid(current_code)
            
            if validation['valid']:
                print("   ✅ 校验通过")
                
                # 如果经历过修复，记录经验 (Mistake Learning)
                if i > 0 and len(attempt_history) > 0 and code_revise_agent:
                    try:
                        last_fail = attempt_history[-1]
                        code_revise_agent.record_mistake(last_fail["code"], last_fail["error"], current_code)
                        print("   📚 错误修复经验已录入")
                    except Exception as e:
                        print(f"   ⚠️ 经验录入失败: {e}")
                
                # 学习成功经验 (Router Learning)
                try: 
                    if router_agent: router_agent.learn_from_success(user_query, current_code)
                except: pass
                
                break # 成功，跳出循环
            
            else:
                # 校验失败
                error_msg = validation['error']
                print(f"   ❌ 校验失败: {error_msg[:50]}...")
                
                if i == max_retries:
                    print("   ❌ 达到最大重试次数，放弃自动修复")
                    break
                
                # 记录失败历史，供下次修复参考
                attempt_history.append({
                    "code": current_code,
                    "error": error_msg
                })
                
                if code_revise_agent:
                    print(f"   🔧 启动自动修复 (第 {i+1} 次尝试)...")
                    # 关键：传入 previous_attempts 历史记录
                    current_code = code_revise_agent.revise_code(
                        current_code, 
                        error_message=error_msg, 
                        previous_attempts=attempt_history
                    )
                else:
                    print("   ⚠️ CodeReviseAgent 未加载，无法进行修复")
                    break
        
        final_code = current_code
        # 如果最后还是 invalid，保留错误信息传给前端
        final_error = validation['error'] if not validation['valid'] else None

        return {"mermaidCode": final_code, "error": final_error}

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