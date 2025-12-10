import streamlit as st
import os
import re
import time
# --- 引入 Agents 和 GraphRAG ---
from codez_gen import CodeGenAgent
from code_revise import CodeReviseAgent
from router import RouterAgent
from graphrag import LightGraphRAG
from vision import QwenVisionAgent
import utils

# --- 页面配置 ---
st.set_page_config(layout="wide", page_title="GraphRAG Logic Agent (v5.0 - Evolving)", page_icon="🕸️")

# --- 缓存初始化 ---
@st.cache_resource
def init_agents():
    return {
        "graph_rag": LightGraphRAG(persist_dir="./.local_graph_db"),
        # Router 默认开启学习模式 (learn_mode=True)
        "router": RouterAgent(model_name="deepseek-chat", learn_mode=True),
        "code_gen": CodeGenAgent(model_name="deepseek-chat"),
        "code_revise": CodeReviseAgent(
            knowledge_base_dir="./knowledge_base",
            mistake_file_path="./knowledge/experience/mistakes.json",
            model_name="deepseek-chat"
        ),
        "vision": QwenVisionAgent()
    }

agents = init_agents()

# --- Session State 管理 ---
if "graph_built" not in st.session_state:
    try:
        current_node_count = agents["graph_rag"].graph.number_of_nodes()
    except:
        current_node_count = 0
    
    if current_node_count > 0:
        print(f"检测到持久化数据：{current_node_count} 个节点，自动恢复状态。")
        st.session_state.graph_built = True
    else:
        st.session_state.graph_built = False

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None 

# --- 主界面 UI ---

st.title("🕸️ GraphRAG 逻辑透视系统 (v5.0 - Evolving)")

# Tab 分页
tab_build, tab_analyze, tab_graph = st.tabs(["📚 1. 知识库构建", "🔍 2. 逻辑透视分析", "🌌 3. 全局图谱预览"])

# --- Tab 1: 知识库构建 ---
with tab_build:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.info("上传文档 (Markdown/TXT/PNG)，系统将自动提取：\n\n1. 实体与关系 (Graph)\n2. 片段摘要 (Summary)\n3. 全局逻辑推导 (Inference)")
        uploaded_files = st.file_uploader("选择文件", type=["md", "txt","png","jpg","jpeg"], accept_multiple_files=True)
        
        build_btn = st.button("🚀 开始构建/重建图谱", type="primary", use_container_width=True)
    
    with col2:
        if build_btn and uploaded_files:
            with st.status("正在构建 GraphRAG 知识底座...", expanded=True) as status:
                st.write("📂 保存文件...")
                doc_files = []
                img_files = []
                
                img_save_dir = "./.uploaded_images"
                os.makedirs(img_save_dir, exist_ok=True)
                doc_save_dir = "./.uploaded_docs" 
                os.makedirs(doc_save_dir, exist_ok=True)

                for up_file in uploaded_files:
                    if up_file.type.startswith("image"):
                        file_path = os.path.join(img_save_dir, up_file.name)
                        with open(file_path, "wb") as f:
                            f.write(up_file.getbuffer())
                        img_files.append(file_path)
                    else:
                        file_path = os.path.join(doc_save_dir, up_file.name)
                        with open(file_path, "wb") as f:
                            f.write(up_file.getbuffer())
                        doc_files.append(file_path)
                
                st.write("🧹 清理旧数据...")
                agents["graph_rag"].clear_db()
                
                progress_bar = st.progress(0)
                total_steps = len(doc_files) + len(img_files)
                current_step = 0

                for img_path in img_files:
                    st.write(f"👁️ 正在进行视觉逻辑分析: {os.path.basename(img_path)} ...")
                    vision_analysis = agents["vision"].analyze_image(img_path)
                    
                    markdown_content = (
                        f"# Visual Logic Analysis: {os.path.basename(img_path)}\n\n"
                        f"{vision_analysis}"
                    )
                    
                    md_filename = f"{os.path.basename(img_path)}.md"
                    md_save_path = os.path.join(doc_save_dir, md_filename)
                    with open(md_save_path, "w", encoding='utf-8') as f:
                        f.write(markdown_content)
                    
                    agents["graph_rag"].build_graph(md_save_path)
                    current_step += 1
                    if total_steps > 0: progress_bar.progress(current_step / total_steps)

                for doc_path in doc_files:
                    st.write(f"🧠 正在深度分析: {os.path.basename(doc_path)} ...")
                    agents["graph_rag"].build_graph(doc_path)
                    current_step += 1
                    if total_steps > 0: progress_bar.progress(current_step / total_steps)
                
                st.session_state.graph_built = True
                status.update(label="✅ 图谱构建完成！", state="complete", expanded=False)
                st.balloons()
        
        if st.session_state.graph_built:
            try:
                st.success(f"当前图谱状态：{agents['graph_rag'].graph.number_of_nodes()} 节点, {agents['graph_rag'].graph.number_of_edges()} 关系")
            except:
                pass

