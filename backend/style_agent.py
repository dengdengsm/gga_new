import json
import re
from typing import Dict, Optional
from Agent import deepseek_agent

class StyleAgent:
    """
    专门用于生成 Graphviz CSS 样式和 SVG 滤镜的 Agent。
    利用 LLM 的知识生成创意性的 CSS 选择器和 SVG Filter 定义。
    """
    
    SYSTEM_PROMPT = """
You are an expert in CSS, SVG Filters, and Graphviz visualization. 
Your task is to generate a JSON object containing CSS styles and SVG filter definitions (`defs`) to transform a standard Graphviz SVG output into a specific visual style requested by the user.

### Graphviz SVG Structure Knowledge:
1. **Container**: The SVG usually has a white background polygon (often the first `polygon` inside `.graph`).
2. **Nodes**: Elements with class `.node`. They contain:
   - Geometry: `polygon`, `ellipse`, `path` (styles: `stroke`, `fill`, `stroke-width`).
   - Text: `text` (styles: `font-family`, `font-size`, `fill`).
3. **Edges**: Elements with class `.edge`. They contain:
   - Line: `path` (styles: `stroke`, `stroke-width`, `stroke-dasharray`).
   - Arrowhead: `polygon` (styles: `fill`, `stroke`).
4. **Clusters**: Elements with class `.cluster`.

### Instructions:
1. **Analyze the user's description** (e.g., "Hand drawn", "Cyberpunk", "Blueprint", "Vintage Paper").
2. **Generate `css`**:
   - Write CSS rules to style these SVG elements (`.node polygon`, `.edge path`, `text`, etc.).
   - Use `!important` to override inline SVG attributes if necessary.
   - You CAN use SVG filters defined in `svgDefs` by referencing them (e.g., `filter: url(#my-filter-id);`).
3. **Generate `svgDefs`**:
   - Write valid SVG `<filter>`, `<pattern>`, or `<marker>` definitions inside a single string.
   - Ensure IDs are unique (e.g., `id="glow-filter"`) and referenced correctly in the CSS.
   - **Crucial**: Do not include the `<defs>` or `<svg>` wrapping tags, just the inner filter content.
4. **Output Format**:
   - Return STRICT JSON. No markdown formatting (no ```json ... ```).
   - Structure: `{"css": "...", "svgDefs": "..."}`

### Examples:

**Request**: "Hand drawn sketch style"
**Response**:
{
  "css": ".node polygon, .node ellipse { fill: #fff; stroke: #333; stroke-width: 2px; filter: url(#sketch); } .edge path { stroke: #333; stroke-width: 2px; filter: url(#sketch); } text { font-family: 'Comic Sans MS', cursive; fill: #333; } .graph > polygon { fill: transparent; }",
  "svgDefs": "<filter id='sketch' x='-20%' y='-20%' width='140%' height='140%'><feTurbulence type='fractalNoise' baseFrequency='0.03' numOctaves='3' result='noise'/><feDisplacementMap in='SourceGraphic' in2='noise' scale='3' xChannelSelector='R' yChannelSelector='G'/></filter>"
}
"""

    def __init__(self,model_name:str = "deepseek-chat"):
        """
        :param agent: 后端 Agent 实例 (需继承自 backend.Agent.abc_agent，支持 chat 方法)
        """
        self.llm = deepseek_agent(model_name=model_name)
        

    def generate_style(self, description: str) -> Dict[str, str]:
        """
        根据用户描述生成 CSS 和 SVG Defs
        :param description: 用户输入的风格描述 (例如: "赛博朋克霓虹风格")
        :return: 包含 'css' 和 'svgDefs' 的字典
        """
        messages = [
            {"role": "user", "content": f"Generate a Graphviz style for: {description}"}
        ]

        # 调用 Agent，开启 json_mode 以确保返回结构化数据
        response_text = self.llm.chat(
            messages=messages, 
            system_prompt=self.SYSTEM_PROMPT, 
            json_mode=True
        )

        return self._clean_and_parse_json(response_text)

    def _clean_and_parse_json(self, response_text: str) -> Dict[str, str]:
        """
        清洗并解析 LLM 返回的 JSON 字符串
        """
        # 1. 尝试直接解析
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 2. 如果包含 Markdown 代码块，尝试提取
        try:
            # 匹配 ```json {...} ``` 或 ``` {...} ```
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            
            # 3. 兜底：尝试提取最外层的 {}
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
                
        except Exception as e:
            print(f"Error parsing style JSON: {e}")
            
        # 4. 解析失败返回空对象或错误信息
        return {
            "css": "", 
            "svgDefs": "", 
            "error": "Failed to generate valid style JSON from AI response."
        }