import json
import os
import shutil
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Callable
import glob
import re
from datetime import datetime
import time
import uuid
import logging

# 关闭 httpx (OpenAI/DeepSeek 底层通讯库) 的 INFO 日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# 如果还有其他干扰，可以尝试关闭这些常见库的日志
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
# --- 引入你的核心模块 ---
from router import RouterAgent
from graphrag import LightGraphRAG
from codez_gen import CodeGenAgent
from code_revise import CodeReviseAgent
from utils import quick_validate_mermaid, preprocess_multi_files
from document_reader import DocumentAnalyzer
from project_manager import ProjectManager
from git_loader import GitHubLoader
from style_agent import StyleAgent

# --- 配置 ---
PROJECTS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.projects"))
DEFAULT_PROJECT = "default"

# --- 全局项目管理器 ---

project_manager = ProjectManager(DEFAULT_PROJECT,PROJECTS_ROOT)

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
    router_agent = RouterAgent(model_name="deepseek-chat", learn_mode=False)
    code_gen_agent = CodeGenAgent(model_name="deepseek-chat")
    code_revise_agent = CodeReviseAgent(
        mistake_file_path="./knowledge/experience/mistakes.json", 
        model_name="deepseek-chat"
    )
    doc_analyzer = DocumentAnalyzer() 
    style_agent = StyleAgent(model_name="deepseek-chat")
    print("✅ [Backend] 引擎加载完毕！")
except Exception as e:
    print(f"❌ [Backend] 引擎加载失败: {e}")


# --- 任务状态管理 ---
tasks = {}

def process_upload_background(task_id: str, file_location: str, project_name: str):
    """后台任务：处理文件并构建图谱"""
    time.sleep(2) 
    
    try:
        tasks[task_id] = {"status": "processing", "message": "文件已接收..."}
        project_manager.update_file_status(task_id, "uploaded", "等待生成时处理")
        
        print(f"🔄 [Task {task_id}] 文件已就绪: {os.path.basename(file_location)}")
        
        # 注意：不再此处自动构建图谱，而是推迟到生成阶段统一处理多文件
        
        tasks[task_id] = {"status": "success", "message": "文件就绪"}
        project_manager.update_file_status(task_id, "success", "文件就绪")
        
    except Exception as e:
        tasks[task_id] = {"status": "error", "message": str(e)}
        project_manager.update_file_status(task_id, "error", str(e))
        print(f"❌ [Task {task_id}] 处理失败: {e}")


# --- 2. Request Models ---

class GenerateRequest(BaseModel):
    text: str
    diagramType: str = "auto"
    aiConfig: Optional[Dict[str, Any]] = None
    useGraph: bool = True 
    useFileContext: bool = True # 是否使用文件上下文
    useHistory:bool = False
    useMistakes:bool = False
    richness:float = 0.5

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

class OptimizeRequest(BaseModel):
    code: str
    instruction: str
    aiConfig: Optional[Dict[str, Any]] = None
    accessPassword: Optional[str] = None
    selectedModel: Optional[str] = None

class GitHubAnalysisRequest(BaseModel):
    repoUrl: str
    diagramType: str = "auto"
    aiConfig: Optional[Dict[str, Any]] = None
    richness: float = 0.5

class StyleGenRequest(BaseModel):
    description: str


# ==========================================
# === 核心逻辑封装 (Refactored Helpers) ===
# ==========================================

