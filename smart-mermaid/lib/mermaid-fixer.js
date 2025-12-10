import { getAIConfig, getSavedPassword, getSelectedModel } from "./config-service";

const BACKEND_URL = "http://localhost:8000";

export async function autoFixMermaidCode(mermaidCode, errorMessage = null, onChunk = null) {
  if (!mermaidCode || typeof mermaidCode !== 'string') {
    return { fixedCode: mermaidCode, error: "无效的代码输入" };
  }

  try {
    const aiConfig = getAIConfig();
    const accessPassword = getSavedPassword();
    const selectedModel = getSelectedModel();

    // --- 核心修改：直连后端 ---
    const response = await fetch(`${BACKEND_URL}/api/fix-mermaid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mermaidCode,
        errorMessage,
        aiConfig,
        accessPassword,
        selectedModel
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "修复代码时出错");
    }

    // --- 使用和 ai-service 一样的 SSE 解析逻辑 (这就统一了) ---
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullFixedCode = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const events = chunk.split("\n\n").filter(Boolean);

      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith("data:")) continue;
        const payloadStr = line.slice(5).trim();
        
        try {
          const payload = JSON.parse(payloadStr);
          if (payload.type === 'chunk' && payload.data) {
            if (onChunk) onChunk(payload.data);
          } else if (payload.type === 'final') {
            fullFixedCode = payload.data;
          }
        } catch (e) { console.warn(e); }
      }
    }

    return {
      fixedCode: fullFixedCode || mermaidCode,
      error: null
    };
  } catch (error) {
    console.error("AI修复错误:", error);
    return {
      fixedCode: mermaidCode,
      error: error.message || "修复代码时发生未知错误"
    };
  }
}

// toggleMermaidDirection 函数保持不变...
export function toggleMermaidDirection(mermaidCode) {
  // ... (保持原样)
  if (!mermaidCode) return mermaidCode;
  return mermaidCode.replace(/(flowchart|graph)\s+(TD|TB|LR|RL)/gi, (_, type, direction) => {
    const newDirection = (direction.toUpperCase() === 'TD' || direction.toUpperCase() === 'TB') ? 'LR' : 'TD';
    return `${type} ${newDirection}`;
  });
}