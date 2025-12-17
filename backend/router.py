import json
import os
from Agent import deepseek_agent
from rag import LocalKnowledgeBase
from typing import Dict, Any, List

class RouterAgent:
    def __init__(self, 
                 model_name: str = "deepseek-reasoner", 
                 learn_mode: bool = False,
                 experience_file: str = "./knowledge/experience/router.json"):
        
        print(f"--- 初始化 RouterAgent (智能进化版) [模型: {model_name}] ---")
        self.llm = deepseek_agent(model_name=model_name)
        self.learn_mode = learn_mode
        self.experience_file = experience_file
        
        # 1. 初始化 RAG 引擎 (复用 LocalKnowledgeBase)
        # 注意：这里我们复用 rag.py 的能力，将经验池作为 "QA知识" 加载
        self.rag = LocalKnowledgeBase("./.local_rag_db/router")
        
        # 2. 加载经验 (冷启动)
        if os.path.exists(self.experience_file):
            print(f"🧠 Router 正在加载历史经验库: {self.experience_file}")
            # add_qa_mistakes 本质就是加载 list of {q, a}，完全通用
            # 它会自动忽略 json 里的 'source_code' 字段，只存 q 和 a
            self.rag.add_qa_mistakes(self.experience_file)
        else:
            print("⚠️ 未找到经验库文件，Router 将从零开始运行。")

    def _load_prompt(self, file_path: str) -> str:
        """加载外部提示词文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def route_and_analyze(self, user_content: str, user_target:str = "",use_experience:bool = False) -> Dict[str, Any]:
        """
        核心功能：分析需求 -> 检索经验 -> 制定策略
        (已重构：内置 Prompt，不再依赖外部文件，统一管理参数)
        """
        print(f"⚡ Router 正在分析需求 (学习模式: {'开启' if self.learn_mode else '关闭'})...")

     
        # 2. 构建经验上下文 (Dynamic RAG Section)
        
        experience_section = ""
        if use_experience:
            retrieved_experiences = self.rag.search_score(query=user_target, top_k=10)
            if retrieved_experiences:
                print(f"   [RAG] 联想到 {len(retrieved_experiences)} 条相关设计思路")
                
                # 拼接具体经验列表
                context_list = "\n".join([f"{idx+1}. {exp}" for idx, exp in enumerate(retrieved_experiences)])
                
                # 构造经验指令块
                experience_section = (
                    "\n\n"
                    "### 🧠 CRITICAL REFERENCE (RAG MEMORY)\n"
                    "The following are **SUCCESSFUL PAST STRATEGIES** retrieved from your memory bank.\n"
                    "**INSTRUCTION**: You MUST prioritized these strategies. If a past case used a specific diagram type for a similar scenario, **COPY THAT CHOICE**.\n"
                    "**Attention**: Pay more attention to the most popular strategies, for that is the most accepted, too.  "
                    "**The diagram type you choose should be suitable for the user's requirement:**\n"
                    "--------------------------------------------------\n"
                    f"{context_list}\n"
                )
            else:
                print("   [RAG] 无相关经验，使用通用策略。")

        
        # 3. 构造完整 System Prompt (原 router.md + 动态逻辑)
        # 包含了图表类型映射表和输出格式要求
        system_prompt = (
    "You are a **Visual Logic Architect**. Your goal is to Analyze the User Request and Context, Select the Best Diagram Type, and **Extract Structured Logic** for the code generator.\n\n"
    
    "### 1. Analysis Strategy\n"
    "Step 1: Analyze the [User Content] to identify the core entities, relationships, and data flow.\n"
    "Step 2: Match the data characteristics with the **Diagram Type Menu**.\n"
    "Step 3: Extract **Critical Details** (Node names, edge labels, conditions, directions) into the `analysis_content`.\n\n"

    "### 2. Diagram Type Menu & Data Characteristics\n"
    "**Structure (Static Relationship)**:\n"
    "- `flowchart.md`: Decisions, process steps, algorithms. (Keyword: Process, Workflow, Logic)\n"
    "- `architecture.md`: System components, cloud infrastructure, container hierarchy. (Keyword: System, Layout, Stack)\n"
    "- `classDiagram.md`: OOP classes, inheritance, interfaces, attributes. (Keyword: Class, Object, Data Model)\n"
    "- `entityRelationshipDiagram.md`: Database schemas, PK/FK, cardinality. (Keyword: DB, Schema, Table)\n"
    
    "**Behavior (Dynamic Interaction)**:\n"
    "- `sequenceDiagram.md`: Message exchange sequence, API calls, request/response. (Keyword: Interaction, Protocol, Flow)\n"
    "- `stateDiagram.md`: Life-cycle states, state transitions, triggers. (Keyword: Status, State Machine, Lifecycle)\n"
    "- `userJourney.md`: User steps, satisfaction levels, tasks. (Keyword: User Experience, Step)\n\n"
    
    "**Data & Plan**:\n"
    "- `gantt.md`: Project schedules, dates, tasks. | `pie.md`: Proportions, percentages.\n\n"

    f"{experience_section}\n"

    "### 3. Critical Output Instruction for `analysis_content`\n"
    "The `analysis_content` MUST be a **Mermaid-Ready Logic Description**, NOT a general summary.\n"
    "- **If Flowchart**: List all nodes with clear IDs and text. Describe strictly: Node A -> Condition B -> Node C.\n"
    "- **If Sequence**: List participants clearly. Describe order: A calls B (sync/async), B returns to A.\n"
    "- **If Class/ER**: List Entity Names, Attributes (type/name), and specific relationships (1:N, inheritance).\n"
    "- **Keep Technical Terms**: Do not translate variable names or API endpoints.\n\n"

    "### 4. Output Format (JSON Only)\n"
    "{\n"
    "  \"reason\": \"Why you chose this diagram type (mention specific data features).\",\n"
    "  \"target_prompt_file\": \"filename.md\",\n"
    "  \"analysis_content\": \"Structured Logic Description...\"\n"
    "}"
)
        
        # 4. LLM 决策
        messages = [{"role": "user", "content": f"[User Requirement]:\n{user_target}\n\n[Context Content]:\n{user_content}"}]
        
        try:
            response_text = self.llm.chat(messages, system_prompt=system_prompt, json_mode=True)
            result = json.loads(response_text)
            
            # 简单的后缀补全
            if not result.get('target_prompt_file', '').endswith('.md'):
                result['target_prompt_file'] += ".md"
            
            return result
            
        except json.JSONDecodeError:
            print("Router JSON 解析失败，回退默认策略。")
            return {
                "target_prompt_file": "flowchart.md",
                "reason": "Fallback: JSON Parse Error",
                "analysis_content": user_content[:2000]
            }
        
    def analyze_specific_mode(self, user_content: str, user_target: str, specific_type: str, use_experience:bool = False) -> Dict[str, Any]:
        """
        【定向分析模式 - 增强版】
        支持 Graphviz (DOT) 及 Mermaid 的深度逻辑提取。
        """
        print(f"⚡ Router 进入定向分析模式 -> 目标类型: {specific_type}")
        
        # 1. 经验检索 (保持原有逻辑，增强针对性)
        experience_section = ""
        if use_experience:
            retrieved_experiences = self.rag.search_score(query=user_target, top_k=3)
            if retrieved_experiences:
                print(f"   [RAG] 联想到 {len(retrieved_experiences)} 条相关经验")
                context_list = "\n".join([f"{idx+1}. {exp}" for idx, exp in enumerate(retrieved_experiences)])
                experience_section = (
                    "\n\n### 🧠 REFERENCE MEMORY (Past Success)\n"
                    f"Consider these successful patterns for {specific_type}:\n"
                    f"{context_list}\n"
                )

        # 2. 构造文件名 (自动适配 graphviz)
        # 如果前端传的是 'dot' 或 'graphviz'，统一映射到 graphviz.md
        if specific_type.lower() in ['dot', 'graphviz']:
            target_file = "graphviz.md"
            type_instruction = (
                "### SPECIAL INSTRUCTION FOR GRAPHVIZ (DOT)\n"
                "You are preparing logic for a **Graphviz DOT** engine.\n"
                "Focus on **Topology and Hierarchy** rather than just flow.\n"
                "**Extraction Requirements**:\n"
                "1. **Clusters/Subgraphs**: Group related nodes (e.g., 'subgraph cluster_A { ... }').\n"
                "2. **Node Attributes**: Define shapes (box, ellipse, record) based on entity type.\n"
                "3. **Relationships**: Define connections clearly (directed '->' or undirected '--').\n"
                "4. **Layout**: Suggest 'rankdir' (TB, LR) based on the flow.\n"
            )
        else:
            # Mermaid 通用逻辑
            target_file = f"{specific_type}.md" if specific_type.endswith('.md') else f"{specific_type}.md"
            type_instruction = (
                f"### SPECIAL INSTRUCTION FOR {specific_type.upper()}\n"
                "Focus on the strict syntax logic required for this specific Mermaid diagram type.\n"
                "- If Sequence: Identify Participants and exact Order of messages.\n"
                "- If Class/ER: Identify Entities, Attributes, and Cardinalities.\n"
                "- If Flowchart: Identify Nodes, Decisions, and Edge labels.\n"
            )

        # 3. 构造增强版 System Prompt
        system_prompt = (
            f"You are a **Specialized Visual Logic Architect**.\n"
            f"The user has EXPLICITLY selected the tool: **'{specific_type}'**.\n"
            f"Your task is NOT to choose a tool, but to **Extract Structured Logic** specifically optimized for it.\n\n"
            
            f"{type_instruction}\n\n"
            
            f"{experience_section}\n\n"

            "### CRITICAL: Analysis Content Format\n"
            "The 'analysis_content' you output MUST be a **Structured Blueprint** for the code generator.\n"
            "Do NOT write paragraphs. Write logic steps or structural definitions.\n"
            "**Example for Graphviz**:\n"
            "- Layout: Left-to-Right (rankdir=LR)\n"
            "- Cluster 'Database': Contains [UserDB, LogDB]\n"
            "- Node 'App': shape=component\n"
            "- Edge: App -> UserDB [label='read']\n\n"

            "### OUTPUT FORMAT (JSON Only)\n"
            "{\n"
            f"  \"reason\": \"User manually selected {specific_type}. Analyzing for optimal structure.\",\n"
            f"  \"target_prompt_file\": \"{target_file}\",\n"
            f"  \"analysis_content\": \"...Your Structured Logic Blueprint here...\"\n"
            "}"
        )

        messages = [{"role": "user", "content": f"[User Requirement]: {user_target}\n\n[Context Content]:\n{user_content}"}]

        try:
            response_text = self.llm.chat(messages, system_prompt=system_prompt, json_mode=True)
            result = json.loads(response_text)
            
            # 双重保险：强制覆盖文件名，防止模型幻觉改名
            result['target_prompt_file'] = target_file
            
            return result
        except Exception as e:
            print(f"Router 定向分析失败: {e}，使用回退策略")
            return {
                "target_prompt_file": target_file,
                "reason": "Fallback: Analysis Failed",
                "analysis_content": f"User Requirement: {user_target}\n\nContext Data:\n{user_content[:2000]}"
            }
                    
    def learn_from_success(self, user_query: str, valid_code: str):
        """
        【进化接口】当 App 确认代码生成成功后调用。
        提炼本次成功的 {Q, A, Source} 并存入库。
        """
        if not self.learn_mode:
            return

        print("🧠 Router 正在从本次成功案例中学习 (Experience Consolidation)...")
        
        # 1. LLM 提炼
        system_prompt = (
            "You are an Experience Extractor. Analyze the User Query and the Generated Mermaid Code.\n"
            "Extract a generic Experience Pair in JSON:\n"
            "{\n"
            "  \"q\": \"Abstract Scenario (e.g., Microservice Trace)\",\n"
            "  \"a\": \"Design Strategy (e.g., Use sequenceDiagram with activation bars...)\"\n"
            "}\n"
            "Note: 'q' should cover the intent, 'a' should cover the visualization technique."
        )
        
        user_msg = f"User Query:\n{user_query}\n\nGenerated Code:\n{valid_code[:1000]}..." # 截断防止太长
        
        try:
            response = self.llm.chat([{"role": "user", "content": user_msg}], system_prompt=system_prompt, json_mode=True)
            data = json.loads(response)
            
            new_q = data.get("q")
            new_a = data.get("a")
            
            if new_q and new_a:
                # 2. 构造完整记录 (含源码溯源)
                new_entry = {
                    "q": new_q,
                    "a": new_a,
                    "source_code": valid_code # 保留源码作为案底
                }
                
                # 3. 持久化存储 (JSON)
                self._save_to_disk(new_entry)
                
                # 4. 运行时热更新 (RAG)
                # 只需要 q 和 a 即可检索
                self.rag.add_single_qa(new_q, new_a, source="runtime_learning")
                print(f"✨ Router 经验值 +1: {new_q}")
                
        except Exception as e:
            print(f"Router 学习失败: {e}")

    def _save_to_disk(self, new_entry: Dict[str, Any]):
        """追加写入 JSON 文件"""
        current_data = []
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.experience_file), exist_ok=True)
        
        if os.path.exists(self.experience_file):
            try:
                with open(self.experience_file, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            except:
                current_data = []
        
        # 简单的查重 (基于 Q)
        # 实际生产中可能允许同一个 Q 有多种 A，这里简单起见去重
        for item in current_data:
            if item.get('q') == new_entry['q']:
                return # 已存在类似场景，暂不重复录入

        current_data.append(new_entry)
        
        with open(self.experience_file, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
    def reload_llm_config(self, config: dict):
        """
        【热更新】接收前端配置(驼峰命名)并更新底层 LLM
        """
        # 从字典中提取配置
        api_key = config.get("apiKey")
        api_url = config.get("apiUrl")
        model_name = config.get("modelName")
        
        # 调用底层 Agent.py 中定义的 update_config
        # 这里的 self.llm 对应 Agent/deepseek_agent 实例
        if hasattr(self, 'llm'):
            self.llm.update_config(api_key=api_key, base_url=api_url, model_name=model_name)
            print(f"🔄 [{self.__class__.__name__}] LLM配置已重载 -> 模型: {model_name}")

# --- 单元测试 ---
if __name__ == "__main__":
    # 测试初始化
    router = RouterAgent(learn_mode=True)
    
    # 测试分析
    req = "画一个TCP三次握手的时序图"
    res = router.route_and_analyze(req)
    print("分析结果:", res.get("target_prompt_file"))
    
    # 测试学习
    code = "sequenceDiagram\nClient->>Server: SYN\nServer->>Client: SYN, ACK..."
    router.learn_from_success(req, code)