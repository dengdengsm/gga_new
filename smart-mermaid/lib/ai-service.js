import { cleanText } from "./utils";
import { getAIConfig, getSavedPassword, getSelectedModel } from "./config-service";
import { getGlobalRules } from "./preference-service";

// 定义后端地址常量
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Sends text to AI API for processing and returns the generated Mermaid code
 * (非流式版本：等待后端完整处理完毕后一次性返回)
 * @param {string} text - User query
 * @param {string} diagramType - Type of diagram
 * @param {function} onChunk - (已废弃，传 null)
 * @param {boolean} useGraph - 是否使用知识图谱模式
 * @param {boolean} useFileContext - 是否依赖已上传文件作为上下文
 */
export async function generateMermaidFromText(text, diagramType = "auto", onChunk = null, useGraph = true, useFileContext = true, richness = 0.5) {
  if (!text) {
    return { mermaidCode: "", error: "请提供文本内容" };
  }

  // 1. 获取并清理用户输入
  const cleanedText = cleanText(text);
  
  // 2. 获取全局偏好规则 (Global Rules)
  // 这些是用户勾选了"记住并应用到所有生成"的建议
  const globalRules = getGlobalRules();
  
  // 3. 构造最终发送给 AI 的文本 Prompt
  // 使用明确的分隔符和提示语，防止 AI 混淆“绘图内容”和“绘图风格/约束”
  let finalPrompt = cleanedText;
  
  if (globalRules && globalRules.length > 0) {
    const rulesList = globalRules.map((rule, index) => `${index + 1}. ${rule}`).join('\n');
    
    finalPrompt = `${cleanedText}

==================================================
【用户全局偏好设置 (Global User Preferences)】
注意：以下是用户设置的全局绘图约束或风格要求，请在生成代码时务必遵守这些规则，它们具有高优先级：
(Please apply the following global constraints/preferences to the generated diagram)

${rulesList}
==================================================`;
  }
  
  // 获取配置
  const aiConfig = getAIConfig();
  const accessPassword = getSavedPassword();
  const selectedModel = getSelectedModel();

  try {
    // 4. 发起 POST 请求
    const response = await fetch(`${BACKEND_URL}/api/generate-mermaid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text: finalPrompt, // 发送拼接后的 Prompt
        diagramType,
        aiConfig,
        accessPassword,
        selectedModel,
        useGraph,
        useFileContext,
        richness
      }),
    });

    if (!response.ok) {
      let errorMsg = "后端服务请求失败";
      try {
        const errData = await response.json();
        errorMsg = errData.message || errData.error || errorMsg;
      } catch (e) {}
      throw new Error(errorMsg);
    }

    const data = await response.json();
    
    if (data.error) {
      return { mermaidCode: "", error: data.error };
    }

    // 虽然移除了流式 UI 逻辑，但为了兼容接口定义，如果传了 onChunk 还是调用一下
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

/**
 * 发送优化请求给后端
 * @param {string} mermaidCode - 当前的 Mermaid 代码
 * @param {string} instruction - 用户的优化指令（已包含全局偏好）
 * @param {function} onChunk - (可选) 流式回调
 */
export async function optimizeMermaidCode(mermaidCode, instruction = "", onChunk = null) {
  if (!mermaidCode) {
    return { optimizedCode: "", error: "未提供代码" };
  }
  if (!instruction) {
    return { optimizedCode: mermaidCode, error: null }; // 无指令则不修改
  }

  const aiConfig = getAIConfig();
  const accessPassword = getSavedPassword();
  const selectedModel = getSelectedModel();

  try {
    // 调用专门的优化接口
    const response = await fetch(`${BACKEND_URL}/api/optimize-mermaid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        code: mermaidCode,
        instruction: instruction, // 这里接收的 instruction 应该已经是前端拼接好的包含【当前建议】+【全局偏好】的完整文本
        aiConfig,
        accessPassword,
        selectedModel
      }),
    });

    if (!response.ok) {
      let errorMsg = "优化服务请求失败";
      try {
        const errData = await response.json();
        errorMsg = errData.message || errData.error || errorMsg;
      } catch (e) {}
      throw new Error(errorMsg);
    }

    const data = await response.json();

    if (data.error) {
      return { optimizedCode: "", error: data.error };
    }

    return { optimizedCode: data.optimizedCode || data.mermaidCode, error: null };

  } catch (error) {
    console.error("Optimize API Error:", error);
    return { 
      optimizedCode: "", 
      error: error.message || "优化请求出错" 
    };
  }
}

// 建议获取函数，改为从本地服务获取，这里保留空壳或者直接废弃（因为前端已改用 preference-service）
// 为了兼容性，如果其他地方还在调用，可以返回空
export async function fetchOptimizationSuggestions(mermaidCode) {
  return { suggestions: [], error: null };
}