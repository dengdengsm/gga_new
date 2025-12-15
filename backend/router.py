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

    def route_and_analyze(self, user_content: str, user_target:str = "",) -> Dict[str, Any]:
        """
        核心功能：分析需求 -> 检索经验 -> 制定策略
        (已重构：内置 Prompt，不再依赖外部文件，统一管理参数)
        """
        print(f"⚡ Router 正在分析需求 (学习模式: {'开启' if self.learn_mode else '关闭'})...")

        # 1. RAG 检索：看看以前有没有画过类似的图
        # search() 返回的是 list of strings (即 'a'/设计思路)
        retrieved_experiences = self.rag.search_score(query=user_target, top_k=10)
     
        # 2. 构建经验上下文 (Dynamic RAG Section)
        experience_section = ""
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
            "You are an intelligent **Visualization Orchestrator**.\n"
            "Your goal is to select the BEST Mermaid diagram type based on the user's request.\n\n"
            
            "### 1. Diagram Type Menu (Strict Mapping)\n"
            "Select the filename strictly from this list. Do NOT invent new filenames.\n\n"
            
            "**Structure **:\n"
            "- `flowchart.md`: Logic flows, algorithms, process steps. (Most Common)\n"
            "- `architecture.md`: Cloud/System high-level architecture.\n"
            "- `classDiagram.md`: OOP classes, data structures.\n"
            "- `entityRelationshipDiagram.md`: Database schemas (ERD).\n"
            "- `block.md`: Hardware layouts or simple block structures.\n\n"
            
            "**Behavior **:\n"
            "- `sequenceDiagram.md`: Interaction between services/actors over time.\n"
            "- `stateDiagram.md`: Lifecycle states, status transitions.\n"
            "- `userJourney.md`: User workflow steps.\n\n"
            
            "**Project & Data **:\n"
            "- `gantt.md`, `timeline.md`, `gitgraph.md`, `mindmap.md`\n"
            "- `pie.md`, `xyChart.md`, `quadrantChart.md`\n\n"
            f"{experience_section}\n"
            "**You should analyze the content according to the user's requirement**\n"
            "**You should contain as more details as you can in your output**\n"
            "### 2. Output Format (JSON Only)\n"
            "Output a SINGLE JSON object:\n"
            "{\n"
            "  \"reason\": \"Cite the specific RAG reference if used.\",\n"
            "  \"target_prompt_file\": \"filename.md\",\n"
            "  \"analysis_content\": \"Structured summary for the coder.\"\n"
            "}\n\n"
            
            
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
        
    def analyze_specific_mode(self, user_content: str, user_target: str, specific_type: str) -> Dict[str, Any]:
        """
        【新增】定向分析模式：当用户明确指定图表类型时调用
        跳过选型步骤，直接生成针对该图表的分析内容。
        """
        print(f"⚡ Router 进入定向分析模式 -> 目标类型: {specific_type}\n")
        # 1. 依然尝试检索相关经验 (可能包含针对该特定图表的画法技巧)
        retrieved_experiences = self.rag.search_score(query=user_target, top_k=5)
        experience_context = ""
        if retrieved_experiences:
            print(f"   [RAG] 联想到 {len(retrieved_experiences)} 条相关设计思路")
            experience_context = "\n### Reference Design Strategies (From Past Success):\n"
            for idx, exp in enumerate(retrieved_experiences):
                experience_context += f"{idx+1}. {exp}\n"
        else:
            print("   [RAG] 无相关经验，使用通用策略。")
        if retrieved_experiences:
            # 如果有经验，就加一段“狠话”
            experience_instruction = (
                "\n\n"
                "### 🧠 CRITICAL REFERENCE (RAG MEMORY)\n"
                "The following are **SUCCESSFUL PAST STRATEGIES** retrieved from your memory bank.\n"
                f"**INSTRUCTION**: You can learn only from the {specific_type} strategies, .\nOther type of diagram has little value to learn from.\n"
                "--------------------------------------------------\n"
            )
            # 拼装：指令 + 具体的经验列表
            experience_section = experience_instruction + experience_context
        else:
            experience_section = ""
        # 2. 构造定向 Prompt
        system_prompt = (
            f"You are a Visualization Expert. The user has EXPLICITLY requested a '{specific_type}' diagram.\n"
            f"### INSTRUCTIONS:\n"
            f"1. Analyze the [User Content] and [User Requirement].\n"
            f"2. Extract the key entities, relationships, or steps needed to build a high-quality {specific_type}.\n"
            f"3. Do NOT suggest other diagram types.\n"
            f"4. Output JSON strictly.\n\n"
            f"{experience_section}"
            f"### OUTPUT FORMAT (JSON):\n"
            f"{{\n"
            f"  \"reason\": \"User manually selected {specific_type}.\",\n"
            f"  \"target_prompt_file\": \"{specific_type}.md\",\n"
            f"  \"analysis_content\": \"...Structured analysis summary suitable for generating {specific_type} code...\"\n"
            f"}}"
        )

        messages = [{"role": "user", "content": f"[User Requirement]: {user_target}\n\n[Context Content]:\n{user_content}"}]

        try:
            response_text = self.llm.chat(messages, system_prompt=system_prompt, json_mode=True)
            result = json.loads(response_text)
            
            # 强制修正文件名，防止LLM幻觉
            target_file = f"{specific_type}.md"
            result['target_prompt_file'] = target_file
            
            return result
        except Exception as e:
            print(f"Router 定向分析失败: {e}，使用原始内容作为分析结果")
            return {
                "target_prompt_file": f"{specific_type}.md",
                "reason": "Fallback: Analysis Failed",
                "analysis_content": f"Requirement: {user_target}\nContext: {user_content[:1500]}"
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