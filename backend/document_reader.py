import os
import requests
import tempfile
import shutil
from pathlib import Path
from urllib.parse import urlparse
from Agent import Agent  # 直接复用你的核心 Agent 类

class DocumentAnalyzer(Agent):
    """
    基于 Qwen-Long 的文档分析器，继承自通用 Agent。
    复用了父类的 client 和 chat 接口，增加了文件处理能力。
    """
    def __init__(self, api_key=None, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model_name="qwen-long"):
        # 优先读取环境变量，或者使用传入值
        final_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        
        # 调用父类构造函数，初始化 self.client
        super().__init__(
            api_key=final_key, 
            base_url=base_url, 
            model_name=model_name,
            temperature=0.1 # 文档分析需要严谨，建议低温度
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
                if url.endswith(".pdf"): filename += ".pdf"
                elif url.endswith(".docx"): filename += ".docx"
            
            temp_dir = tempfile.mkdtemp()
            local_path = os.path.join(temp_dir, filename)

            print(f"⬇️ [DocAnalyzer] Downloading from URL: {url}")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            return local_path, True 
        except Exception as e:
            raise Exception(f"Failed to download file: {str(e)}")

    def analyze(self, file_source: str, prompt: str = None) -> str:
        """
        Upload and analyze document.
        :param file_source: Local file path OR File URL
        :param prompt: User instruction (Optional). If None, uses default English prompt for diagram extraction.
        """
        # --- 1. Set Default English Prompt ---
        if not prompt:
            prompt = (
                "Please analyze this document carefully to extract core information suitable for creating technical diagrams "
                "(such as Flowcharts, Architecture Diagrams, Sequence Diagrams, Class Diagrams, etc.).\n\n"
                "Please focus on and structurally output the following content:\n"
                "1. Key Entities: Systems, modules, components, or roles, including their attributes.\n"
                "2. Relationships: Interactions, dependencies, associations, or data flows between entities.\n"
                "3. Process Logic: Detailed steps, decision points, branching logic, and conditions.\n"
                "4. Temporal Aspects: Any information involving sequences, phases, or lifecycles.\n\n"
                "Instruction: Remove irrelevant decorative text and marketing filler. "
                "Output a clear, structured logical summary that can be directly used as context for generating Mermaid.js code."
            )

        local_path = file_source
        is_temp = False
        file_id = None

        try:
            # --- 2. Handle File Source ---
            if self._is_url(file_source):
                local_path, is_temp = self._download_file(file_source)
            else:
                if not os.path.exists(local_path):
                    return f"Error: File not found at {local_path}"

            # --- 3. Upload File (Qwen File-Extract) ---
            file_path = Path(local_path)
            print(f"📤 [DocAnalyzer] Uploading: {file_path.name}...")
            
            # Use parent client for upload
            file_object = self.client.files.create(
                file=file_path,
                purpose="file-extract"
            )
            file_id = file_object.id
            print(f"✅ [DocAnalyzer] File ID: {file_id}")

            # --- 4. Execute Chat ---
            # Qwen-long protocol: system prompt contains fileid://
            system_instruction = f"fileid://{file_id}"
            
            # Call parent chat method
            response_content = self.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_instruction
            )

            return response_content

        except Exception as e:
            return f"Error in document analysis: {str(e)}"
        
        finally:
            # --- 5. Cleanup ---
            if is_temp and local_path and os.path.exists(local_path):
                try:
                    shutil.rmtree(os.path.dirname(local_path))
                except OSError:
                    pass
            
            # 可选：如果不需要保留云端文件，可以在这里调用 self.client.files.delete(file_id)
            # 但 Qwen 上下文往往有时效性，保留着也无妨，视需求而定

if __name__ == "__main__":
    # 测试代码
    # 需要环境变量 DASHSCOPE_API_KEY
    analyzer = DocumentAnalyzer()
    res = analyzer.analyze("https://pdfobject.com/pdf/sample.pdf", "这个文档讲了什么？")
    print("\nResult:", res)