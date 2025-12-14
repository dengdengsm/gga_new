import os
import shutil
import requests
import tempfile
import base64
import json  # <--- 新增引用
import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
import re
# --- 配置 ---
TEMP_UPLOAD_DIR = "./.temp_uploaded_files"

def quick_validate_mermaid(code: str) -> dict:
    """验证 Mermaid 代码"""
    if re.search(r'classDef\s+subgraph\b', code, re.IGNORECASE):
        error_msg = (
            "Syntax Error (Hard Check): "
            "'subgraph' is a reserved keyword and cannot be used as a class name.\n"
            "❌ Bad: classDef subgraph fill:#f9f...\n"
            "✅ Fix: Rename it to something else (e.g., classDef subgraphStyle ...)"
        )
        return {"valid": False, "error": error_msg}
    try:
        response = requests.post(
            "https://kroki.io/mermaid/svg",
            json={"diagram_source": code},
            timeout=10
        )
        if response.status_code == 200:
            return {"valid": True, "error": ""}
        else:
            return {"valid": False, "error": response.text}
    except Exception as e:
        return {"valid": False, "error": f"Request Exception: {str(e)}"}
    
def save_uploaded_files(uploaded_files):
    """保存上传文件"""
    saved_paths = []
    if os.path.exists(TEMP_UPLOAD_DIR):
        shutil.rmtree(TEMP_UPLOAD_DIR)
    os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
        
    for uploaded_file in uploaded_files:
        file_path = os.path.join(TEMP_UPLOAD_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        saved_paths.append(file_path)
    return saved_paths

def render_mermaid(code, height=600):
    """
    【最终修复版】渲染 Mermaid (解决 Python f-string 冲突)
    """
    # 1. 准备 Base64 代码
    b64_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')

    # 2. 定义配置 (这是 Python 字典，随便写，不会报错)
    # 我们在这里配置手绘风格和颜色
    mermaid_config = {
        "startOnLoad": False,
        "theme": "neutral",       # <--- 关键修改：使用 neutral 主题
        "look": "handDrawn",      # 确保开启手绘风格
        "securityLevel": "loose",
        "fontFamily": '"Comic Sans MS", "Chalkboard SE", "Comic Neue", sans-serif',
        # 移除 themeVariables，让 neutral 主题自带的手绘风格生效
        # "themeVariables": { ... } 
    }
    
    # 3. 将 Python 字典转为 JSON 字符串 (自动处理 True/False -> true/false)
    js_config_str = json.dumps(mermaid_config)

    # 4. 构建 HTML
    # 注意：下面的 HTML 中，只有 {height}, {b64_code}, {js_config_str} 是 Python 变量
    # 其他 CSS 里的花括号我都用了双括号 {{ }} 转义
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ 
                margin: 0; padding: 0; overflow: hidden; background-color: white; 
            }}
            #container {{ 
                width: 100vw; height: {height}px; position: relative; overflow: hidden;
            }}
            #loading-msg {{
                position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                color: #666; font-size: 14px; font-family: sans-serif;
            }}
            .error-box {{
                color: #d32f2f; background-color: #ffcdd2; padding: 20px; margin: 20px; border: 1px solid #d32f2f;
            }}
            /* 强制覆盖 SVG 样式 */
            svg {{ width: 100% !important; height: 100% !important; max-width: none !important; }}
        </style>
        
        <script src="https://unpkg.com/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
    </head>
    <body>
        <div id="container">
            <div id="loading-msg">⏳ 正在渲染手绘图表...</div>
        </div>

        <script type="module">
            import mermaid from 'https://unpkg.com/mermaid@10.9.1/dist/mermaid.esm.min.mjs';

            // 核心修改：直接注入 Python 生成的 JSON 字符串
            const config = {js_config_str};
            mermaid.initialize(config);

            const drawDiagram = async () => {{
                const element = document.getElementById('container');
                
                try {{
                    const graphDefinition = atob("{b64_code}"); 
                    const {{ svg }} = await mermaid.render('graphDiv', graphDefinition);
                    element.innerHTML = svg;
                    
                    const svgElement = element.querySelector('svg');
                    if (svgElement) {{
                        svgElement.style.maxWidth = 'none';
                        if (window.svgPanZoom) {{
                            window.svgPanZoom(svgElement, {{
                                zoomEnabled: true,
                                controlIconsEnabled: true,
                                fit: true,
                                center: true,
                                minZoom: 0.1,
                                maxZoom: 10
                            }});
                        }}
                    }}
                }} catch (error) {{
                    element.innerHTML = `
                        <div class="error-box">
                            <h3>Render Error</h3>
                            <pre>${{error.message}}</pre>
                        </div>
                    `;
                    console.error(error);
                }}
            }};

            drawDiagram();
        </script>
    </body>
    </html>
    """
    
    components.html(html_code, height=height + 20, scrolling=False)

def visualize_knowledge_graph(graph_rag_instance, height=500):
    """可视化知识图谱 (保持不变)"""
    if graph_rag_instance.graph.number_of_nodes() == 0:
        st.warning("图谱为空，请先构建知识库。")
        return

    net = Network(height=f"{height}px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)
    
    simple_graph = nx.Graph()
    for n in graph_rag_instance.graph.nodes():
        simple_graph.add_node(n, label=str(n), title=str(n), color="#4F8BF9")
    
    for u, v, data in graph_rag_instance.graph.edges(data=True):
        rel = data.get('relation', '')
        evidence_count = len(data.get('evidence', []))
        title_html = f"关系: {rel}<br>证据数: {evidence_count}"
        simple_graph.add_edge(u, v, title=title_html, label=rel)

    try:
        net.from_nx(simple_graph)
    except Exception as e:
        st.error(f"NetworkX 转换失败: {e}")
        return

    net.toggle_physics(True)
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode='w+', encoding='utf-8') as tmp:
            net.save_graph(tmp.name)
            tmp.seek(0)
            html_data = tmp.read()
        components.html(html_data, height=height, scrolling=False)
    except Exception as e:
        st.error(f"图谱渲染失败: {e}")