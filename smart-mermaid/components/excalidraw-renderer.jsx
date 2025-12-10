"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import { parseMermaidToExcalidraw } from "@excalidraw/mermaid-to-excalidraw";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { 
  Download, 
  ZoomIn, 
  ZoomOut, 
  Minimize,
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
  const [excalidrawElements, setExcalidrawElements] = useState([]);
  const [excalidrawFiles, setExcalidrawFiles] = useState({});
  const [excalidrawAPI, setExcalidrawAPI] = useState(null);
  const [isRendering, setIsRendering] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [sceneKey, setSceneKey] = useState(0);
  // 标记需要在新场景首次变更后执行一次自动适配
  const pendingFitSceneKeyRef = useRef(null);

  // 监听全局事件
  useEffect(() => {
    const handleResetView = () => {
      if (excalidrawAPI) {
        excalidrawAPI.resetScene();
        if (mermaidCode && mermaidCode.trim()) {
          // 重新渲染当前内容
          renderMermaidContent();
        }
      }
    };

    const handleToggleFullscreen = () => {
      setIsFullscreen(prev => !prev);
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
      // 清空旧的 API 引用，避免在重挂载过程中被误用
      setExcalidrawAPI(null);
      setSceneKey((k) => {
        const next = k + 1;
        // 空内容不需要适配
        pendingFitSceneKeyRef.current = null;
        return next;
      });
      return;
    }

    setIsRendering(true);
    setRenderError(null);

    try {
      // 预处理 mermaidCode: 移除 <br> 标签
      const preprocessedCode = mermaidCode.replace(/<br\s*\/?>/gi, '');
      const { elements, files } = await parseMermaidToExcalidraw(preprocessedCode);
      const convertedElements = convertToExcalidrawElements(elements);
      
      setExcalidrawElements(convertedElements);
      setExcalidrawFiles(files);
      // 清空旧的 API 引用，避免在重挂载过程中被误用
      setExcalidrawAPI(null);
      setSceneKey((k) => {
        const next = k + 1;
        // 标记该场景需要在首次变更后自动适配
        pendingFitSceneKeyRef.current = next;
        return next;
      });

      // 通知父组件没有错误
      if (onErrorChange) {
        onErrorChange(null, false);
      }
    } catch (error) {
      console.error("Mermaid rendering error:", error);
      const errorMsg = `${error.message}`;
      setRenderError(errorMsg);
      toast.error("图表渲染失败，请检查 Mermaid 代码语法");

      // 通知父组件有错误，与 mermaid-renderer 保持一致
      if (onErrorChange) {
        onErrorChange(errorMsg, true);
      }
    } finally {
      setIsRendering(false);
    }
  }, [mermaidCode]);

  useEffect(() => {
    renderMermaidContent();
  }, [renderMermaidContent]);

  // 通过 onChange 的首次回调来保证 Excalidraw 完成挂载和布局后再适配
  // 以及在 sceneKey 或 API 就绪时也尝试进行一次自动适配（双保险）
  useEffect(() => {
    if (!excalidrawAPI) return;
    if (renderError) return;
    if (pendingFitSceneKeyRef.current !== sceneKey) return;
    // 等待一帧，确保容器尺寸稳定
    const raf = requestAnimationFrame(() => {
      try {
        excalidrawAPI.scrollToContent(undefined, { fitToContent: true });
      } catch (e) {
        console.error('Auto fit in effect failed:', e);
      }
      pendingFitSceneKeyRef.current = null;
    });
    return () => cancelAnimationFrame(raf);
  }, [excalidrawAPI, sceneKey, renderError]);

  // 缩放功能
  const handleZoomIn = () => {
    if (excalidrawAPI) {
      excalidrawAPI.zoomIn();
    }
  };

  const handleZoomOut = () => {
    if (excalidrawAPI) {
      excalidrawAPI.zoomOut();
    }
  };

  const handleZoomReset = () => {
    if (excalidrawAPI) {
      excalidrawAPI.resetZoom();
      if (excalidrawElements.length > 0) {
        excalidrawAPI.scrollToContent(excalidrawElements, {
          fitToContent: true,
        });
      }
    }
  };

  // 适应窗口大小
  const handleFitToScreen = () => {
    if (excalidrawAPI && excalidrawElements.length > 0) {
      excalidrawAPI.scrollToContent(excalidrawElements, {
        fitToContent: true,
      });
    }
  };

  const handleDownload = async () => {
    if (!excalidrawAPI || excalidrawElements.length === 0) {
      toast.error("没有可下载的内容");
      return;
    }

    try {
      // 获取当前应用状态
      const appState = excalidrawAPI.getAppState();
      
      // 使用正确的exportToBlob API
      const blob = await exportToBlob({
        elements: excalidrawElements,
        appState: appState,
        files: excalidrawFiles,
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

  return (
    <div className={`${isFullscreen ? 'fixed inset-0 z-50 bg-background' : 'h-full'} flex flex-col`}>
      {/* 控制栏 - 固定高度 */}
      <div className="h-12 flex justify-between items-center px-2 flex-shrink-0">
        <h3 className="text-sm font-medium">Excalidraw 图表</h3>
        <div className="flex gap-2">
          {/* 适应窗口 */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleFitToScreen}
            className="h-7 gap-1 text-xs px-2"
            title="适应窗口"
            disabled={!excalidrawAPI || excalidrawElements.length === 0}
          >
            <Move className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">适应</span>
          </Button>

          {/* 下载按钮 */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            disabled={!excalidrawAPI || excalidrawElements.length === 0}
            className="h-7 gap-1 text-xs px-2"
          >
            <Download className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">下载</span>
          </Button>

          {/* 全屏模式下的退出按钮 */}
          {isFullscreen && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsFullscreen(false)}
              className="h-7 gap-1 text-xs px-2"
              title="退出全屏"
            >
              <Minimize className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">退出</span>
            </Button>
          )}
        </div>
      </div>

      {/* 图表显示区域 - 占用剩余空间 */}
      <div className="flex-1 border rounded-lg bg-gray-50 dark:bg-gray-900 relative min-h-0 overflow-hidden">
        {isRendering && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
            <div className="flex items-center space-x-2">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              <span className="text-muted-foreground">渲染中...</span>
            </div>
          </div>
        )}
        
        {renderError && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
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
        
        <div className="w-full h-full">
          <Excalidraw
            key={sceneKey}
            initialData={{
              elements: excalidrawElements,
              appState: {
                viewBackgroundColor: "#fafafa",
                currentItemFontFamily: 1,
              },
              files: excalidrawFiles,
              scrollToContent: excalidrawElements.length > 0,
            }}
            excalidrawAPI={(api) => setExcalidrawAPI(api)}
            onChange={(elements) => {
              // 仅在新场景挂载后的首次变更时自动适配一次
              if (
                pendingFitSceneKeyRef.current === sceneKey &&
                excalidrawAPI &&
                elements &&
                elements.length > 0 &&
                !renderError
              ) {
                // 等待一帧，确保容器尺寸与布局稳定
                requestAnimationFrame(() => {
                  try {
                    excalidrawAPI.scrollToContent(undefined, { fitToContent: true });
                  } catch (e) {
                    console.error('Auto fit in onChange failed:', e);
                  }
                });
                pendingFitSceneKeyRef.current = null;
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default ExcalidrawRenderer; 
