"use client";

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import { Upload, FileText, Loader2, CheckCircle2, XCircle, Trash2, Image as ImageIcon, Plus, FileClock, Github } from "lucide-react";

// 引入 UI 组件
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";

export function FileUpload({ autoBuild = true, onCodeGenerated }) {
  // 文件项结构: { id, filename, status, message, file?: File, isGithub?: boolean }
  const [fileList, setFileList] = useState([]);
  
  // GitHub 相关状态
  const [isGithubOpen, setIsGithubOpen] = useState(false);
  const [githubUrl, setGithubUrl] = useState("");
  const [isAnalyzingGithub, setIsAnalyzingGithub] = useState(false);

  // 1. 初始化加载
  useEffect(() => {
    fetchFiles();
  }, []);

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

  // 2. 核心轮询逻辑 (处理异步任务状态)
  useEffect(() => {
    const timer = setInterval(() => {
      setFileList(currentList => {
        // 筛选出 "processing" 或 "pending" 的任务进行轮询
        const processingItems = currentList.filter(item => 
          (item.status === 'processing' || item.status === 'pending') && item.id
        );
        
        if (processingItems.length === 0) return currentList;

        processingItems.forEach(item => {
          // 如果是临时ID (temp-开头)，跳过轮询，等待 handleGithubAnalysis 替换为真实 ID
          if (typeof item.id === 'string' && item.id.startsWith('temp-')) return;

          fetch(`/api/tasks/${item.id}`)
            .then(res => res.json())
            .then(data => {
              // 检查任务状态是否有变化
              if (data.status) {
                const isStatusChanged = data.status !== item.status;
                const isMessageChanged = data.message !== item.message;

                if (isStatusChanged || isMessageChanged) {
                  // 更新列表状态
                  setFileList(prev => prev.map(curr => {
                      if (curr.id === item.id) {
                          return { ...curr, status: data.status, message: data.message };
                      }
                      return curr;
                  }));

                  // 处理完成状态
                  if (data.status === 'success' && isStatusChanged) {
                    toast.success(`任务 "${item.filename}" 完成`);
                    
                    // 如果是 GitHub 分析任务且有结果，触发回调将代码传给父组件
                    if (data.result && data.result.mermaidCode && onCodeGenerated) {
                        onCodeGenerated(data.result.mermaidCode);
                    }
                  } else if (data.status === 'error' && isStatusChanged) {
                    toast.error(`任务失败: ${data.message}`);
                  }
                }
              }
            })
            .catch(e => console.error("Poll error:", e));
        });
        
        return currentList; 
      });
    }, 2000); // 每2秒轮询一次

    return () => clearInterval(timer);
  }, [onCodeGenerated]);

  const onDrop = useCallback(async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return;

    const newFiles = acceptedFiles.map(file => ({
      id: Math.random().toString(36).substring(7),
      file,
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
      formData.append("autoBuild", autoBuild); 

      try {
        const response = await fetch("/api/upload", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);

        const result = await response.json();

        if (result.status === "success") {
          const nextStatus = autoBuild ? 'processing' : 'uploaded';
          const nextMsg = autoBuild ? '正在云端深度分析...' : '文件已保存 (待分析)';

          setFileList(prev => prev.map(item => {
              if (item.id === fileItem.id) {
                  return {
                      ...item,
                      id: result.taskId, 
                      status: nextStatus,
                      message: nextMsg
                  };
              }
              return item;
          }));
          
          if (!autoBuild) {
              toast.success(`文件 "${fileItem.filename}" 上传成功`);
          }

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
  }, [autoBuild]);

  // 3. 处理 GitHub 分析请求 (异步模式)
  const handleGithubAnalysis = async () => {
    if (!githubUrl) {
      toast.error("请输入有效的 GitHub 仓库地址");
      return;
    }

    setIsAnalyzingGithub(true);
    
    // 生成临时 ID 占位
    const tempId = "temp-" + Math.random().toString(36).substring(7);
    const repoName = githubUrl.split('/').pop() || "GitHub Repo";
    
    // 立即在 UI 显示条目
    const mockFile = {
        id: tempId,
        filename: `GitHub: ${repoName}`,
        status: 'pending',
        message: '正在提交请求...',
        isGithub: true
    };
    setFileList(prev => [mockFile, ...prev]);
    setIsGithubOpen(false); // 关闭弹窗

    try {
        const response = await fetch("/api/upload-github", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                repoUrl: githubUrl,
                diagramType: "auto"
            })
        });

        const data = await response.json();

        if (data.status === "success" && data.taskId) {
            // 请求成功，将临时 ID 替换为后端返回的真实 Task ID
            // 状态改为 processing，这样 useEffect 里的轮询逻辑就会接管它
            setFileList(prev => prev.map(item => {
                if (item.id === tempId) {
                    return {
                        ...item,
                        id: data.taskId, // 关键：替换 ID
                        status: 'processing',
                        message: '任务已启动，正在排队...'
                    };
                }
                return item;
            }));
            
            toast.info("分析任务已在后台启动");
        } else {
            throw new Error(data.message || "启动失败");
        }

    } catch (e) {
        console.error("GitHub Request Error:", e);
        toast.error(`请求失败: ${e.message}`);
        // 失败则移除临时条目
        setFileList(prev => prev.filter(item => item.id !== tempId));
    } finally {
        setIsAnalyzingGithub(false);
        setGithubUrl("");
    }
  };

  const removeFile = async (e, id) => {
    e.stopPropagation(); 
    setFileList(prev => prev.filter(item => item.id !== id));
    // 只有真实文件才调用后端删除，GitHub 条目（如果没有对应文件记录）仅前端移除
    if (!id.startsWith("temp-")) {
        try {
            await fetch(`/api/files/${id}`, { method: 'DELETE' });
        } catch(e) {
            // 忽略 404 等错误
        }
    }
  };

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    noClick: true, // 禁用默认点击，以便我们自定义按钮
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
      {/* 上传/操作区域 */}
      <div
        {...getRootProps()}
        className={`flex-shrink-0 border-2 border-dashed rounded-lg transition-all flex items-center justify-center gap-2 relative
          ${isDragActive ? "border-primary bg-primary/5 scale-[0.99]" : "border-border hover:border-primary/50 hover:bg-muted/50"}
          ${hasFiles ? "h-14 flex-row px-4" : "h-full flex-col p-6"}
        `}
      >
        <input {...getInputProps()} />
        
        {hasFiles ? (
             // --- 紧凑模式 (已有文件) ---
             <>
                <div className="flex items-center gap-2 flex-1">
                    <Button 
                        variant="ghost" 
                        size="icon" 
                        onClick={(e) => { e.stopPropagation(); open(); }}
                        className="h-8 w-8 rounded-full bg-primary/10 hover:bg-primary/20"
                        title="上传本地文件"
                    >
                        <Plus className="h-4 w-4 text-primary" />
                    </Button>
                    
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e) => { e.stopPropagation(); setIsGithubOpen(true); }}
                        className="h-8 w-8 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
                        title="从 GitHub 导入"
                    >
                        <Github className="h-4 w-4" />
                    </Button>

                    <p className="text-xs text-muted-foreground ml-2">
                        {isDragActive ? "放手添加文件" : "添加更多..."}
                    </p>
                </div>
             </>
        ) : (
             // --- 完整模式 (空状态) ---
             <>
                <div className="p-3 bg-primary/10 rounded-full mb-2">
                  {isDragActive ? (
                    <FileText className="h-6 w-6 text-primary animate-bounce" />
                  ) : (
                    <Upload className="h-6 w-6 text-primary" />
                  )}
                </div>
                
                <div className="text-center space-y-4">
                  <div>
                    <p className="text-sm font-medium">
                        {isDragActive ? "放手即可上传" : "拖拽文件到此处，或选择操作"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                        支持 .md, .txt, .pdf, .docx, .png, .jpg
                    </p>
                  </div>

                  {/* 两个并排按钮 */}
                  <div className="flex items-center justify-center gap-3">
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); open(); }}
                        className="gap-2"
                      >
                        <FileText className="h-4 w-4" />
                        选择文件
                      </Button>
                      
                      <span className="text-xs text-muted-foreground">- 或 -</span>
                      
                      <Button 
                        variant="default" 
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); setIsGithubOpen(true); }}
                        className="gap-2 bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-200"
                      >
                        <Github className="h-4 w-4" />
                        GitHub 仓库
                      </Button>
                  </div>
                </div>
             </>
        )}
      </div>

      {/* 文件列表区域 */}
      {hasFiles && (
        <div className="flex-1 overflow-y-auto min-h-0 border rounded-md bg-muted/20">
          <div className="divide-y">
            {fileList.map((item) => {
              const name = item.filename || item.file?.name || "Unknown File";
              const isImage = name.match(/\.(jpg|jpeg|png|gif)$/i);
              const isGithub = item.isGithub || name.startsWith("GitHub:");

              return (
                <div key={item.id} className="p-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors group">
                  <div className="flex-shrink-0">
                    {isGithub ? (
                        <Github className="h-6 w-6 text-black dark:text-white" />
                    ) : isImage ? (
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
                      {/* 状态图标 */}
                      {(item.status === 'pending' || !item.status) && <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />}
                      {item.status === 'uploaded' && <FileClock className="h-3 w-3 text-blue-400" />} 
                      {item.status === 'uploading' && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
                      {item.status === 'processing' && <Loader2 className="h-3 w-3 animate-spin text-purple-500" />}
                      {item.status === 'success' && <CheckCircle2 className="h-3 w-3 text-green-500" />}
                      {item.status === 'error' && <XCircle className="h-3 w-3 text-red-500" />}
                      
                      <p className={`text-[10px] truncate ${
                        item.status === 'error' ? 'text-red-500' : 
                        item.status === 'success' ? 'text-green-600' : 
                        item.status === 'uploaded' ? 'text-blue-500' :
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

      {/* GitHub 输入弹窗 */}
      <Dialog open={isGithubOpen} onOpenChange={setIsGithubOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>从 GitHub 导入</DialogTitle>
            <DialogDescription>
              输入公开仓库的 URL，我们将自动分析其代码结构并生成图表。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="github-url">仓库地址 (URL)</Label>
              <Input
                id="github-url"
                placeholder="https://github.com/username/repo"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                disabled={isAnalyzingGithub}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsGithubOpen(false)} disabled={isAnalyzingGithub}>
                取消
            </Button>
            <Button onClick={handleGithubAnalysis} disabled={isAnalyzingGithub}>
              {isAnalyzingGithub ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    启动中...
                  </>
              ) : (
                  <>
                    <Github className="mr-2 h-4 w-4" />
                    开始分析
                  </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}