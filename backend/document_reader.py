import os
import requests
import tempfile
import shutil
import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from Agent import Agent

class DocumentAnalyzer(Agent):
    """
    统一文档分析器 (Unified Reader)
    整合了文档阅读 (Qwen-Long) 和 视觉分析 (Qwen-VL) 的能力。
    - 对于 PDF/Word/Text: 使用 Qwen-Long 进行文件内容提取与分析。
    - 对于 Images: 使用 Qwen-VL-Max 进行视觉逻辑识别。
    """
    def __init__(self, api_key=None, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"):
        # 默认 Key (生产环境建议走环境变量，这里保留你原有的硬编码方便调试)
        final_key = "sk-3b009784a72d4d969c005e2afb2a7087"
        
        # 基础初始化：默认作为文档分析器启动 (Qwen-Long)
        super().__init__(
            api_key=final_key, 
            base_url=base_url, 
            model_name="qwen-long", 
            temperature=0.1 # 分析任务需要严谨，低温度
        )
        
        # 定义视觉模型名称，用于在分析图片时临时切换
        self.vision_model = "qwen-vl-max"

        # --- 预定义 System Prompts ---
        # 1. 视觉分析提示词 (移植自原 vision.py)
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

    def _is_url(self, path_string):
        """判断字符串是否为 URL"""
        try:
            result = urlparse(path_string)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def _download_file(self, url):
        """
        下载 URL 文件到临时目录
        :return: (临时文件路径, 是否需要清理的标记)
        """
        try:
            path = urlparse(url).path
            filename = os.path.basename(path)
            if not filename:
                filename = "temp_downloaded_doc"
                # 尝试根据 Content-Type 猜后缀，这里简单处理
                if url.endswith(".pdf"): filename += ".pdf"
                elif url.endswith(".png"): filename += ".png"
                elif url.endswith(".jpg") or url.endswith(".jpeg"): filename += ".jpg"
            
            temp_dir = tempfile.mkdtemp()
            local_path = os.path.join(temp_dir, filename)

            print(f"⬇️ [UnifiedReader] Downloading from URL: {url}")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            return local_path, True 
        except Exception as e:
            raise Exception(f"Failed to download file: {str(e)}")

    def _encode_image(self, image_path: str) -> str:
        """读取本地图片转 Base64 (用于 Vision API)"""
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"
        try:
            with open(image_path, "rb") as image_file:
                base64_encoded_data = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:{mime_type};base64,{base64_encoded_data}"
        except Exception as e:
            raise ValueError(f"无法读取图片: {image_path}, 错误: {e}")

    def analyze(self, file_source: str, prompt: str = None, max_token_limit: int = None) -> str:
        """
        统一分析入口 (Unified Entry Point)
        :param file_source: 本地文件路径 或 文件 URL
        :param prompt: 用户指令 (可选)。若为空，则使用内置默认提示词。
        :param max_token_limit: (新增) 最大输出长度限制 (Token/字数)，用于防止多文件时上下文溢出。
        """
        local_path = file_source
        is_temp = False
        file_id = None

        # --- 0. 构造字数限制指令 ---
        limit_instruction = ""
        if max_token_limit:
            limit_instruction = (
                f"\n\n[STRICT CONSTRAINT]: Please keep your response concise. "
                f"The total length MUST be under {max_token_limit} tokens/words. "
                "Focus ONLY on the most critical logic and omit verbose descriptions."
            )

        try:
            # --- 1. 处理文件源 (URL vs Local) ---
            if self._is_url(file_source):
                local_path, is_temp = self._download_file(file_source)
            else:
                if not os.path.exists(local_path):
                    return f"Error: File not found at {local_path}"

            # --- 2. 智能分流 (Image vs Document) ---
            mime_type, _ = mimetypes.guess_type(local_path)
            if not mime_type: mime_type = ""
            
            is_image = mime_type.startswith("image/")
            
            # ====== 分支 A: 视觉分析 (Vision) ======
            if is_image:
                print(f"👁️ [UnifiedReader] Detected Image format: {os.path.basename(local_path)}")
                
                # 准备 Prompt (如果用户没给，就用默认的逻辑提取指令)
                user_query = prompt if prompt else "Please analyze the image structure and logic."
                final_query = user_query + limit_instruction
                
                # 构造 Payload
                img_data = self._encode_image(local_path)
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": img_data}},
                            {"type": "text", "text": final_query},
                        ]
                    }
                ]
                
                # 临时切换到 Vision 模型
                original_model = self.model_name
                self.model_name = self.vision_model
                try:
                    # 使用专门的 Vision System Prompt
                    response = self.chat(messages, system_prompt=self.vision_system_prompt)
                    return response
                finally:
                    self.model_name = original_model # 恢复原状
            
            # ====== 分支 B: 文档分析 (File Extract) ======
            else:
                print(f"📄 [UnifiedReader] Detected Document format: {os.path.basename(local_path)}")
                
                # 准备 Prompt
                if not prompt:
                    prompt = (
                        "Please analyze this document carefully to extract core information suitable for creating technical diagrams.\n"
                        "Focus on:\n"
                        "1. Key Entities & Roles\n"
                        "2. Relationships & Interactions\n"
                        "3. Process Logic & Conditions\n"
                        "Instruction: Remove irrelevant decorative text."
                    )
                
                final_prompt = prompt + limit_instruction

                # 上传文件 (Qwen-Long file-extract 协议)
                file_path = Path(local_path)
                print(f"📤 [UnifiedReader] Uploading to DashScope: {file_path.name}...")
                
                file_object = self.client.files.create(
                    file=file_path,
                    purpose="file-extract"
                )
                file_id = file_object.id
                print(f"✅ [UnifiedReader] File ID: {file_id}")

                # Qwen-Long 需要在 system prompt 中注入 fileid
                system_instruction = f"fileid://{file_id}"
                
                response_content = self.chat(
                    messages=[{"role": "user", "content": final_prompt}],
                    system_prompt=system_instruction
                )

                return response_content

        except Exception as e:
            print(f"❌ [UnifiedReader] Error: {str(e)}")
            return f"Error in unified analysis: {str(e)}"
        
        finally:
            # --- 3. 清理资源 ---
            if is_temp and local_path and os.path.exists(local_path):
                try:
                    shutil.rmtree(os.path.dirname(local_path))
                    print(f"🧹 [UnifiedReader] Cleaned up temp files.")
                except OSError as e:
                    print(f"⚠️ [UnifiedReader] Cleanup failed: {e}")
            
            # 注意：DashScope 的云端文件通常会自动过期或需要显式删除，视需求可在此调用 self.client.files.delete(file_id)

if __name__ == "__main__":
    # --- 测试代码 ---
    # 确保你设置了环境变量或在类里硬编码了 Key
    analyzer = DocumentAnalyzer()
    
    print("\n--- Test 1: Image Analysis (Vision) ---")
    # 找一个本地图片路径测试，或者用网图
    img_test = "./test_flowchart.png" 
    if os.path.exists(img_test):
        res_img = analyzer.analyze(img_test, prompt="What is the flow described here?", max_token_limit=200)
        print("Image Result:\n", res_img)
    else:
        print("Skipping local image test (file not found).")

    print("\n--- Test 2: PDF Analysis (Doc) ---")
    pdf_url = "https://pdfobject.com/pdf/sample.pdf"
    res_doc = analyzer.analyze(pdf_url, prompt="Summarize this PDF.", max_token_limit=100)
    print("PDF Result:\n", res_doc)