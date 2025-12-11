"use client";

// 默认指向后端地址，生产环境可配置环境变量
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

/**
 * 获取当前项目的历史记录
 */
export async function getHistory() {
  try {
    const res = await fetch(`${API_URL}/history`, {
      cache: 'no-store' // 确保不缓存，获取最新数据
    });
    if (!res.ok) {
      console.warn("Failed to fetch history:", res.statusText);
      return [];
    }
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (error) {
    console.error("Error fetching history:", error);
    return [];
  }
}

/**
 * 添加一条历史记录
 * @param {object} entry - { query, code, diagramType }
 */
export async function addHistoryEntry(entry) {
  try {
    const res = await fetch(`${API_URL}/history`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(entry),
    });
    
    if (!res.ok) {
      throw new Error("Failed to save history entry");
    }
    
    return await res.json();
  } catch (error) {
    console.error("Error adding history entry:", error);
    return null;
  }
}

/**
 * 删除指定 ID 的历史记录
 */
export async function deleteHistoryEntry(id) {
  try {
    const res = await fetch(`${API_URL}/history/${id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error("Failed to delete history entry");
    }
    return true;
  } catch (error) {
    console.error("Error deleting history entry:", error);
    return false;
  }
}

/**
 * 清空当前项目的所有历史记录
 */
export async function clearHistory() {
  try {
    const res = await fetch(`${API_URL}/history`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error("Failed to clear history");
    }
    return true;
  } catch (error) {
    console.error("Error clearing history:", error);
    return false;
  }
}