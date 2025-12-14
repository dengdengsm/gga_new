import { cleanText } from "./utils";
import { getAIConfig, getSavedPassword, getSelectedModel } from "./config-service";

// 定义后端地址常量
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Sends text to AI API for processing and returns the generated Mermaid code
 * (非流式版本：等待后端完整处理完毕后一次性返回)
 * @param {string} text - User query
 * @param {string} diagramType - Type of diagram
 * @param {function} onChunk - Streaming callback
 * @param {boolean} useGraph - 是否使用知识图谱模式
 * @param {boolean} useFileContext - 【新增】是否依赖已上传文件作为上下文
 */
export async function generateMermaidFromText(text, diagramType = "auto", onChunk = null, useGraph = true, useFileContext = true) {
  if (!text) {
    return { mermaidCode: "", error: "请提供文本内容" };
  }

  const cleanedText = cleanText(text);
  
  // 获取配置
  const aiConfig = getAIConfig();
  const accessPassword = getSavedPassword();
  const selectedModel = getSelectedModel();

  try {
    // 1. 发起标准的 POST 请求
    const response = await fetch(`${BACKEND_URL}/api/generate-mermaid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text: cleanedText,
        diagramType,
        aiConfig,
        accessPassword,
        selectedModel,
        useGraph,
        useFileContext // 【新增】传递参数给后端
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
    const data = await response.json();
    
    // 检查后端返回的逻辑错误
    if (data.error) {
      return { mermaidCode: "", error: data.error };
    }

    // 3. 成功拿到代码
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