"use client";

// 默认指向后端地址
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

/**
 * 获取项目列表及当前项目
 * 返回格式: { projects: ["default", "p1"], current: "default" }
 */
export async function getProjects() {
  try {
    const res = await fetch(`${API_URL}/projects`, { 
      cache: 'no-store' 
    });
    if (!res.ok) throw new Error("Failed to fetch projects");
    return await res.json();
  } catch (error) {
    console.error("Error fetching projects:", error);
    // 发生错误时返回兜底数据
    return { projects: ["default"], current: "default" };
  }
}

/**
 * 创建新项目
 */
export async function createProject(name) {
  try {
    const res = await fetch(`${API_URL}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    return await res.json();
  } catch (error) {
    console.error("Error creating project:", error);
    return { status: "error", message: error.message };
  }
}

/**
 * 切换项目
 */
export async function switchProject(name) {
  try {
    const res = await fetch(`${API_URL}/projects/switch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    return await res.json();
  } catch (error) {
    console.error("Error switching project:", error);
    return { status: "error", message: error.message };
  }
}