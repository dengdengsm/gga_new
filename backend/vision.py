import base64
import mimetypes
import os
from Agent import Agent
# API 配置
API_KEY_QWEN = "sk-3b009784a72d4d969c005e2afb2a7087"
BASE_URL_QWEN = "https://dashscope.aliyuncs.com/compatible-mode/v1"

class QwenVisionAgent(Agent):
    def __init__(self, model_name: str = "qwen-vl-max"):
        super().__init__(api_key=API_KEY_QWEN, base_url=BASE_URL_QWEN, model_name=model_name)
        
        # --- 核心修改：更强力的 Markdown 逻辑分析提示词 ---
        self.vision_system_prompt = (
            "You are a Visual Logic Analyst. Your goal is to deconstruct the image into structured data using Markdown. "
            "Do not output conversational filler. Follow this strict format:\n\n"
            
            "### 1. Object Inventory\n"
            "- List every distinct key object or entity visible in the image.\n"
            "- Format: **[Object Name]**: [Brief visual description (color, position, state)].\n\n"
            
            "### 2. Visual Logic & Interaction\n"
            "Analyze how these objects relate to each other. Focus on:\n"
            "- **Spatial Logic**: Relative positions (e.g., 'A is supporting B', 'X is shadowing Y').\n"
            "- **Causal/Action Logic**: Who is doing what to whom? What is the cause and effect?\n"
            "- **Semantic Logic**: What is the symbolic or functional connection between the objects?\n\n"
            
            "### 3. The Logical Full Picture\n"
            "Synthesize the above into a coherent summary of what is happening and the underlying intent or narrative of the scene."
        )

    def _encode_image_to_data_url(self, image_path: str) -> str:
        """读取本地图片转 Base64"""
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"
        try:
            with open(image_path, "rb") as image_file:
                base64_encoded_data = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:{mime_type};base64,{base64_encoded_data}"
        except Exception as e:
            raise ValueError(f"无法读取图片: {image_path}, 错误: {e}")

    def analyze_image(self, image_input: str, user_query: str = "Please analyze the image structure and logic.") -> str:
        """
        :param image_input: URL 或 本地路径
        :param user_query: 用户指令 (默认为空，完全依赖 System Prompt 的结构化指令)
        """
        image_url_content = ""

        # 1. 路径/URL 识别
        if image_input.strip().startswith(("http://", "https://")):
            image_url_content = image_input
        else:
            if os.path.exists(image_input):
                image_url_content = self._encode_image_to_data_url(image_input)
            else:
                return f"**Error**: File not found at path `{image_input}`"

        # 2. 构造 payload
        vision_content = [
            {
                "type": "image_url",
                "image_url": {"url": image_url_content},
            },
            {"type": "text", "text": user_query},
        ]

        messages = [{"role": "user", "content": vision_content}]

        # 3. 发送请求
        return self.chat(messages, system_prompt=self.vision_system_prompt)

# --- 测试代码 ---
if __name__ == "__main__":
    agent = QwenVisionAgent()
    
    # 换成你的本地图片路径
    img_path = "./test.png" 
    
    if os.path.exists(img_path):
        print(f"正在分析图片逻辑: {img_path} ...")
        # 直接打印结果，Markdown 格式会很清晰
        print(agent.analyze_image(img_path))
    else:
        # 如果没有本地图，用个网图测试下效果
        url = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"
        print("正在分析网络图片...")
        print(agent.analyze_image(url))