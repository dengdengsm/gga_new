import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Cleans text input for better AI processing
 * @param {string} text - The input text to clean
 * @returns {string} - Cleaned text
 */
export function cleanText(text) {
  if (!text) return "";
  
  // Remove excessive whitespace
  let cleanedText = text.replace(/\s+/g, " ");
  
  // Trim leading/trailing whitespace
  cleanedText = cleanedText.trim();
  
  return cleanedText;
}

/**
 * Counts characters in a string
 * @param {string} text - Text to count
 * @returns {number} - Character count
 */
export function countCharacters(text) {
  return text ? text.length : 0;
}

/**
 * Validates if text is within the character limit
 * @param {string} text - Text to validate
 * @param {number} limit - Maximum character limit
 * @returns {boolean} - Whether text is within limit
 */
export function isWithinCharLimit(text, limit) {
  return countCharacters(text) <= limit;
}

/**
 * Formats byte size to human readable format
 * @param {number} bytes - Size in bytes
 * @returns {string} - Formatted size (e.g., "2.5 MB")
 */
export function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

/**
 * Truncates text to a specific length with ellipsis
 * @param {string} text - Text to truncate
 * @param {number} length - Maximum length
 * @returns {string} - Truncated text
 */
export function truncateText(text, length = 100) {
  if (!text) return "";
  if (text.length <= length) return text;
  
  return text.substring(0, length) + "...";
}

/**
 * Copies text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} - Success status
 */
export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    console.error("Failed to copy text:", error);
    return false;
  }
}

/**
 * Parses Mermaid code to extract nodes (ID and Label)
 * Primarily supports Flowchart syntax
 * @param {string} code - The Mermaid code
 * @returns {Array<{id: string, label: string}>} - List of nodes
 */
export function parseMermaidNodes(code) {
  if (!code) return [];
  
  const nodes = new Map();
  
  // Clean comments
  const cleanCode = code.replace(/%%.*$/gm, '');

  // Regex to match node definitions in Flowcharts
  // Matches patterns like: id[Label], id(Label), id{Label}, id((Label)), etc.
  // Group 1: ID
  // Group 2: Quote (optional)
  // Group 3: Label content
  const regex = /([a-zA-Z0-9_\-]+)\s*(?:\[|\[\[|\(|\[\(|\(\(|>|\{|\{\{|\[\/|\[\\)\s*(["']?)(.*?)\2\s*(?:\]|\]\]|\)|-|\)\)|\]|\}|\}\}|\]|\]\/)/g;
  
  let match;
  while ((match = regex.exec(cleanCode)) !== null) {
    const id = match[1];
    const label = match[3];
    
    // Filter out reserved keywords or style definitions if they match accidentally
    if (['graph', 'flowchart', 'subgraph', 'style', 'classDef', 'click', 'linkStyle'].includes(id)) continue;

    if (!nodes.has(id)) {
      nodes.set(id, { id, label: label ? label.trim() : id });
    }
  }

  return Array.from(nodes.values());
}