def run_code_revision_loop(
    initial_code: str, 
    revise_agent: CodeReviseAgent,
    user_query: Optional[str] = None,
    router_agent_instance: Optional[RouterAgent] = None,
    use_mistakes: bool = False,
    status_callback: Optional[Callable[[str], None]] = None
):
    """
    通用代码修复循环：校验 -> 失败 -> 记录 -> 修复 (最多3次)
    :param initial_code: 初始生成的代码
    :param revise_agent: 修复代理实例
    :param user_query: 用户原始查询（用于成功后学习）
    :param router_agent_instance: 路由代理实例（用于成功后学习）
    :param use_mistakes: 是否使用错误本辅助修复
    :param status_callback: 可选的回调函数，用于更新外部状态（如 GitHub 任务消息）
    :return: (final_code, final_error)
    """
    current_code = initial_code
    max_retries = 3 
    attempt_history = []
    validation = {'valid': False, 'error': 'Not started'}

    print(f"   -> 正在校验代码语法 (最大重试 {max_retries} 次)...")

    for i in range(max_retries + 1):
        print(f"   🔍 [第 {i+1} 次校验] ...")
        validation = quick_validate_mermaid(current_code)
        
        if validation['valid']:
            print("   ✅ 校验通过")
            
            # 1. 记录经验 (如果是在修复过程中成功的)
            if i > 0 and len(attempt_history) > 0 and revise_agent:
                try:
                    last_fail = attempt_history[-1]
                    revise_agent.record_mistake(last_fail["code"], last_fail["error"], current_code)
                    print("   📚 错误修复经验已录入")
                except Exception as e:
                    print(f"   ⚠️ 经验录入失败: {e}")
            
            # 2. Router 学习 (如果提供了 agent 和 query)
            try: 
                if router_agent_instance and user_query: 
                    router_agent_instance.learn_from_success(user_query, current_code)
            except: pass
            
            break 
        
        else:
            error_msg = validation['error']
            print(f"   ❌ 校验失败: {error_msg[:50]}...")
            
            if i == max_retries:
                print("   ❌ 达到最大重试次数，放弃自动修复")
                break
            
            attempt_history.append({"code": current_code, "error": error_msg})
            
            if revise_agent:
                msg = f"正在自动修复语法错误 ({i+1}/{max_retries})..."
                print(f"   🔧 {msg}")
                if status_callback:
                    status_callback(msg)

                current_code = revise_agent.revise_code(
                    current_code, 
                    error_message=error_msg, 
                    previous_attempts=attempt_history,
                    use_mistake_book=use_mistakes
                )
            else:
                print("   ⚠️ CodeReviseAgent 未加载，无法进行修复")
                break
    
    final_error = validation['error'] if not validation['valid'] else None
    return current_code, final_error

# ==========================================
# === 简单的文件状态管理 (基于项目目录) ===
# ==========================================


