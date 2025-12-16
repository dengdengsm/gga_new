import os
import json
import glob
from typing import List, Optional,Dict
from Agent import deepseek_agent, Message
from rag import LocalKnowledgeBase

class CodeReviseAgent:
    def __init__(self, 
                 knowledge_base_dir: str = "./knowledge_base", 
                 mistake_file_path: str = "./knowledge/experience/mistakes.json",
                 model_name: str = "deepseek-chat"):
        """
        初始化代码修订 Agent
        :param knowledge_base_dir: 存放语法规则 MD 文件的目录
        :param mistake_file_path: 存放错题集 JSON 的路径
        :param model_name: DeepSeek 模型名称
        """
        print(f"--- 初始化 CodeReviseAgent [模型: {model_name}] ---")
        
        self.llm = deepseek_agent(model_name=model_name)
        self.rag = LocalKnowledgeBase("./.local_rag_db/mistakes")
        
        self.mistake_file_path = mistake_file_path
        
        # 1. 加载通用语法手册 (Markdown)
        # self._load_markdown_rules(knowledge_base_dir)
        
        # 2. 加载错题经验 (JSON - Q&A 模式)
        self._load_mistakes(mistake_file_path)

    def _load_markdown_rules(self, directory: str):
        """加载 Markdown 格式的语法说明书"""
        if not os.path.exists(directory):
            # os.makedirs(directory, exist_ok=True)
            return

        md_files = glob.glob(os.path.join(directory, "*.md"))
        for file_path in md_files:
            try:
                self.rag.add_markdown(file_path)
            except Exception as e:
                print(f"加载规则文件 {file_path} 失败: {e}")

    def _load_mistakes(self, json_path: str):
        """加载错题本"""
        if not os.path.exists(os.path.dirname(json_path)):
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            
        if os.path.exists(json_path):
            try:
                self.rag.add_qa_mistakes(json_path)
            except Exception as e:
                print(f"加载错题集失败: {e}")
        else:
            # 初始化一个空文件
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def revise_code(self, raw_code: str, error_message: str = "", previous_attempts: List[Dict] = None, language: str = "mermaid", use_mistake_book:bool  = False) -> str:
        """
        核心功能：接收代码和(可选的)报错信息，利用 RAG 检索策略进行修复
        """
        print(f"\n--- CodeRevise: 开始修订 (Ref: ErrorLog? {bool(error_message)}) ---")
        
        # 1. RAG 检索策略
        # 如果有报错信息，直接用报错去查 QA 库 (查到了就是以前踩过的坑)
        # 如果没有报错(只是预检)，则用代码片段去查通用的 Markdown 语法书
        reference_context = ""
        if use_mistake_book:
            search_query = error_message if error_message else raw_code[:200]
            retrieved_docs = self.rag.search(query=search_query, top_k=6)
            reference_context = "\n- ".join(retrieved_docs)
            if not reference_context:
                reference_context = "No specific past experience found. Follow standard syntax."

            print(f"   [RAG 知识召回]: 检索到 {len(retrieved_docs)} 条相关建议")

        # 2. 构建 Prompt
        # 构造失败历史的文本块
        failed_history_text = ""
        if previous_attempts:
            failed_history_text = "\n### 🚫 FAILED ATTEMPTS (DO NOT REPEAT!)\nThe following solutions have already been tried and FAILED. You must generate a DIFFERENT solution.\n"
            for idx, attempt in enumerate(previous_attempts):
                failed_history_text += f"--- Attempt {idx+1} ---\n[Code Snippet]:\n{attempt['code'][:200]}...\n[Resulting Error]: {attempt['error']}\n"
        
        system_prompt = (
            f"You are an expert **Code Reviser** for {language}.\n"
            "Your goal is to fix the code to make it renderable.\n\n"
            "### Knowledge Base (Past Experience & Rules)\n"
            f"{reference_context}\n"
            f"{failed_history_text}\n\n"
            "### Instructions\n"
            "1. Focus strictly on fixing syntax errors.\n"
            "2. **DO NOT** change the logic, node names (unless they cause syntax errors), or flow direction.\n"
            "3. **CRITICAL**: If previous attempts are provided, analyze why they failed and try a completely different syntax approach.\n"
            "4. Return ONLY the fixed code. No markdown markers, no explanations."
        )

        user_content = f"【Bad Code】:\n{raw_code}\n\n"
        
        if error_message:
            user_content += f"【Error Log】:\n{error_message}\n\n"
            user_content += "Please fix the code specifically addressing the Error Log above."
        
        # 3. 调用 LLM
        try:
            revised_code = self.llm.chat([{"role": "user", "content": user_content}], system_prompt=system_prompt)
            # 清洗
            revised_code = revised_code.replace("```mermaid", "").replace("```", "").strip()
            return revised_code
        except Exception as e:
            print(f"修订调用失败: {e}")
            return raw_code
        
    def revise_code_stream(self, raw_code: str, error_message: str = "", previous_attempts: List[Dict] = None, language: str = "mermaid"):
        """
        【流式修复接口】支持打字机效果
        逻辑与 revise_code 完全一致，只是改为 yield 输出
        """
        print(f"🌊 [CodeRevise] 开始流式修订 (Ref: ErrorLog? {bool(error_message)})")
        
        # 1. RAG 检索策略 (完全复用原有逻辑)
        search_query = error_message if error_message else raw_code[:200]
        retrieved_docs = self.rag.search(query=search_query, top_k=6)
        
        reference_context = "\n- ".join(retrieved_docs)
        if not reference_context:
            reference_context = "No specific past experience found. Follow standard syntax."

        # 2. 构建 Prompt (完全复用原有逻辑)
        failed_history_text = ""
        if previous_attempts:
            failed_history_text = "\n### 🚫 FAILED ATTEMPTS (DO NOT REPEAT!)\nThe following solutions have already been tried and FAILED. You must generate a DIFFERENT solution.\n"
            for idx, attempt in enumerate(previous_attempts):
                # 做了简单的防御，防止字段缺失报错
                code_snippet = attempt.get('code', '')[:200]
                err_msg = attempt.get('error', '')
                failed_history_text += f"--- Attempt {idx+1} ---\n[Code Snippet]:\n{code_snippet}...\n[Resulting Error]: {err_msg}\n"
        
        system_prompt = (
            f"You are an expert **Code Reviser** for {language}.\n"
            "Your goal is to fix the code to make it renderable.\n\n"
            "### Knowledge Base (Past Experience & Rules)\n"
            f"{reference_context}\n"
            f"{failed_history_text}\n\n"
            "### Instructions\n"
            "1. Focus strictly on fixing syntax errors.\n"
            "2. **DO NOT** change the logic, node names (unless they cause syntax errors), or flow direction.\n"
            "3. **CRITICAL**: If previous attempts are provided, analyze why they failed and try a completely different syntax approach.\n"
            "4. Return ONLY the fixed code. No markdown markers, no explanations."
        )

        user_content = f"【Bad Code】:\n{raw_code}\n\n"
        
        if error_message:
            user_content += f"【Error Log】:\n{error_message}\n\n"
            user_content += "Please fix the code specifically addressing the Error Log above."
        
        # 3. 调用底层的流式接口
        for chunk in self.llm.chat_stream([{"role": "user", "content": user_content}], system_prompt=system_prompt):
            if chunk:
                # 同样，这里不做 replace 清洗，保持流的原始性
                yield chunk

    def optimize_code(self, code: str, instruction: str) -> str:
        """
        【新增】根据用户指令优化 Mermaid 代码
        特点：不使用 RAG，仅基于 LLM 理解执行指令（如：布局调整、样式修改、内容增删）
        """
        print(f"\n--- CodeRevise: 执行优化指令 ---")
        print(f"   [Instruction]: {instruction[:100]}...")

        system_prompt = (
            "You are an expert Mermaid Diagram Specialist.\n"
            "Your task is to MODIFY the provided Mermaid code based strictly on the User Instruction.\n"
            "Rules:\n"
            "1. Output ONLY the modified Mermaid code.\n"
            "2. Do not add markdown code blocks (```mermaid ... ```). Just the code text.\n"
            "3. Maintain the original diagram logic unless the instruction explicitly asks to change it.\n"
            "4. If the instruction involves global preferences (e.g., 'Use specific colors'), apply them accurately."
        )

        user_content = f"【Current Code】:\n{code}\n\n【Optimization Instruction】:\n{instruction}"
        
        try:
            # 直接调用 LLM，不查 RAG
            optimized_code = self.llm.chat([{"role": "user", "content": user_content}], system_prompt=system_prompt)
            # 基础清洗
            optimized_code = optimized_code.replace("```mermaid", "").replace("```", "").strip()
            return optimized_code
        except Exception as e:
            print(f"优化调用失败: {e}")
            return code # 失败则返回原代码

    def record_mistake(self, bad_code: str, error_message: str, fixed_code: str):
        """
        核心功能 (错题本)：
        当修复成功后，调用此函数。
        让 LLM 总结 {q: 报错特征, a: 通用修复策略} 并存入文件。
        """
        print("📝 正在记录错题经验 (Experience Replay)...")
        
        # 1. 构造 Prompt 让 LLM 提炼规则
        system_prompt = (
            "You are a Tech Lead summarizing coding mistakes.\n"
            "Compare the Bad Code and Fixed Code based on the Error Log.\n"
            "Extract a GENERIC rule in JSON format: {\"q\": \"Error feature\", \"a\": \"Fix strategy\"}.\n"
            "Rules:\n"
            "1. 'q' should capture the key part of the error message (for vector matching).\n"
            "2. 'a' should be a general advice (e.g., 'Do not use spaces in IDs'), NOT specific to this user's variable names.\n"
            "3. Output JSON ONLY."
        )
        
        user_content = (
            f"Error: {error_message}\n"
            f"Bad Code Fragment: {bad_code[:300]}...\n"
            f"Fixed Code Fragment: {fixed_code[:300]}..."
        )
        
        try:
            response = self.llm.chat([{"role": "user", "content": user_content}], system_prompt=system_prompt, json_mode=True)
            result = json.loads(response)
            
            new_q = result.get("q")
            new_a = result.get("a")
            
            if new_q and new_a:
                # 2. 写入文件
                current_data = []
                if os.path.exists(self.mistake_file_path):
                    with open(self.mistake_file_path, 'r', encoding='utf-8') as f:
                        try:
                            current_data = json.load(f)
                        except:
                            current_data = []
                
                # 避免完全重复
                if not any(item['q'] == new_q for item in current_data):
                    current_data.append({"q": new_q, "a": new_a})
                    with open(self.mistake_file_path, 'w', encoding='utf-8') as f:
                        json.dump(current_data, f, ensure_ascii=False, indent=2)
                    
                    # 3. 运行时热更新 (让它立即生效)
                    self.rag.add_single_qa(new_q, new_a, source="auto_recorded")
                    print(f"✅ 错题已录入: {new_q[:50]}...")
                else:
                    print("重复的经验，跳过录入。")
                    
        except Exception as e:
            print(f"记录错题失败: {e}")
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