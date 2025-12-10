import json
import os
from Agent import deepseek_agent
from rag import LocalKnowledgeBase
from typing import Dict, Any, List

class RouterAgent:
    def __init__(self, 
                 model_name: str = "deepseek-reasoner", 
                 learn_mode: bool = True,
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

    def route_and_analyze(self, user_content: str, user_target:str = "") -> Dict[str, Any]:
        """
        核心功能：分析需求 -> 检索经验 -> 制定策略
        """
        print(f"⚡ Router 正在分析需求 (学习模式: {'开启' if self.learn_mode else '关闭'})...")

        # 1. RAG 检索：看看以前有没有画过类似的图
        # search() 返回的是 list of strings (即 'a'/设计思路)
        retrieved_experiences = self.rag.search(query=user_target, top_k=10)
        
        # ================== 🐛 DEBUG LOG START ==================
        # 既然你觉得它选得离谱，我们就把案发现场保留下来
        debug_info = {
            "search_query": user_target,
            "retrieved_count": len(retrieved_experiences),
            "retrieved_experiences": retrieved_experiences
        }
        
        debug_file = "debug_router_experiences.json"
        try:
            with open(debug_file, "w", encoding="utf-8") as f:
                json.dump(debug_info, f, ensure_ascii=False, indent=2)
            print(f"🐛 [DEBUG] 检索结果已导出至: {debug_file} (请检查到底是谁在误导Router)")
        except Exception as e:
            print(f"🐛 [DEBUG] 导出失败: {e}")
        # ================== 🐛 DEBUG LOG END ====================

        experience_context = ""
        if retrieved_experiences:
            print(f"   [RAG] 联想到 {len(retrieved_experiences)} 条相关设计思路")
            experience_context = "\n### Reference Design Strategies (From Past Success):\n"
            for idx, exp in enumerate(retrieved_experiences):
                experience_context += f"{idx+1}. {exp}\n"
        else:
            print("   [RAG] 无相关经验，使用通用策略。")

        # 2. 构造 Prompt
        # 如果有外部文件则加载，否则使用内置默认
        base_prompt = self._load_prompt("./prompt/router/router.md")
        if not base_prompt:
            base_prompt = (
                "You are a Visualization Architect. Analyze the input content.\n"
                "Output JSON: {\"reason\": \"...\", \"target_prompt_file\": \"...\", \"analysis_content\": \"...\"}"
            )
        # --- 核心修改：在代码里动态注入“强制参考指令” ---
        if retrieved_experiences:
            # 如果有经验，就加一段“狠话”
            experience_instruction = (
                "\n\n"
                "### 🧠 CRITICAL REFERENCE (RAG MEMORY)\n"
                "The following are **SUCCESSFUL PAST STRATEGIES** retrieved from your memory bank.\n"
                "**INSTRUCTION**: You MUST prioritized these strategies. If a past case used a specific diagram type for a similar scenario, **COPY THAT CHOICE**.\n"
                "**Attention**: You should choose the most popular strategies, for that is the most accepted, too."
                "--------------------------------------------------\n"
            )
            # 拼装：指令 + 具体的经验列表
            experience_section = experience_instruction + experience_context
        else:
            experience_section = ""
        # 将经验注入 Prompt
        system_prompt = f"{base_prompt}\n\n{experience_section}"
        
        # 3. LLM 决策
        messages = [{"role": "user", "content": f"[User Requirement]:\n{user_content}"}]
        
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