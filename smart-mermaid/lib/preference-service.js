"use client";

const HISTORY_KEY = "mermaid_opt_history";
const GLOBAL_RULES_KEY = "mermaid_global_rules";
const MAX_HISTORY_SIZE = 50;

/**
 * 获取历史建议列表
 * @returns {string[]}
 */
export function getSuggestionHistory() {
  if (typeof window === 'undefined') return [];
  
  try {
    const history = localStorage.getItem(HISTORY_KEY);
    return history ? JSON.parse(history) : [];
  } catch (e) {
    console.error("Failed to parse suggestion history:", e);
    return [];
  }
}

/**
 * 添加建议到历史记录（去重，最新的排前面）
 * @param {string} text 
 */
export function addSuggestionToHistory(text) {
  if (!text || typeof window === 'undefined') return;
  const trimmedText = text.trim();
  if (!trimmedText) return;

  try {
    const history = getSuggestionHistory();
    // 移除已存在的相同条目，确保不重复且新的在最前
    const newHistory = [trimmedText, ...history.filter(item => item !== trimmedText)];
    
    // 限制长度
    if (newHistory.length > MAX_HISTORY_SIZE) {
      newHistory.length = MAX_HISTORY_SIZE;
    }

    localStorage.setItem(HISTORY_KEY, JSON.stringify(newHistory));
  } catch (e) {
    console.error("Failed to save suggestion history:", e);
  }
}

/**
 * 获取全局优选规则列表（需要每次生成时自动应用的规则）
 * @returns {string[]}
 */
export function getGlobalRules() {
  if (typeof window === 'undefined') return [];

  try {
    const rules = localStorage.getItem(GLOBAL_RULES_KEY);
    return rules ? JSON.parse(rules) : [];
  } catch (e) {
    console.error("Failed to parse global rules:", e);
    return [];
  }
}

/**
 * 添加一条全局规则
 * @param {string} text 
 */
export function addGlobalRule(text) {
  if (!text || typeof window === 'undefined') return;
  const trimmedText = text.trim();
  if (!trimmedText) return;

  try {
    const rules = getGlobalRules();
    if (!rules.includes(trimmedText)) {
      const newRules = [...rules, trimmedText];
      localStorage.setItem(GLOBAL_RULES_KEY, JSON.stringify(newRules));
    }
  } catch (e) {
    console.error("Failed to save global rule:", e);
  }
}

/**
 * 移除一条全局规则
 * @param {string} text 
 */
export function removeGlobalRule(text) {
  if (!text || typeof window === 'undefined') return;
  
  try {
    const rules = getGlobalRules();
    const newRules = rules.filter(r => r !== text);
    localStorage.setItem(GLOBAL_RULES_KEY, JSON.stringify(newRules));
  } catch (e) {
    console.error("Failed to remove global rule:", e);
  }
}

/**
 * 清空所有历史建议
 */
export function clearSuggestionHistory() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(HISTORY_KEY);
}

/**
 * 清空所有全局规则
 */
export function clearGlobalRules() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(GLOBAL_RULES_KEY);
}

/**
 * [新增] 从历史记录中移除指定建议
 * @param {string} text 
 */
export function removeSuggestionFromHistory(text) {
  if (!text || typeof window === 'undefined') return;
  
  try {
    const history = getSuggestionHistory();
    const newHistory = history.filter(item => item !== text);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(newHistory));
  } catch (e) {
    console.error("Failed to remove suggestion:", e);
  }
}