# --- Tab 2: 逻辑分析 (核心功能 - 含 Double-Loop Learning) ---
with tab_analyze:
    if not st.session_state.graph_built:
        st.warning("请先在“知识库构建”页面上传并处理文档。")
    else:
        col_q, col_btn = st.columns([4, 1])
        with col_q:
            query = st.text_input("输入分析目标", placeholder="例如：RAG 系统的核心流程是怎样的？", value="系统整体架构与核心算法流程")
        with col_btn:
            st.write("")
            st.write("")
            analyze_btn = st.button("🔍 深度分析", type="primary", use_container_width=True)
            
        if analyze_btn:
            st.session_state.analysis_result = {} 
            
            # 1. GraphRAG 搜索
            with st.spinner("正在图谱中游走并回溯原文..."):
                raw_context = agents["graph_rag"].search(query, top_k=3)
                st.session_state.analysis_result['raw_context'] = raw_context
                
            # 2. Router 决策 (会利用 Router 经验池)
            with st.spinner("正在由 Router 参考历史经验进行策略制定..."):
                route_res = agents["router"].route_and_analyze(user_content = raw_context,user_target = query)
                st.session_state.analysis_result['logic'] = route_res.get("analysis_content", "")
                st.session_state.analysis_result['prompt_file'] = route_res.get("target_prompt_file", "flowchart.md")
                st.session_state.analysis_result['reason'] = route_res.get("reason", "")
            
            # 3. 代码生成
            with st.spinner("正在生成可视化代码..."):
                current_code = agents["code_gen"].generate_code(
                    st.session_state.analysis_result['logic'], 
                    prompt_file=st.session_state.analysis_result['prompt_file']
                )
                
                       
            # 4. 代码校验与闭环学习
            max_retries = 3
            
            # 【核心修改】定义一个列表，记录本次循环中失败的尝试
            # 结构: [{"code": "failed_code_str", "error": "error_msg_str"}]
            attempt_history = [] 
            
            last_bad_code = None
            last_error = None
            
            with st.status("正在进行语法校验与系统进化...", expanded=True) as status:
                for i in range(max_retries + 1):
                    status.write(f"🔍 第 {i+1} 次语法校验...")
                    
                    # A. 校验
                    validation = utils.quick_validate_mermaid(current_code)
                    
                    if validation['valid']:
                        # ... (校验通过的逻辑不变，录入 Router/CodeRevise 经验) ...
                        status.write("✅ 校验通过！")
                        
                        if i > 0 and last_bad_code and last_error:
                            # ... (CodeRevise 录入逻辑) ...
                            try:
                                agents["code_revise"].record_mistake(last_bad_code, last_error, current_code)
                            except: pass

                        try:
                            agents["router"].learn_from_success(query, current_code)
                        except: pass

                        st.session_state.analysis_result['code'] = current_code
                        status.update(label="代码生成与系统进化完成", state="complete", expanded=False)
                        break
                    else:
                        # C. 校验失败
                        error_msg = validation['error']
                        status.write(f"❌ 发现语法错误: {error_msg[:100]}...")
                        
                        if i == max_retries:
                            st.error("无法自动修复该代码，请手动检查。")
                            st.session_state.analysis_result['code'] = current_code
                            status.update(label="自动修复失败", state="error")
                            break
                        
                        # 【核心修改】记录本次失败的尝试
                        attempt_history.append({
                            "code": current_code,
                            "error": error_msg
                        })
                        
                        last_bad_code = current_code
                        last_error = error_msg
                        
                        status.write(f"🔧 正在尝试第 {i+1} 种修复方案 (参考前 {len(attempt_history)} 次失败)...")
                        
                        # 【核心修改】调用 revise_code 时传入 previous_attempts
                        current_code = agents["code_revise"].revise_code(
                            current_code, 
                            error_message=error_msg,
                            previous_attempts=attempt_history # <--- 关键参数
                        )            

        # --- 结果展示区 ---
        if st.session_state.analysis_result:
            res = st.session_state.analysis_result
            
            st.divider()
            
            c1, c2 = st.columns([3, 2])
            
            with c1:
                st.subheader("📊 逻辑可视化")
                st.caption(f"策略: {res.get('reason','')} | 模式: {res.get('prompt_file','')}")
                
                if 'code' in res:
                    utils.render_mermaid(res['code'], height=600)
                    with st.expander("查看 Mermaid 源码"):
                        st.code(res['code'], language='mermaid')
                
            with c2:
                st.subheader("📖 溯源与证据")
                
                context_text = res.get('raw_context', '')
                logic_text = res.get('logic', '')

                with st.expander("提取的结构化逻辑", expanded=True):
                    st.markdown(logic_text)
                
                if "### Source References" in context_text:
                    parts = context_text.split("### Source References")
                    graph_paths = parts[0]
                    sources = "### Source References" + parts[1]
                else:
                    graph_paths = context_text
                    sources = "无详细原文引用。"

                with st.expander("图谱推理路径 (Graph Paths)", expanded=False):
                    st.markdown(graph_paths)
                
                with st.expander("核心原文片段 (Chunks)", expanded=False):
                    st.markdown(sources)

# --- Tab 3: 全局图谱预览 ---
with tab_graph:
    st.header("🌌 知识图谱全景")
    st.markdown("这是 GraphRAG 脑海中的“世界观”。节点代表实体，连线代表通过局部提取或全局推导出的关系。")
    if st.button("刷新全景图"):
        pass 
    
    if st.session_state.graph_built:
        utils.visualize_knowledge_graph(agents["graph_rag"], height=700)
    else:
        st.info("暂无图谱数据。")