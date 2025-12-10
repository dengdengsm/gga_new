import os
from Agent import deepseek_agent, Message
from typing import List, Optional

class CodeGenAgent:
    def __init__(self, model_name: str = "deepseek-chat", prompt_dir: str = "./prompt/code_gen"):
        """
        初始化代码生成 Agent
        支持从 external Markdown 文件加载提示词，实现多种图表/代码的生成
        """
        print(f"--- 初始化 CodeGenAgent [模型: {model_name}] ---")
        self.llm = deepseek_agent(model_name=model_name)
        self.prompt_dir = prompt_dir
        
        # 确保提示词目录存在，如果不存在则创建，避免报错
        if not os.path.exists(self.prompt_dir):
            os.makedirs(self.prompt_dir, exist_ok=True)
            print(f"提示: 已自动创建提示词目录 {self.prompt_dir}")

    def _load_system_prompt(self, prompt_filename: str) -> str:
        """
        内部方法：从 prompt 文件夹加载 Markdown 内容
        :param prompt_filename: 文件名 (如 'flowchart.md' 或 'flowchart')
        :return: Prompt 文本内容
        """
        # 容错处理：如果用户没写 .md 后缀，自动补全
        if not prompt_filename.endswith(".md"):
            prompt_filename += ".md"
            
        file_path = os.path.join(self.prompt_dir, prompt_filename)
        
        if not os.path.exists(file_path):
            error_msg = f"错误: 提示词文件 '{file_path}' 未找到。请检查 prompt 目录下是否存在该文件。"
            print(error_msg)
            # 返回一个极其基础的默认 Prompt 防止程序直接崩溃
            return "You are a code generator, please generate mermaid code for user's content."
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return content

    def generate_code(self, input_text: str, prompt_file: str = "flowchart.md") -> str:
        """
        【通用生成接口】
        根据传入的 prompt_file 不同，生成不同类型的代码 (流程图、思维导图、Python绘图等)
        
        :param input_text: 用户的需求描述或逻辑文本
        :param prompt_file: 位于 prompt 文件夹下的文件名
        """
        # 1. 加载 Prompt
        system_prompt = self._load_system_prompt(prompt_file)
        
        # 2. 构建消息
        messages: List[Message] = [
            {"role": "user", "content": f"[Requirements or content]:\n{input_text}"}
        ]

        print(f"正在生成代码 (模式: {prompt_file}, Input长度: {len(input_text)})...")
        
        # 3. 调用 LLM
        response = self.llm.chat(messages, system_prompt=system_prompt)

        # 4. 清洗代码 (移除 Markdown 标记)
        return self._clean_code(response)

    def generate_code_stream(self, input_text: str, prompt_file: str = "flowchart.md"):
        """
        【流式生成接口】支持打字机效果
        逻辑与 generate_code 完全一致，只是改为 yield 输出
        """
        # 1. 加载 Prompt (复用原有逻辑)
        system_prompt = self._load_system_prompt(prompt_file)
        
        # 2. 构建消息
        messages: List[Message] = [
            {"role": "user", "content": f"[Requirements or content]:\n{input_text}"}
        ]

        print(f"🌊 [CodeGen] 正在流式生成代码 (模式: {prompt_file})...")
        
        # 3. 调用底层的流式接口 (yield)
        # 注意：这里直接把 LLM 的原始 token 吐出来，不做 _clean_code 清洗
        # 因为流式过程中很难判断 ``` 什么时候结束，清洗工作交给 API 层或前端处理
        for chunk in self.llm.chat_stream(messages, system_prompt=system_prompt):
            if chunk:
                yield chunk
        
    def _clean_code(self, text: str) -> str:
        """内部工具：移除 markdown 代码块标记，提取纯代码"""
        text = text.strip()
        
        # 移除常见的 markdown 代码块头部
        # 这里不仅包含 mermaid，也预留了 python 等其他标记
        prefixes = ["```mermaid", "```python", "```javascript", "```xml", "```json", "```"]
        
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break # 只要匹配到一个前缀就跳出
        
        # 移除结尾的 ```
        if text.endswith("```"):
            text = text[:-3]
            
        return text.strip()
