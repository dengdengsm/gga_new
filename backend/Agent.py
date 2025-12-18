from abc import ABC, abstractmethod
from typing import List, Dict, Generator, Union, Optional
from openai import OpenAI
import os
from pathlib import Path  # 必须引入 Path

# --- 1. 定义数据结构 ---
Message = Dict[str, str]

# --- 2. 抽象接口 (Interface) ---
class abc_agent(ABC):
    @abstractmethod
    def chat(self, messages: List[Message], system_prompt: Optional[str] = None) -> str:
        pass

    @abstractmethod
    def chat_stream(self, messages: List[Message], system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        pass

# --- 3. 通用 OpenAI 协议实现 ---
class Agent(abc_agent):
    """
    通用 Agent，用于 DeepSeek 等标准模型
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, temperature: float = 0.7):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.temperature = temperature

    def chat(self, messages: List[Message], system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        final_msgs = []
        if system_prompt:
            final_msgs.append({"role": "system", "content": system_prompt})
        final_msgs.extend(messages)
        
        params = {
            "model": self.model_name,
            "messages": final_msgs,
            "temperature": self.temperature,
            "stream": False
        }
        
        # 标准 OpenAI 模型支持 json_object
        if json_mode:
            params["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            return f"{{\"error\": \"Error invoking model {self.model_name}: {str(e)}\"}}"

    def chat_stream(self, messages: List[Message], system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        final_msgs = []
        if system_prompt:
            final_msgs.append({"role": "system", "content": system_prompt})
        final_msgs.extend(messages)
        
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=final_msgs,
                temperature=self.temperature,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error in stream: {str(e)}"

# --- DeepSeek Config ---
API_KEY_deepseek = "sk-53ad620095534cae927007367eecf082" 
BASE_URL_deepseek = "https://api.deepseek.com"

class deepseek_agent(Agent):
    def __init__(self, model_name="deepseek-chat", api_key=None, base_url=None):
        final_key = api_key if api_key else API_KEY_deepseek
        final_url = base_url if base_url else BASE_URL_deepseek
        super().__init__(final_key, final_url, model_name, 0.0)


# --- Qwen Config (修复版) ---
API_KEY_qwen = "sk-3b009784a72d4d969c005e2afb2a7087"

class qwen_doc_agent:
    """
    专用于 Qwen-Long 的 Agent
    修复说明：将 fileid 和 system_prompt 拆分为两条消息，避免 400 Invalid File 错误
    """
    def __init__(self, model_name="qwen-long"):
        self.client = OpenAI(
            api_key=API_KEY_qwen,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model_name = model_name

    def chat(self, messages, system_prompt=None, file_path=None, json_mode=False):
        try:
            final_messages = []
            
            # --- 1. 文件处理 ---
            if file_path:
                print(f"📤 [QwenAgent] Uploading: {file_path} ...")
                file_object = self.client.files.create(
                    file=Path(file_path),
                    purpose="file-extract"
                )
                file_id = file_object.id
                
                # 关键修复：作为独立的一条 system 消息发送 fileid
                # 这样后端解析时就不会把后面的 prompt 误认为是 id 的一部分了
                final_messages.append({"role": "system", "content": f"fileid://{file_id}"})
                
                # 如果还有额外的 system_prompt，作为第二条 system 消息追加
                if system_prompt:
                    final_messages.append({"role": "system", "content": system_prompt})
            
            # 没有文件，只有 prompt 的情况
            elif system_prompt:
                final_messages.append({"role": "system", "content": system_prompt})

            # 2. 追加用户消息
            final_messages.extend(messages)

            # 3. 准备参数
            params = {
                "model": self.model_name,
                "messages": final_messages,
                "stream": False
            }
            
            # json_mode 对 qwen-long 暂时不加 response_format 以防兼容性问题

            # 4. 调用
            response = self.client.chat.completions.create(**params)
            content = response.choices[0].message.content
            
            # 清洗 markdown json 标记
            if json_mode and "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif json_mode and "```" in content: # 简单的 markdown 清洗
                content = content.split("```")[1].split("```")[0].strip()
            
            return content

        except Exception as e:
            print(f"❌ Qwen Agent Critical Error: {e}")
            # 打印详细错误信息以便调试
            if hasattr(e, 'body'):
                print(f"   -> Error Body: {e.body}")
            return "{}"