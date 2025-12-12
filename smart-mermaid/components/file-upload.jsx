"use client";

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import { Upload, FileText, Loader2, CheckCircle2, XCircle, Trash2, Image as ImageIcon, Plus } from "lucide-react";

export function FileUpload() {
  // 文件项结构: { id, file, status: 'pending'|'uploading'|'processing'|'success'|'error', message, taskId }
  const [fileList, setFileList] = useState([]);

  // 更新单个文件的状态辅助函数
  const updateFileStatus = (id, newStatus, newMessage, taskId = null) => {
    setFileList(prev => prev.map(item => {
      if (item.id === id) {
        return {
          ...item,
          status: newStatus !== undefined ? newStatus : item.status,
          message: newMessage !== undefined ? newMessage : item.message,
          taskId: taskId || item.taskId
        };
      }
      return item;
    }));
  };

  // 轮询 Effect：每 2 秒检查一次所有处于 "processing" 状态的文件
  useEffect(() => {
    const timer = setInterval(() => {
      setFileList(currentList => {
        // 筛选出需要轮询的任务
        const processingItems = currentList.filter(item => item.status === 'processing' && item.taskId);
        
        if (processingItems.length === 0) return currentList;

        processingItems.forEach(item => {
          fetch(`/api/tasks/${item.taskId}`)
            .then(res => res.json())
            .then(data => {
              if (data.status && data.status !== 'processing') {
                if (data.status === 'success') {
                  toast.success(`文档 "${item.file.name}" 分析完成`);
                } else if (data.status === 'error') {
                  toast.error(`文档 "${item.file.name}" 分析失败`);
                }
                
                setFileList(prev => prev.map(curr => {
                    if (curr.id === item.id) {
                        return { ...curr, status: data.status, message: data.message };
                    }
                    return curr;
                }));
              }
            })
            .catch(e => console.error("Poll error:", e));
        });
        
        return currentList; 
      });
    }, 2000);

    return () => clearInterval(timer);
  }, []);

  const onDrop = useCallback(async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return;

    // 1. 初始化文件列表项
    const newFiles = acceptedFiles.map(file => ({
      id: Math.random().toString(36).substring(7),
      file,
      status: 'pending',
      message: '等待上传...'
    }));

    setFileList(prev => [...newFiles, ...prev]); 

    // 2. 逐个触发上传
    newFiles.forEach(async (fileItem) => {
      updateFileStatus(fileItem.id, 'uploading', '正在上传...');

      const formData = new FormData();
      formData.append("file", fileItem.file);

      try {
        const response = await fetch("/api/upload", {
          method: "POST",
          body: formData,
        });

        // 处理可能的非 JSON 响应（如服务器错误）
        if (!response.ok) {
           throw new Error(`HTTP Error: ${response.status}`);
        }

        const result = await response.json();

        if (result.status === "success") {
          updateFileStatus(fileItem.id, 'processing', '正在云端深度分析...', result.taskId);
        } else {
          updateFileStatus(fileItem.id, 'error', result.message || "上传失败");
          toast.error(`❌ 上传失败: ${fileItem.file.name}`);
        }

      } catch (error) {
        console.error("Upload error:", error);
        updateFileStatus(fileItem.id, 'error', "上传中断");
        toast.error(`❌ 上传中断: ${fileItem.file.name}`);
      }
    });
  }, []);

  const removeFile = (e, id) => {
    e.stopPropagation(); 
    setFileList(prev => prev.filter(item => item.id !== id));
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg']
    },
    disabled: false 
  });

  const hasFiles = fileList.length > 0;

  return (
    <div className="flex flex-col h-full gap-2">
      {/* 拖拽上传区域 - 动态高度 */}
      <div
        {...getRootProps()}
        className={`flex-shrink-0 border-2 border-dashed rounded-lg transition-all cursor-pointer flex items-center justify-center gap-2
          ${isDragActive ? "border-primary bg-primary/5 scale-[0.99]" : "border-border hover:border-primary/50 hover:bg-muted/50"}
          ${hasFiles ? "h-14 flex-row px-4" : "h-full flex-col p-6"}
        `}
      >
        <input {...getInputProps()} />
        
        {/* 两种模式的显示内容 */}
        {hasFiles ? (
            // 1. 紧凑模式 (有文件时)
             <>
                <div className="p-1.5 bg-primary/10 rounded-full flex-shrink-0">
                    <Plus className="h-4 w-4 text-primary" />
                </div>
                <p className="text-xs text-muted-foreground truncate">
                    {isDragActive ? "放手添加文件" : "点击或拖拽添加更多"}
                </p>
             </>
        ) : (
             // 2. 完整模式 (初始状态)
             <>
                <div className="p-3 bg-primary/10 rounded-full">
                  {isDragActive ? (
                    <FileText className="h-6 w-6 text-primary animate-bounce" />
                  ) : (
                    <Upload className="h-6 w-6 text-primary" />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">
                    {isDragActive ? "放手即可上传" : "点击或拖放文件到此处"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    支持 .md, .txt, .pdf, .docx, .png, .jpg
                  </p>
                </div>
             </>
        )}
      </div>

      {/* 文件列表区域 - 仅在有文件时显示并占据剩余空间 */}
      {hasFiles && (
        <div className="flex-1 overflow-y-auto min-h-0 border rounded-md bg-muted/20">
          <div className="divide-y">
            {fileList.map((item) => (
              <div key={item.id} className="p-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors group">
                {/* 图标 */}
                <div className="flex-shrink-0">
                  {item.file.type.startsWith('image/') ? (
                    <ImageIcon className="h-6 w-6 text-blue-500" />
                  ) : (
                    <FileText className="h-6 w-6 text-orange-500" />
                  )}
                </div>

                {/* 内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium truncate max-w-[150px]" title={item.file.name}>
                      {item.file.name}
                    </p>
                  </div>
                  
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {item.status === 'pending' && <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />}
                    {item.status === 'uploading' && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
                    {item.status === 'processing' && <Loader2 className="h-3 w-3 animate-spin text-purple-500" />}
                    {item.status === 'success' && <CheckCircle2 className="h-3 w-3 text-green-500" />}
                    {item.status === 'error' && <XCircle className="h-3 w-3 text-red-500" />}
                    
                    <p className={`text-[10px] truncate ${
                      item.status === 'error' ? 'text-red-500' : 
                      item.status === 'success' ? 'text-green-600' : 
                      'text-muted-foreground'
                    }`}>
                      {item.message}
                    </p>
                  </div>
                </div>

                {/* 操作 */}
                <button
                  onClick={(e) => removeFile(e, item.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 hover:bg-destructive/10 hover:text-destructive rounded"
                  title="移除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}