"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import { Upload, FileText } from "lucide-react"; // 移除了 File 引用，因为它没被用到且可能导致报错
import { extractTextFromFile } from "@/lib/file-service";
// 移除了 formatFileSize 和 Button，因为下面代码暂时没用到，保持简洁

export function FileUpload({ onTextExtracted }) {
  const [isProcessing, setIsProcessing] = useState(false);

  const onDrop = useCallback(
    async (acceptedFiles) => {
      if (acceptedFiles.length === 0) return;

      const file = acceptedFiles[0]; // 只处理第一个文件
      
      // 检查文件类型
      const fileExt = file.name.split('.').pop().toLowerCase();
      if (!['txt', 'md', 'docx', 'pdf'].includes(fileExt)) {
        toast.error("不支持的文件类型。请上传 .txt, .md, .pdf 或 .docx 文件。");
        return;
      }

      setIsProcessing(true);
      
      try {
        // --- 动作 1: 前端提取文本 (为了在输入框显示) ---
        // 这一步保留，这样用户能看到上传了什么内容，也可以手动修改作为 Prompt
        const { text, error } = await extractTextFromFile(file);
        
        if (error) {
          console.warn("前端提取文本失败，尝试继续上传后端...", error);
        } else if (text) {
          onTextExtracted(text);
        }

        // --- 动作 2: (新增) 上传到 Python 后端构建图谱 ---
        toast.info("正在上传并构建知识图谱...");
        
        const formData = new FormData();
        formData.append("file", file);

        // 发送给我们的 Python 后端接口
        const response = await fetch("/api/upload", {
          method: "POST",
          body: formData,
        });

        const result = await response.json();

        if (response.ok && result.status === "success") {
          toast.success("✅ 后端图谱构建完成！");
        } else {
          toast.error(`❌ 构建失败: ${result.message || "未知错误"}`);
        }

      } catch (error) {
        console.error("File processing error:", error);
        toast.error("处理文件时出错：" + error.message);
      } finally {
        setIsProcessing(false);
      }
    },
    [onTextExtracted]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf']
    },
    maxFiles: 1,
    disabled: isProcessing
  });

  return (
    <div
      {...getRootProps()}
      className={`h-full overflow-auto border-2 border-dashed rounded-lg p-6 transition-colors cursor-pointer flex flex-col items-center justify-center gap-4
        ${isDragActive ? "border-primary bg-primary/5" : "border-border"}
        ${isProcessing ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center justify-center gap-2 text-center">
        {isProcessing ? (
          <>
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            <p className="text-sm text-muted-foreground mt-2">正在分析并构建图谱...</p>
          </>
        ) : (
          <>
            <div className="p-3 bg-primary/10 rounded-full">
              {isDragActive ? (
                <FileText className="h-8 w-8 text-primary" />
              ) : (
                <Upload className="h-8 w-8 text-primary" />
              )}
            </div>
            <div>
              {isDragActive ? (
                <p className="font-medium text-primary">快放手，让我来处理！</p>
              ) : (
                <>
                  <p className="font-medium">点击或拖放文件到此处</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    会自动触发后端 RAG 建图逻辑<br/>支持 .txt, .md, .docx, .pdf
                  </p>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}