def build_file_context(user_query: str, use_graph: bool, use_file: bool) -> str:
    """
    构建上下文：基于 ProjectManager 的统一状态管理
    """
    context = ""
    
    # 1. 获取项目路径和文件记录
    project_dir = project_manager.get_project_dir() 
    upload_dir = os.path.join(project_dir, "uploads")
    
    # 获取“唯一真理”：ProjectManager 里的记录
    file_records = project_manager.get_file_records() 
    # 建立 filename -> record 的映射，方便后续查找
    record_map = {rec['filename']: rec for rec in file_records}
    
    # 扫描实际存在的物理文件
    _, text_files, blob_files = preprocess_multi_files(upload_dir, project_dir)
    all_current_files = text_files + blob_files
    
    if use_file and len(all_current_files) > 0:
        if use_graph:
            print(f"   -> 🔵 Mode: GraphRAG (Project: {project_manager.current_project})")
            
            # 3. 找出需要更新到图谱的文件
            files_to_update = []
            
            for fpath in all_current_files:
                fname = os.path.basename(fpath)
                current_mtime = os.path.getmtime(fpath) # 物理文件的最后修改时间
                
                record = record_map.get(fname)
                
                # 判断逻辑：
                # 1. 如果 ProjectManager 里没记录（可能是手动复制进去的），暂不处理或强制更新
                # 2. 如果记录里没有 'last_graph_sync' 字段（说明上传了但从未构建过图谱）-> 需要更新
                # 3. 如果物理文件比记录的时间新（说明文件被修改过）-> 需要更新
                
                needs_update = False
                if not record:
                    # 这种情况理论上不应发生，除非手动操作了文件夹
                    print(f"   ⚠️ Warning: File {fname} found on disk but not in ProjectManager.")
                    continue 
                
                last_sync = record.get("last_graph_sync", 0) # 默认为 0
                
                if current_mtime > last_sync:
                    needs_update = True
                
                if needs_update:
                    files_to_update.append((fpath, record))

            # 4. 如果有变动，执行增量构建
            if files_to_update:
                print(f"   -> 发现 {len(files_to_update)} 个文件需要同步到图谱...")
                graph_input_path = os.path.join(upload_dir, "graph_full_context.md")
                new_content_buffer = ""
                
                for fpath, record in files_to_update:
                    fname = os.path.basename(fpath)
                    try:
                        # --- 读取内容 ---
                        if fpath in text_files:
                            with open(fpath, 'r', encoding='utf-8') as f:
                                content = f.read()
                            new_content_buffer += f"\n\n### File: {fname}\n{content}\n"
                        else:
                            blob_desc = doc_analyzer.analyze(
                                fpath, 
                                prompt="请详细描述该文件的内容，以便构建准确的知识图谱。", 
                                max_token_limit=2400
                            )
                            new_content_buffer += f"\n\n### File: {fname}\nContent Description:\n{blob_desc}\n"
                        
                        # --- 关键修改：更新 ProjectManager 记录 ---
                        # 记录当前时间戳，并标记状态为 "indexed" (已索引)
                        project_manager.update_file_info(
                            record["id"], 
                            {
                                "last_graph_sync": os.path.getmtime(fpath),
                                "status": "indexed", # 或者保持 "success"
                                "message": "已同步至知识库"
                            }
                        )
                        
                    except Exception as e:
                        print(f"      ❌ 处理失败 {fname}: {e}")
                        project_manager.update_file_info(
                            record["id"], 
                            {"status": "error", "message": f"图谱构建失败: {str(e)}"}
                        )

                # 写入 Graph md 并触发构建
                if new_content_buffer:
                    with open(graph_input_path, "a", encoding="utf-8") as f:
                        f.write(new_content_buffer)
                    
                    rag_engine.build_graph(graph_input_path)
            else:
                print("   -> ✨ 图谱已是最新，无需重建。")

            # 搜索图谱
            print("   -> Searching Knowledge Graph...")
            context = rag_engine.search(user_query, top_k=3)

        # --- 分支 B: 直接多文件模式 (No Graph) ---
        else:
            print("   -> 🟠 Mode: Direct Analysis (All Files)")
            
            all_targets = text_files + blob_files
            count = len(all_targets)
            token_budget = 1200
            limit_per_file = max(100, token_budget // count) if count > 0 else 1200
            
            file_contexts = []
            print(f"   -> Processing {count} files (Limit: ~{limit_per_file} tokens/file)...")
            
            for fpath in all_targets:
                try:
                    analysis = doc_analyzer.analyze(
                        fpath, 
                        prompt=f"Briefly explain this file's relevance to: {user_query}", 
                        max_token_limit=limit_per_file
                    )
                    print("文档提取成功......")
                    file_contexts.append(f"### File: {os.path.basename(fpath)}\nSummary:\n{analysis}\n")
                except Exception as e:
                    print(f"Error analyzing {fpath}: {e}")
            
            context = "\n".join(file_contexts)
    
    else:
        print("   -> ⚪ Mode: Pure Text (No File Context)")
        context = "" 

    return context

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
    return project_manager.get_file_records()

@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    project_manager.remove_file_record(file_id)
    return {"status": "success"}

# === 图谱数据接口 ===
@app.get("/api/graph/data")
async def get_graph_data():
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

# === 文件上传接口 ===

@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    autoBuild: bool = Form(True) 
):
    try:
        upload_dir = os.path.join(project_manager.get_project_dir(), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_location = os.path.join(upload_dir, file.filename)
        
        with open(file_location, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                await run_in_threadpool(f.write, chunk)
            
        task_id = str(uuid.uuid4())
        print(f"📂 [Upload] 收到文件: {file.filename}, ID: {task_id}, AutoBuild: {autoBuild}")
        
        initial_status = "pending" if autoBuild else "uploaded"
        initial_msg = "文件等待处理..." if autoBuild else "文件已保存 (待分析)"
        
        tasks[task_id] = {
            "status": initial_status,
            "message": initial_msg,
            "filename": file.filename,
            "timestamp": time.time(),
            "location": file_location 
        }
        
        file_record = {
            "id": task_id,
            "filename": file.filename,
            "status": initial_status,
            "message": initial_msg,
            "timestamp": datetime.now().isoformat(),
            "location": file_location, 
            "size": 0 
        }
        project_manager.add_file_record(file_record)
        
        if autoBuild:
            background_tasks.add_task(
                process_upload_background, 
                task_id, 
                file_location, 
                project_manager.current_project
            )
        
        return {
            "status": "success", 
            "message": "文件上传成功" + ("，已进入处理队列" if autoBuild else "，等待使用"),
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

# === 核心生成接口 (增强版：支持多文件分路处理) ===
@app.post("/api/generate-mermaid")
async def generate_mermaid(request: GenerateRequest):
    user_query = request.text
    print(f"\n⚡ [Generate] 收到请求: {user_query[:50]}... | Graph: {request.useGraph} | File: {request.useFileContext}")

    try:
        # 1. 调用封装好的上下文构建函数
        context = build_file_context(user_query, request.useGraph, request.useFileContext)

        # 2. Router 调度中心
        print("   -> Router 正在制定策略...")
        
        if request.diagramType == "auto":
            route_res = router_agent.route_and_analyze(user_content=context, user_target=user_query, use_experience=request.useHistory)
        else:
            print(f"   -> 用户强制指定类型: {request.diagramType}")
            route_res = router_agent.analyze_specific_mode(
                user_content=context, 
                user_target=user_query, 
                specific_type=request.diagramType,
                use_experience=request.useHistory
            )
            
        prompt_file = route_res.get("target_prompt_file", "flowchart.md")
        logic_analysis = route_res.get("analysis_content", "")
        
        print(f"   -> 目标 Prompt: {prompt_file}")
        
        # 3. 代码生成
        print("   -> 正在生成代码...")
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file, richness=request.richness)
        
        # 4. 调用封装好的循环修复逻辑
        final_code, final_error = run_code_revision_loop(
            initial_code=initial_code,
            revise_agent=code_revise_agent,
            user_query=user_query,
            router_agent_instance=router_agent,
            use_mistakes=request.useMistakes
        )

        return {"mermaidCode": final_code, "error": final_error}

    except Exception as e:
        print(f"🔥 [Generate] 处理异常: {e}")
        import traceback
        traceback.print_exc()
        return {"mermaidCode": "", "error": str(e)}

# === GitHub 分析接口 ===

def process_github_background(task_id: str, repo_url: str, diagram_type: str, richness: float):
    """GitHub 分析的后台任务逻辑"""
    try:
        # 1. 更新状态：克隆中
        tasks[task_id].update({"status": "processing", "message": "正在克隆仓库..."})
        
        project_dir = project_manager.get_project_dir()
        # 源代码存储路径 (与 uploads 隔离)
        loader = GitHubLoader(base_dir=os.path.join(project_dir, "repos"))
        upload_dir = os.path.join(project_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        # 2. 下载代码
        print(f"   -> [Task {task_id}] Cloning {repo_url}...")
        repo_path = loader.clone_repo(repo_url)
        repo_name = os.path.basename(repo_path)
        
        # 3. 分析结构
        tasks[task_id].update({"message": "正在分析文件结构..."})
        files_map = loader.classify_files(repo_path)
        tree_structure = loader.generate_tree_structure(repo_path)
        
        # 4. 深度分析核心代码
        source_files = files_map['source_code']
        # 使用智能筛选
        max_files_to_analyze = 30 
        selected_files = loader.smart_select_files(source_files, max_files=max_files_to_analyze)
        
        analysis_results = []
        count = 0
        ignored_files = set(source_files) - set(selected_files)
        
        print(f"   -> Smart selected {len(selected_files)} files from {len(source_files)} total sources.")
        
        for file_path in selected_files:
            count += 1
            tasks[task_id].update({"message": f"正在深度阅读 ({count}/{len(selected_files)}): {os.path.basename(file_path)}"})
            
            try:
                res = doc_analyzer.analyze_code_file(file_path, project_root=repo_path)
                analysis_results.append(res)
            except Exception as e:
                print(f"      ❌ Skipped {os.path.basename(file_path)}: {e}")
            
        # 5. 组装 Context
        full_context = (
            f"# GitHub Repository Analysis: {repo_name}\n\n"
            f"> Source URL: {repo_url}\n"
            f"> Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"## 1. Directory Structure\n"
            f"```\n{tree_structure}\n```\n\n"
            f"## 2. Core Logic Analysis\n"
            f"{''.join(analysis_results)}\n\n"
            f"## 3. Supplementary Info\n"
            f"Total files scanned: {len(source_files)}. Files fully analyzed: {len(selected_files)}.\n"
        )
        
        # 保存分析结果
        summary_filename = f"{repo_name}.md"
        summary_file_path = os.path.join(upload_dir, summary_filename)
        with open(summary_file_path, "w", encoding="utf-8") as f:
            f.write(full_context)
        print(f"   💾 [Save] Context saved to: {summary_filename}")

        try:
            summary_record = {
                "id": str(uuid.uuid4()),
                "filename": summary_filename, 
                "status": "success",
                "message": "GitHub 智能分析报告",
                "timestamp": datetime.now().isoformat(),
                "location": summary_file_path,
                "size": len(full_context),
                "isGithubAnalysis": True
            }
            project_manager.add_file_record(summary_record)
        except Exception as e:
            print(f"   ⚠️ Failed to register summary file: {e}")

        user_query = f"Analyze the architecture of the GitHub repository '{repo_name}'. Use the Directory Tree to understand the full scope, and the Core File Analysis to understand the specific logic implementation."
        
        # 6. 生成图表
        tasks[task_id].update({"message": "AI 正在构建图表逻辑..."})
        
        if diagram_type == "auto":
            route_res = router_agent.route_and_analyze(user_content=full_context, user_target=user_query)
        else:
            route_res = router_agent.analyze_specific_mode(
                user_content=full_context, 
                user_target=user_query, 
                specific_type=diagram_type
            )
            
        prompt_file = route_res.get("target_prompt_file", "classDiagram.md")
        logic_analysis = route_res.get("analysis_content", "")
        
        tasks[task_id].update({"message": "正在生成 Mermaid 代码..."})
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file, richness=richness)
        
        # 7. Code Revise (使用封装函数，带状态更新回调)
        def update_status(msg):
            tasks[task_id].update({"message": msg})

        final_code, final_error = run_code_revision_loop(
            initial_code=initial_code,
            revise_agent=code_revise_agent,
            user_query=None, # GitHub 任务暂不触发 Router 学习
            status_callback=update_status
        )
        
        # 保存历史记录
        try:
            hist_entry = {
                "id": str(int(time.time() * 1000)),
                "query": f"GitHub Analysis: {repo_name}",
                "code": final_code,
                "diagramType": diagram_type,
                "timestamp": datetime.now().isoformat(),
                "analysisSummary": logic_analysis
            }
            p_dir = project_manager.get_project_dir()
            hist_file = os.path.join(p_dir, "history.json")
            
            current_hist = []
            if os.path.exists(hist_file):
                with open(hist_file, "r", encoding="utf-8") as f:
                    try: current_hist = json.load(f)
                    except: current_hist = []
            
            current_hist.insert(0, hist_entry)
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(current_hist, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"   ⚠️ Failed to save history: {e}")

        # 8. 任务完成
        print(f"✅ [Task {task_id}] GitHub 分析完成")
        tasks[task_id] = {
            "status": "success",
            "message": "分析完成",
            "result": {  
                "mermaidCode": final_code,
                "error": final_error,
                "analysisSummary": logic_analysis
            }
        }

    except Exception as e:
        print(f"❌ [Task {task_id}] Failed: {e}")
        tasks[task_id] = {"status": "error", "message": str(e)}

@app.post("/api/upload-github")
async def analyze_github(request: GitHubAnalysisRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    print(f"\n⚡ [GitHub] 收到请求，创建后台任务 ID: {task_id}")
    tasks[task_id] = {
        "status": "pending",
        "message": "任务初始化...",
        "type": "github",
        "repo": request.repoUrl
    }
    background_tasks.add_task(
        process_github_background,
        task_id,
        request.repoUrl,
        request.diagramType,
        request.richness
    )
    return {"status": "success", "taskId": task_id, "message": "后台分析已启动"}

@app.post("/api/optimize-mermaid")
async def optimize_mermaid(request: OptimizeRequest):
    print(f"\n⚡ [Optimize] 收到优化请求: {request.instruction[:50]}...")
    
    try:
        # 第一步：执行优化
        current_code = code_revise_agent.optimize_code(request.code, request.instruction)
        
        # 第二步：调用封装的校验+修复逻辑
        final_code, final_error = run_code_revision_loop(
            initial_code=current_code,
            revise_agent=code_revise_agent,
            use_mistakes=False # 优化通常不查错误本，而是基于指令
        )
        
        return {
            "optimizedCode": final_code, 
            "error": final_error
        }

    except Exception as e:
        print(f"🔥 [Optimize] 处理异常: {e}")
        return {"optimizedCode": request.code, "error": str(e)}

@app.post("/api/fix-mermaid")
async def fix_mermaid(request: FixRequest):
    # 调用封装的循环修复逻辑
    final_code, final_error = run_code_revision_loop(
        initial_code=request.mermaidCode,
        revise_agent=code_revise_agent,
        use_mistakes=True # 纯修复模式建议开启错误本学习
    )
    return {"fixedCode": final_code, "error": final_error}

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

@app.post("/api/style/generate")
async def generate_graph_style(req: StyleGenRequest):
    print(f"🎨 [Style] 收到样式生成请求: {req.description}")
    try:
        # 调用 StyleAgent
        result = style_agent.generate_style(req.description)
        
        # 检查是否有错误
        if result.get("error"):
            return {"status": "error", "message": result["error"]}
            
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"🔥 [Style] 生成失败: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)