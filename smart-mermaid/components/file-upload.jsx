"use client";

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import { Upload, FileText, Loader2, CheckCircle2, XCircle, Trash2, Image as ImageIcon, Plus } from "lucide-react";

export function FileUpload() {
  // 文件项结构: { id, filename, status, message, file?: File }
  // 注意：本地刚上传的有 file 对象，从后端加载的只有 filename
  const [fileList, setFileList] = useState([]);

  // 1. 初始化加载：获取后端保存的文件列表
  useEffect(() => {
    fetchFiles();
  }, []); // 空依赖，仅挂载时执行一次（如果需要随项目切换更新，父组件需要控制 key 刷新此组件）

  const fetchFiles = async () => {
    try {
      const res = await fetch("/api/files");
      const data = await res.json();
      if (Array.isArray(data)) {
        setFileList(data);
      }
    } catch (e) {
      console.error("Failed to load files:", e);
    }
  };

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

  // 轮询 Effect：检查处理中的任务
  useEffect(() => {
    const timer = setInterval(() => {
      setFileList(currentList => {
        // 筛选出 "processing" 或 "pending" 且有 ID 的任务进行轮询
        const processingItems = currentList.filter(item => 
          (item.status === 'processing' || item.status === 'pending') && item.id
        );
        
        if (processingItems.length === 0) return currentList;

        processingItems.forEach(item => {
          // 这里可以使用 tasks 接口查状态，也可以重新拉取 file list
          // 为了准确性，我们查 tasks 接口，它反映实时进度
          fetch(`/api/tasks/${item.id}`)
            .then(res => res.json())
            .then(data => {
              if (data.status && data.status !== item.status) {
                if (data.status === 'success') {
                  toast.success(`文档 "${item.filename || item.file?.name}" 分析完成`);
                } else if (data.status === 'error') {
                  toast.error(`文档 "${item.filename || item.file?.name}" 分析失败`);
                }
                
                // 更新状态
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

    // 初始化新的文件项
    const newFiles = acceptedFiles.map(file => ({
      id: Math.random().toString(36).substring(7), // 临时ID，稍后会被后端ID替换
      file, // 保留原始 File 对象用于上传
      filename: file.name,
      status: 'pending',
      message: '等待上传...'
    }));

    setFileList(prev => [...newFiles, ...prev]); 

    // 逐个触发上传
    newFiles.forEach(async (fileItem) => {
      updateFileStatus(fileItem.id, 'uploading', '正在上传...');

      const formData = new FormData();
      formData.append("file", fileItem.file);

      try {
        const response = await fetch("/api/upload", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);

        const result = await response.json();

        if (result.status === "success") {
          // 关键：上传成功后，更新ID为后端生成的 taskId，确保轮询和持久化一致
          setFileList(prev => prev.map(item => {
              if (item.id === fileItem.id) {
                  return {
                      ...item,
                      id: result.taskId, // 替换为真实 ID
                      status: 'processing',
                      message: '正在云端深度分析...'
                  };
              }
              return item;
          }));
        } else {
          updateFileStatus(fileItem.id, 'error', result.message || "上传失败");
          toast.error(`❌ 上传失败: ${fileItem.filename}`);
        }

      } catch (error) {
        console.error("Upload error:", error);
        updateFileStatus(fileItem.id, 'error', "上传中断");
        toast.error(`❌ 上传中断: ${fileItem.filename}`);
      }
    });
  }, []);

  const removeFile = async (e, id) => {
    e.stopPropagation(); 
    
    // 乐观 UI 更新：先移除前端
    setFileList(prev => prev.filter(item => item.id !== id));
    
    // 调用后端删除
    try {
        await fetch(`/api/files/${id}`, { method: 'DELETE' });
    } catch(e) {
        console.error("Delete error:", e);
    }
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
      {/* 拖拽上传区域 */}
      <div
        {...getRootProps()}
        className={`flex-shrink-0 border-2 border-dashed rounded-lg transition-all cursor-pointer flex items-center justify-center gap-2
          ${isDragActive ? "border-primary bg-primary/5 scale-[0.99]" : "border-border hover:border-primary/50 hover:bg-muted/50"}
          ${hasFiles ? "h-14 flex-row px-4" : "h-full flex-col p-6"}
        `}
      >
        <input {...getInputProps()} />
        
        {hasFiles ? (
             <>
                <div className="p-1.5 bg-primary/10 rounded-full flex-shrink-0">
                    <Plus className="h-4 w-4 text-primary" />
                </div>
                <p className="text-xs text-muted-foreground truncate">
                    {isDragActive ? "放手添加文件" : "点击或拖拽添加更多"}
                </p>
             </>
        ) : (
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

      {/* 文件列表区域 */}
      {hasFiles && (
        <div className="flex-1 overflow-y-auto min-h-0 border rounded-md bg-muted/20">
          <div className="divide-y">
            {fileList.map((item) => {
              // 兼容逻辑：刚上传的有 file 对象，后端加载的只有 filename 字符串
              const name = item.filename || item.file?.name || "Unknown File";
              const isImage = name.match(/\.(jpg|jpeg|png|gif)$/i);

              return (
                <div key={item.id} className="p-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors group">
                  <div className="flex-shrink-0">
                    {isImage ? (
                      <ImageIcon className="h-6 w-6 text-blue-500" />
                    ) : (
                      <FileText className="h-6 w-6 text-orange-500" />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium truncate max-w-[150px]" title={name}>
                        {name}
                      </p>
                    </div>
                    
                    <div className="flex items-center gap-1.5 mt-0.5">
                      {(item.status === 'pending' || !item.status) && <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />}
                      {item.status === 'uploading' && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
                      {item.status === 'processing' && <Loader2 className="h-3 w-3 animate-spin text-purple-500" />}
                      {item.status === 'success' && <CheckCircle2 className="h-3 w-3 text-green-500" />}
                      {item.status === 'error' && <XCircle className="h-3 w-3 text-red-500" />}
                      
                      <p className={`text-[10px] truncate ${
                        item.status === 'error' ? 'text-red-500' : 
                        item.status === 'success' ? 'text-green-600' : 
                        'text-muted-foreground'
                      }`}>
                        {item.message || (item.status === 'success' ? '已完成' : '处理中...')}
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={(e) => removeFile(e, item.id)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 hover:bg-destructive/10 hover:text-destructive rounded"
                    title="移除"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}