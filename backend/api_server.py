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
from utils import quick_validate_mermaid, preprocess_multi_files
from document_reader import DocumentAnalyzer
from project_manager import ProjectManager

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
    use_graph = request.useGraph
    diagram_type = request.diagramType
    use_file = request.useFileContext
    
    print(f"\n⚡ [Generate] 收到请求: {user_query[:50]}... | Graph: {use_graph} | File: {use_file}")

    try:
        context = ""
        project_dir = project_manager.get_project_dir()
        upload_dir = os.path.join(project_dir, "uploads")
        
        # 1. 预处理文件：自动分类与合并
        # merged_md: 文本类文件的合并内容路径 (用于 GraphRAG)
        # text_files: 文本文件列表 (用于 No-Graph 直接读取)
        # blob_files: 非文本文件列表 (用于 DocumentAnalyzer)
        merged_md, text_files, blob_files = preprocess_multi_files(upload_dir, project_dir)
        total_files_count = len(text_files) + len(blob_files)

        if use_file and total_files_count > 0:
            
            # --- 分支 A: 知识图谱模式 (GraphRAG) ---
            if use_graph:
                print("   -> 🔵 Mode: GraphRAG (Full Context Integration)")
                
                # 1. 准备图谱构建的完整语料 (文本文件 + 非文本文件的AI描述)
                full_corpus_content = ""
                
                # A. 读取现有的合并文本 (来自 text_files)
                if merged_md and os.path.exists(merged_md):
                    with open(merged_md, "r", encoding="utf-8") as f:
                        full_corpus_content += f.read() + "\n\n"
                
                # B. 处理非文本文件 (Blob) -> 转为文本描述
                # 逻辑要求：每个非文本文件生成 1200 token 的详细说明
                if blob_files:
                    print(f"   -> [GraphPrep] 正在将 {len(blob_files)} 个非文本文件转化为图谱语料...")
                    for bf in blob_files:
                        try:
                            # 视作文本文件处理：生成长描述
                            blob_desc = doc_analyzer.analyze(
                                bf, 
                                prompt="请详细描述该文件的内容，以便构建准确的知识图谱。", 
                                max_token_limit=1200
                            )
                            full_corpus_content += f"### File: {os.path.basename(bf)}\nContent Description:\n{blob_desc}\n\n"
                        except Exception as e:
                            print(f"   ❌ Error processing blob {bf} for graph: {e}")
                
                # C. 保存为临时构建文件并构建图谱
                # 将所有内容整合后，再次直接调用 Build_graph
                graph_input_path = os.path.join(upload_dir, "graph_full_context.md")
                with open(graph_input_path, "w", encoding="utf-8") as f:
                    f.write(full_corpus_content)
                
                try:
                    print(f"   -> Building Graph from integrated corpus: {os.path.basename(graph_input_path)}")
                    rag_engine.build_graph(graph_input_path)
                    print("   ✅ Graph Build/Update Complete")
                except Exception as build_e:
                    print(f"   ❌ Graph Build Failed: {build_e}")
                
                # D. 搜索图谱获取上下文 (Router 使用的内容)
                print("   -> Searching Knowledge Graph...")
                context = rag_engine.search(user_query, top_k=3)

            # --- 分支 B: 直接多文件模式 (No Graph) ---
            else:
                print("   -> 🟠 Mode: Direct Analysis (All Files)")
                
                # 逻辑要求：调用 document-reader 处理所有文件 (含文本文件)
                # 约束：总字数 (Total Token Budget) 1200
                
                all_targets = text_files + blob_files
                count = len(all_targets)
                token_budget = 1200
                # 动态分配每个文件的配额，最少给100，防止文件过多时分配为0
                limit_per_file = max(100, token_budget // count) if count > 0 else 1200
                
                file_contexts = []
                print(f"   -> Processing {count} files (Limit: ~{limit_per_file} tokens/file)...")
                
                for fpath in all_targets:
                    try:
                        # 统一使用 analyzer 生成摘要，文本文件也能处理
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
            context = "" # 仅使用用户 Query

        # 2. Router 调度中心
        print("   -> Router 正在制定策略...")
        
        if diagram_type == "auto":
            # 自动选型模式
            route_res = router_agent.route_and_analyze(user_content=context, user_target=user_query)
        else:
            # 定向生成模式
            print(f"   -> 用户强制指定类型: {diagram_type}")
            route_res = router_agent.analyze_specific_mode(
                user_content=context, 
                user_target=user_query, 
                specific_type=diagram_type
            )
            
        prompt_file = route_res.get("target_prompt_file", "flowchart.md")
        logic_analysis = route_res.get("analysis_content", "")
        
        print(f"   -> 目标 Prompt: {prompt_file}")
        
        # 3. 代码生成
        print("   -> 正在生成代码...")
        initial_code = code_gen_agent.generate_code(logic_analysis, prompt_file=prompt_file,richness=request.richness)
        
        # 4. 循环修复逻辑 (保持不变)
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
                
                if i > 0 and len(attempt_history) > 0 and code_revise_agent:
                    try:
                        last_fail = attempt_history[-1]
                        code_revise_agent.record_mistake(last_fail["code"], last_fail["error"], current_code)
                        print("   📚 错误修复经验已录入")
                    except Exception as e:
                        print(f"   ⚠️ 经验录入失败: {e}")
                
                try: 
                    if router_agent: router_agent.learn_from_success(user_query, current_code)
                except: pass
                
                break 
            
            else:
                error_msg = validation['error']
                print(f"   ❌ 校验失败: {error_msg[:50]}...")
                
                if i == max_retries:
                    break
                
                attempt_history.append({"code": current_code, "error": error_msg})
                
                if code_revise_agent:
                    print(f"   🔧 启动自动修复 (第 {i+1} 次尝试)...")
                    current_code = code_revise_agent.revise_code(
                        current_code, 
                        error_message=error_msg, 
                        previous_attempts=attempt_history
                    )
                else:
                    print("   ⚠️ CodeReviseAgent 未加载，无法进行修复")
                    break
        
        final_code = current_code
        final_error = validation['error'] if not validation['valid'] else None

        return {"mermaidCode": final_code, "error": final_error}

    except Exception as e:
        print(f"🔥 [Generate] 处理异常: {e}")
        import traceback
        traceback.print_exc()
        return {"mermaidCode": "", "error": str(e)}

@app.post("/api/optimize-mermaid")
async def optimize_mermaid(request: OptimizeRequest):
    print(f"\n⚡ [Optimize] 收到优化请求: {request.instruction[:50]}...")
    
    try:
        # 2. 第一步：执行优化 (不查 RAG，纯 LLM 修改)
        # 这对应你要求的“调用llm进行优化，这个过程不检索任何rag”
        current_code = code_revise_agent.optimize_code(request.code, request.instruction)
        
        # 3. 第二步：进入标准的“校验+自动修复”循环 (复用 generate_mermaid 的逻辑)
        # 这对应你要求的“再用和generate_mermaid同一套的revise逻辑”
        
        max_retries = 3
        attempt_history = []
        validation = {'valid': False, 'error': 'Not started'}
        
        print(f"   -> 正在校验优化后的代码 (最大重试 {max_retries} 次)...")

        for i in range(max_retries + 1):
            validation = quick_validate_mermaid(current_code)
            
            if validation['valid']:
                print(f"   ✅ [第 {i+1} 次] 校验通过")
                # 如果是在修复过程中成功的，记录经验
                if i > 0 and len(attempt_history) > 0:
                    try:
                        last_fail = attempt_history[-1]
                        code_revise_agent.record_mistake(last_fail["code"], last_fail["error"], current_code)
                    except: pass
                break
            else:
                error_msg = validation['error']
                print(f"   ❌ [第 {i+1} 次] 校验失败: {error_msg[:50]}...")
                
                if i == max_retries:
                    break
                
                attempt_history.append({"code": current_code, "error": error_msg})
                
                # 调用带 RAG 的修复功能
                print(f"   🔧 启动自动修复...")
                current_code = code_revise_agent.revise_code(
                    current_code, 
                    error_message=error_msg, 
                    previous_attempts=attempt_history
                )

        final_error = validation['error'] if not validation['valid'] else None
        
        return {
            "optimizedCode": current_code, 
            "error": final_error
        }

    except Exception as e:
        print(f"🔥 [Optimize] 处理异常: {e}")
        return {"optimizedCode": request.code, "error": str(e)}

@app.post("/api/fix-mermaid")
async def fix_mermaid(request: FixRequest):
    
     # === 循环修复逻辑开始 ===
        current_code = request.mermaidCode
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)