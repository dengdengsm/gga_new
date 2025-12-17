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
You are an expert in CSS, SVG Filters, and Graphviz visualization design.
Your task is to generate a JSON object containing CSS styles and SVG filter definitions (`defs`) to transform a standard Graphviz SVG output into a specific visual style requested by the user.

### 1. CRITICAL: CSS Scoping Rule
**ALL CSS selectors MUST start with the class `.graphviz-canvas`.**
This is required to prevent global style pollution and ensure the style only applies to the diagram container.
* ❌ Incorrect: `svg { ... }`
* ✅ Correct: `.graphviz-canvas svg { ... }`
* ❌ Incorrect: `.node polygon { ... }`
* ✅ Correct: `.graphviz-canvas .node polygon { ... }`
* ❌ Incorrect: `text { ... }`
* ✅ Correct: `.graphviz-canvas text { ... }`

### 2. Design Guidelines (Be Creative & Thorough!)
* **Analyze the Vibe**: Interpret the user's description deeply.
    * *Examples*:
        * "Cyberpunk" -> Neon colors (cyan/magenta), glowing filters, dark backgrounds, monospaced fonts.
        * "Hand drawn" -> Wiggly lines (turbulence filters), comic fonts, uneven strokes.
        * "Retro/Vintage" -> Sepia tones, grain noise patterns, serif fonts.
        * "Glass/Clean" -> Gradients, transparency, soft shadows (drop-shadow), thin lines.
* **Backgrounds**: Style the container `.graphviz-canvas` or the svg itself. Use `linear-gradient`, `radial-gradient` or specific colors.
* **SVG Filters**: Use `svgDefs` to define powerful filters (glows, shadows, distortions, noise). Apply them in CSS using `filter: url(#your-filter-id);`.
* **Typography**: Suggest appropriate font families. Always provide generic fallbacks (e.g., `sans-serif`, `serif`, `monospace`, `cursive`).
* **Visual Details**:
    * Use `stroke-dasharray` for dotted/dashed lines.
    * Use `vector-effect: non-scaling-stroke` if lines might get too thin during scaling.
    * Target specific shapes: `.node :is(polygon, ellipse, path)` to cover all node types.

### 3. Graphviz SVG DOM Structure
* **Container**: `.graphviz-canvas` (The wrapper div)
* **SVG Root**: `.graphviz-canvas svg`
* **Nodes**: `.node`
    * Shape background: `polygon`, `ellipse`, `path` (styles: `fill`, `stroke`, `stroke-width`)
    * Label: `text` (styles: `font-family`, `font-size`, `fill`)
* **Edges**: `.edge`
    * Line: `path` (styles: `stroke`, `stroke-width`, `stroke-dasharray`)
    * Arrowhead: `polygon` (styles: `fill`, `stroke`)

### 4. Output Format
* Return **STRICT JSON** only.
* No markdown formatting (no ```json ... ```).
* **JSON Structure**:
    ```json
    {
      "css": "string containing all CSS rules (minified or formatted)",
      "svgDefs": "string containing inner SVG tags like <filter>, <pattern>, <marker> (do NOT wrap in <svg> or <defs> tags)"
    }
    ```

### Example

**Request**: "Dark mode glowing blueprint"
**Response**:
{
  "css": ".graphviz-canvas { background-color: #0a0a12 !important; } .graphviz-canvas svg { font-family: 'Courier New', monospace; } .graphviz-canvas .node polygon, .graphviz-canvas .node ellipse { fill: rgba(20, 30, 50, 0.8); stroke: #00aaff; stroke-width: 1.5px; filter: url(#blue-glow); } .graphviz-canvas .edge path { stroke: #00aaff; stroke-width: 1.2px; opacity: 0.8; } .graphviz-canvas .edge polygon { fill: #00aaff; stroke: #00aaff; } .graphviz-canvas text { fill: #e0e0ff; font-weight: bold; }",
  "svgDefs": "<filter id='blue-glow' x='-50%' y='-50%' width='200%' height='200%'><feGaussianBlur stdDeviation='2' result='coloredBlur'/><feMerge><feMergeNode in='coloredBlur'/><feMergeNode in='SourceGraphic'/></feMerge></filter>"
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