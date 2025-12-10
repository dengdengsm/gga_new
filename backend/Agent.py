from abc import ABC, abstractmethod
from typing import List, Dict, Generator, Union, Optional
from openai import OpenAI
import os

# --- 1. 定义数据结构 ---
# 为了通用性，我们采用标准的 OpenAI 消息格式: [{"role": "user", "content": "..."}]
Message = Dict[str, str]

# --- 2. 抽象接口 (Interface) ---
class abc_agent(ABC):
    """
    通用大模型接口抽象类
    所有具体的模型实现都必须继承此类
    """
    
    @abstractmethod
    def chat(self, messages: List[Message], system_prompt: Optional[str] = None) -> str:
        """
        同步对话接口
        :param messages: 历史对话列表
        :param system_prompt: 系统提示词（可选，如果这里传入，会覆盖messages里的system）
        :param json_mode: 是否强制输出 JSON 格式
        :return: 模型生成的完整文本
        """
        pass

    @abstractmethod
    def chat_stream(self, messages: List[Message], system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        """
        流式对话接口 (用于打字机效果)
        :return: 生成器，逐个返回字符/Token
        """
        pass

# --- 3. 通用 OpenAI 协议实现 (核心) ---
class Agent(abc_agent):
    """
    基于 OpenAI SDK 协议的通用 Agent。
    支持 DeepSeek, Qwen, Moonshot, ChatGPT 等所有兼容 OpenAI 格式的模型。
    """
    
    def __init__(self, api_key: str, base_url: str, model_name: str, temperature: float = 0.7):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.temperature = temperature

    def update_config(self, api_key: str, base_url: str, model_name: Optional[str] = None):
        """
        【热更新】运行时修改 Agent 的配置
        """
        if api_key and base_url:
            # print(f"🔄 [Agent] 正在热更新 LLM 配置... (Target: {base_url})")
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        
        if model_name:
            self.model_name = model_name

    def _prepare_messages(self, messages: List[Message], system_prompt: Optional[str]) -> List[Message]:
        """内部工具：处理 System Prompt"""
        if system_prompt:
            return [{"role": "system", "content": system_prompt}] + messages
        return messages

    def chat(self, messages: List[Message], system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        final_msgs = self._prepare_messages(messages, system_prompt)
        
        # 构造参数字典
        params = {
            "model": self.model_name,
            "messages": final_msgs,
            "temperature": self.temperature,
            "stream": False
        }
        
        # 核心修改：如果是 JSON 模式，添加 response_format 参数
        if json_mode:
            params["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            return f"{{\"error\": \"Error invoking model {self.model_name}: {str(e)}\"}}"

    def chat_stream(self, messages: List[Message], system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        final_msgs = self._prepare_messages(messages, system_prompt)
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

# --- 默认开发配置 (可被热更新覆盖) ---
API_KEY_deepseek = "sk-53ad620095534cae927007367eecf082" 
BASE_URL_deepseek = "https://api.deepseek.com"

class deepseek_agent(Agent):
    def __init__(self, model_name, api_key=None, base_url=None):
        # 优先使用传入的配置，否则回退到默认常量
        final_key = api_key if api_key else API_KEY_deepseek
        final_url = base_url if base_url else BASE_URL_deepseek
        
        super().__init__(final_key, final_url, model_name, 0.0)