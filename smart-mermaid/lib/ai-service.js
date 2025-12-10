import { cleanText } from "./utils";
import { getAIConfig, getSavedPassword, getSelectedModel } from "./config-service";

// 定义后端地址常量
const BACKEND_URL = "http://localhost:8000";

/**
 * Sends text to AI API for processing and returns the generated Mermaid code
 * (非流式版本：等待后端完整处理完毕后一次性返回)
 */
export async function generateMermaidFromText(text, diagramType = "auto", onChunk = null) {
  if (!text) {
    return { mermaidCode: "", error: "请提供文本内容" };
  }

  const cleanedText = cleanText(text);
  
  // 获取配置 (虽然我们后端暂时主要用 text，但保持参数完整性)
  const aiConfig = getAIConfig();
  const accessPassword = getSavedPassword();
  const selectedModel = getSelectedModel();

  try {
    // 1. 发起标准的 POST 请求
    const response = await fetch(`${BACKEND_URL}/api/generate-mermaid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // 注意：这里不再需要 Accept: text/event-stream
      },
      body: JSON.stringify({
        text: cleanedText,
        diagramType,
        aiConfig,
        accessPassword,
        selectedModel
      }),
    });

    if (!response.ok) {
      // 尝试读取错误信息
      let errorMsg = "后端服务请求失败";
      try {
        const errData = await response.json();
        errorMsg = errData.message || errData.error || errorMsg;
      } catch (e) {}
      throw new Error(errorMsg);
    }

    // 2. 直接解析 JSON
    // Python 的 JSON 序列化会完美保留 \n 换行符
    const data = await response.json();
    
    // 检查后端返回的逻辑错误
    if (data.error) {
      return { mermaidCode: "", error: data.error };
    }

    // 3. 成功拿到代码
    // 如果之前在 page.js 里开了流式，onChunk 这里其实就没用了，
    // 但为了兼容，我们可以模拟一下“一次性推完”
    if (onChunk && data.mermaidCode) {
      onChunk(data.mermaidCode); 
    }

    return { mermaidCode: data.mermaidCode, error: null };

  } catch (error) {
    console.error("AI API Error:", error);
    return { 
      mermaidCode: "", 
      error: error.message || "与AI服务通信时出错" 
    };
  }
}

// 下面的函数暂时保持空实现，防止报错
export async function optimizeMermaidCode(mermaidCode, instruction = "") {
  return { optimizedCode: mermaidCode, error: "暂不支持" };
}

export async function fetchOptimizationSuggestions(mermaidCode) {
  return { suggestions: [], error: null };
}