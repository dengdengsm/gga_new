"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import { parseMermaidToExcalidraw } from "@excalidraw/mermaid-to-excalidraw";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { 
  Download, 
  Minimize,
  Maximize,
  Move
} from "lucide-react";
import "@excalidraw/excalidraw/index.css";
import { convertToExcalidrawElements, exportToBlob } from "@excalidraw/excalidraw";

// Dynamically import Excalidraw to avoid SSR issues
const Excalidraw = dynamic(
  async () => (await import("@excalidraw/excalidraw")).Excalidraw,
  {
    ssr: false,
  }
);

function ExcalidrawRenderer({ mermaidCode, onErrorChange }) {
  // 基础 Mermaid 转换数据（作为兜底初始值）
  const [excalidrawElements, setExcalidrawElements] = useState([]);
  const [excalidrawFiles, setExcalidrawFiles] = useState({});
  
  const [excalidrawAPI, setExcalidrawAPI] = useState(null);
  const [isRendering, setIsRendering] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  
  // 场景控制 Key
  const [sceneKey, setSceneKey] = useState(0);     // 代码变化时更新
  const [remountKey, setRemountKey] = useState(0); // 模式切换时更新
  
  // 数据持久化引用（解决切换模式数据丢失问题）
  const latestSceneElementsRef = useRef(null);
  const latestAppStateRef = useRef(null);
  const latestFilesRef = useRef(null);
  
  // 记录上一次处理的代码，防止切换全屏时重复解析覆盖用户数据
  const prevMermaidCodeRef = useRef(null);
  const pendingFitSceneKeyRef = useRef(null);

  // 切换全屏并强制重载
  const toggleFullscreenMode = (targetStatus) => {
    setIsFullscreen(targetStatus);
    setRemountKey(prev => prev + 1);
  };

  // 监听全局事件
  useEffect(() => {
    const handleResetView = () => {
      if (excalidrawAPI) {
        excalidrawAPI.resetScene();
        // 仅当确实需要重置回初始代码状态时才调用
        if (mermaidCode && mermaidCode.trim()) {
           // 清空用户更改记录，强制回退到代码生成状态
           latestSceneElementsRef.current = null;
           // 强制重新解析
           prevMermaidCodeRef.current = null; 
           renderMermaidContent();
        }
      }
    };

    const handleToggleFullscreen = () => {
      setIsFullscreen(prev => {
        const nextStatus = !prev;
        setRemountKey(k => k + 1);
        return nextStatus;
      });
    };

    window.addEventListener('resetView', handleResetView);
    window.addEventListener('toggleFullscreen', handleToggleFullscreen);

    return () => {
      window.removeEventListener('resetView', handleResetView);
      window.removeEventListener('toggleFullscreen', handleToggleFullscreen);
    };
  }, [excalidrawAPI, mermaidCode]);

  const renderMermaidContent = useCallback(async () => {
    if (!mermaidCode || mermaidCode.trim() === "") {
      setExcalidrawElements([]);
      setExcalidrawFiles({});
      setRenderError(null);
      setExcalidrawAPI(null);
      latestSceneElementsRef.current = null; // 清空缓存
      setSceneKey(k => k + 1);
      return;
    }

    // 如果代码没有变化（例如只是切换全屏触发了 Effect），则跳过解析
    // 这样可以保留用户的绘图数据
    if (prevMermaidCodeRef.current === mermaidCode) {
      return;
    }

    setIsRendering(true);
    setRenderError(null);

    try {
      const preprocessedCode = mermaidCode.replace(/<br\s*\/?>/gi, '');
      const { elements, files } = await parseMermaidToExcalidraw(preprocessedCode);
      const convertedElements = convertToExcalidrawElements(elements);
      
      setExcalidrawElements(convertedElements);
      setExcalidrawFiles(files);
      setExcalidrawAPI(null);
      
      // 代码变了，这是全新的图，清空用户的旧笔迹缓存
      latestSceneElementsRef.current = null;
      latestAppStateRef.current = null;
      latestFilesRef.current = null;

      // 更新代码记录
      prevMermaidCodeRef.current = mermaidCode;

      setSceneKey((k) => {
        const next = k + 1;
        pendingFitSceneKeyRef.current = next;
        return next;
      });

      if (onErrorChange) {
        onErrorChange(null, false);
      }
    } catch (error) {
      console.error("Mermaid rendering error:", error);
      const errorMsg = `${error.message}`;
      setRenderError(errorMsg);
      toast.error("图表渲染失败，请检查 Mermaid 代码语法");

      if (onErrorChange) {
        onErrorChange(errorMsg, true);
      }
    } finally {
      setIsRendering(false);
    }
  }, [mermaidCode, onErrorChange]);

  useEffect(() => {
    renderMermaidContent();
  }, [renderMermaidContent]);

  // 自动适配视图逻辑
  useEffect(() => {
    if (!excalidrawAPI) return;
    if (renderError) return;
    
    // 如果是代码变化引起的新场景，或者是全屏切换
    if (pendingFitSceneKeyRef.current === sceneKey || remountKey > 0) {
      const raf = requestAnimationFrame(() => {
        try {
          excalidrawAPI.scrollToContent(undefined, { fitToContent: true });
        } catch (e) {
          console.error('Auto fit in effect failed:', e);
        }
        if (pendingFitSceneKeyRef.current === sceneKey) {
            pendingFitSceneKeyRef.current = null;
        }
      });
      return () => cancelAnimationFrame(raf);
    }
  }, [excalidrawAPI, sceneKey, renderError, remountKey]);

  // 适应窗口
  const handleFitToScreen = () => {
    if (excalidrawAPI) {
      // 优先使用当前 API 获取的元素，确保包含用户新增的内容
      const elements = excalidrawAPI.getSceneElements();
      if (elements && elements.length > 0) {
        excalidrawAPI.scrollToContent(elements, { fitToContent: true });
      }
    }
  };

  // 下载功能修复：使用当前真实场景数据
  const handleDownload = async () => {
    if (!excalidrawAPI) {
      toast.error("组件未就绪");
      return;
    }

    // 获取当前场景中的所有元素（包含用户修改）
    const currentElements = excalidrawAPI.getSceneElements();
    
    if (!currentElements || currentElements.length === 0) {
      toast.error("没有可下载的内容");
      return;
    }

    try {
      const appState = excalidrawAPI.getAppState();
      // 获取当前文件列表，优先使用Ref中的（可能有用户上传的图），没有则用初始的
      const currentFiles = latestFilesRef.current || excalidrawFiles;

      const blob = await exportToBlob({
        elements: currentElements,
        appState: appState,
        files: currentFiles,
        mimeType: "image/png",
        quality: 0.8,
      });

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'excalidraw-diagram.png';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("图表已下载");
    } catch (error) {
      console.error('Download error:', error);
      toast.error("下载失败");
    }
  };

  // 数据变更监听：实时保存用户的笔迹
  const handleExcalidrawChange = (elements, appState, files) => {
    latestSceneElementsRef.current = elements;
    latestAppStateRef.current = appState;
    latestFilesRef.current = files;
  };

  return (
    <div className={`${isFullscreen ? 'fixed inset-0 z-50 bg-background' : 'h-full'} flex flex-col`}>
      {/* Header */}
      <div className="h-12 flex justify-between items-center px-2 flex-shrink-0 border-b bg-background">
        <h3 className="text-sm font-medium flex items-center gap-2">
          Excalidraw 图表
          {!isFullscreen && (
            <span className="text-[10px] text-muted-foreground font-normal bg-muted px-1.5 py-0.5 rounded border">
              预览模式
            </span>
          )}
        </h3>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleFitToScreen}
            className="h-7 gap-1 text-xs px-2"
            title="适应窗口"
            disabled={!excalidrawAPI}
          >
            <Move className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">适应</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            disabled={!excalidrawAPI}
            className="h-7 gap-1 text-xs px-2"
          >
            <Download className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">下载</span>
          </Button>

          {isFullscreen ? (
            <Button
              variant="default"
              size="sm"
              onClick={() => toggleFullscreenMode(false)}
              className="h-7 gap-1 text-xs px-2"
              title="完成编辑"
            >
              <Minimize className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">完成</span>
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => toggleFullscreenMode(true)}
              className="h-7 gap-1 text-xs px-2"
              title="全屏编辑"
            >
              <Maximize className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">全屏编辑</span>
            </Button>
          )}
        </div>
      </div>

      {/* Excalidraw Container */}
      <div className="flex-1 bg-gray-50 dark:bg-gray-900 relative min-h-0 overflow-hidden group">
        
        {/* Loading / Error States */}
        {isRendering && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
            <div className="flex items-center space-x-2">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              <span className="text-muted-foreground">渲染中...</span>
            </div>
          </div>
        )}
        
        {renderError && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
            <div className="text-center p-4">
              <p className="text-destructive mb-2">渲染失败</p>
              <p className="text-sm text-muted-foreground">{renderError}</p>
            </div>
          </div>
        )}
        
        {!isRendering && !renderError && !mermaidCode && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-muted-foreground">请生成Mermaid代码以查看图表</p>
          </div>
        )}
        
        {/* 核心修复：预览模式遮罩层
            1. z-index 高于 Excalidraw，拦截所有鼠标事件，防止双击穿透导致组件上浮。
            2. 提供点击入口，用户体验更直观。
        */}
        {!isFullscreen && !isRendering && !renderError && mermaidCode && (
          <div 
            className="absolute inset-0 z-10 cursor-pointer flex items-center justify-center bg-transparent transition-colors hover:bg-black/5"
            onClick={() => toggleFullscreenMode(true)}
            title="点击进入全屏编辑模式"
          >
            <div className="opacity-0 group-hover:opacity-100 transition-opacity bg-background/90 px-3 py-1.5 rounded-full shadow-sm border text-xs font-medium flex items-center gap-1.5 pointer-events-none">
              <Maximize className="h-3 w-3" />
              点击编辑
            </div>
          </div>
        )}

        {/* 画布区域 */}
        <div className="w-full h-full relative">
          <Excalidraw
            // 组合 Key：确保场景变了或者模式变了都会重载
            key={`${sceneKey}-${remountKey}`}
            viewModeEnabled={!isFullscreen} 
            zenModeEnabled={!isFullscreen}
            gridModeEnabled={false}
            initialData={{
              // 关键逻辑：如果 Ref 中有用户的数据，优先使用用户的；否则使用 Mermaid 生成的
              elements: latestSceneElementsRef.current || excalidrawElements,
              appState: {
                viewBackgroundColor: "#fafafa",
                currentItemFontFamily: 1,
                viewModeEnabled: !isFullscreen,
                // 如果有保存的状态（比如滚动位置），也可以在这里恢复
                ...(latestAppStateRef.current || {})
              },
              files: latestFilesRef.current || excalidrawFiles,
              scrollToContent: true,
            }}
            excalidrawAPI={(api) => setExcalidrawAPI(api)}
            // 实时监听变更
            onChange={handleExcalidrawChange}
          />
        </div>
      </div>
    </div>
  );
}

export default ExcalidrawRenderer;