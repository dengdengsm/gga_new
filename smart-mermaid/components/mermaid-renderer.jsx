"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  Download,
  ZoomIn,
  ZoomOut,
  Minimize,
  Maximize,
  Move
} from "lucide-react";
import { copyToClipboard } from "@/lib/utils";
import { toast } from "sonner";

export function MermaidRenderer({ mermaidCode, onChange, onErrorChange }) {
  const mermaidRef = useRef(null);
  const containerRef = useRef(null);

  // 性能优化：使用 Ref 存储变换状态，避免高频 Re-render
  const transformRef = useRef({ x: 0, y: 0, k: 1 });

  // 仅用于 UI 显示的 Zoom 数值，不需要高频更新
  const [displayZoom, setDisplayZoom] = useState(100);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // 拖拽状态
  const isDraggingRef = useRef(false);
  const startPosRef = useRef({ x: 0, y: 0 });

  // 辅助函数：应用变换到 DOM
  const updateTransform = () => {
    if (mermaidRef.current) {
      const { x, y, k } = transformRef.current;
      mermaidRef.current.style.transform = `scale(${k}) translate(${x / k}px, ${y / k}px)`;
      // 可以在这里做一个节流来更新 setDisplayZoom，或者只在交互结束时更新
    }
  };

  // 辅助函数：安全的设置缩放并更新 UI
  const setZoom = (newZoom) => {
    // 限制缩放范围
    const clampedZoom = Math.max(0.1, Math.min(5, newZoom));
    transformRef.current.k = clampedZoom;
    updateTransform();
    setDisplayZoom(Math.round(clampedZoom * 100));
  };

  // 清理函数：移除任何残留的mermaid元素
  const cleanupMermaidElements = useCallback(() => {
    const specificId = mermaidRef.current?.getAttribute('data-mermaid-id');
    if (specificId) {
      const existingElement = document.getElementById(specificId);
      if (existingElement && existingElement.parentNode && !mermaidRef.current?.contains(existingElement)) {
        existingElement.parentNode.removeChild(existingElement);
      }
    }

    const strayElements = document.querySelectorAll('[id^="dmermaid-"]');
    strayElements.forEach(element => {
      if (element.parentNode && !mermaidRef.current?.contains(element)) {
        element.parentNode.removeChild(element);
      }
    });
  }, []);

  useEffect(() => {
    let mounted = true;

    const renderMermaid = async () => {
      if (!mermaidCode || !mermaidRef.current) {
        setIsLoading(false);
        if (onErrorChange) onErrorChange(null, false);
        return;
      }

      try {
        setIsLoading(true);
        setError(null);

        const mermaid = (await import("mermaid")).default;

        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          // 1. 全局配置：尝试启用 elk (部分图表类型支持)
          flowchart: {
            useMaxWidth: true,
            htmlLabels: true,
            // 添加这就行，让流程图默认使用 elk 引擎
            defaultRenderer: 'elk'
          },
          // 2. ELK 的具体配置（可选）
          elk: {
            mergeEdges: true,
            nodePlacementStrategy: 'NETWORK_SIMPLEX', // 或 'LINEAR_SEGMENTS'
          },
          sequence: { useMaxWidth: true, wrap: true },
          gantt: { useMaxWidth: true },
          journey: { useMaxWidth: true },
          pie: { useMaxWidth: true }
        });
        try {
          await mermaid.parse(mermaidCode);
        } catch (parseError) {
          if (mounted) {
            const errorMsg = 'Mermaid语法错误: ' + parseError.message;
            setError(errorMsg);
            setIsLoading(false);
            if (onErrorChange) onErrorChange(errorMsg, true);
          }
          return;
        }

        cleanupMermaidElements();
        mermaidRef.current.innerHTML = '';

        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        mermaidRef.current.setAttribute('data-mermaid-id', id);

        const { svg } = await mermaid.render(id, mermaidCode);

        if (mounted) {
          mermaidRef.current.innerHTML = svg;
          setIsLoading(false);
          // 重置视图
          transformRef.current = { x: 0, y: 0, k: 1 };
          updateTransform();
          setDisplayZoom(100);

          if (onErrorChange) onErrorChange(null, false);
        }
      } catch (err) {
        console.error('Mermaid rendering error:', err);
        if (mounted) {
          const errorMsg = '渲染Mermaid图表时出错: ' + err.message;
          setError(errorMsg);
          setIsLoading(false);
          if (onErrorChange) onErrorChange(errorMsg, true);
        }
      }
    };

    renderMermaid();

    return () => {
      mounted = false;
      cleanupMermaidElements();
    };
  }, [mermaidCode, cleanupMermaidElements, onErrorChange]);

  // 缩放按钮处理
  const handleZoomIn = () => setZoom(transformRef.current.k * 1.2);
  const handleZoomOut = () => setZoom(transformRef.current.k / 1.2);
  const handleZoomReset = () => {
    transformRef.current = { x: 0, y: 0, k: 1 };
    updateTransform();
    setDisplayZoom(100);
  };

  // 鼠标滚轮缩放 (高频事件，直接操作)
  const handleWheel = useCallback((e) => {
    if (e.shiftKey && mermaidRef.current?.contains(e.target)) {
      e.preventDefault();
      e.stopPropagation();

      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const currentK = transformRef.current.k;
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      const newK = Math.max(0.1, Math.min(5, currentK * delta));

      // 以鼠标为中心缩放的位移计算
      // 公式：newX = mouseX - (mouseX - oldX) * (newK / oldK)
      const zoomRatio = newK / currentK;
      transformRef.current.x = mouseX - (mouseX - transformRef.current.x) * zoomRatio;
      transformRef.current.y = mouseY - (mouseY - transformRef.current.y) * zoomRatio;
      transformRef.current.k = newK;

      updateTransform();
      // 滚轮时，我们防抖更新 React 状态，或者为了性能干脆不实时更新 displayZoom
      // 这里选择不实时更新 displayZoom 以保证绝对流畅，
      // 或者可以使用 requestAnimationFrame 的防抖策略，这里简单处理：
      if (window.zoomTimeout) clearTimeout(window.zoomTimeout);
      window.zoomTimeout = setTimeout(() => {
        setDisplayZoom(Math.round(newK * 100));
      }, 100);
    }
  }, []);

  // 鼠标/触摸 交互逻辑
  const handleMouseDown = (e) => {
    // 允许在容器或内容上点击，忽略按钮等
    if (e.target.closest('button')) return;

    isDraggingRef.current = true;
    startPosRef.current = {
      x: e.clientX - transformRef.current.x,
      y: e.clientY - transformRef.current.y
    };
    if (containerRef.current) containerRef.current.style.cursor = 'grabbing';
  };

  const handleMouseMove = useCallback((e) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();

    // 直接计算新坐标
    transformRef.current.x = e.clientX - startPosRef.current.x;
    transformRef.current.y = e.clientY - startPosRef.current.y;

    // 直接操作 DOM，不触发 Re-render
    updateTransform();
  }, []);

  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false;
    if (containerRef.current) containerRef.current.style.cursor = 'grab';
  }, []);

  // 全局事件监听
  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  // 适应窗口大小
  const handleFitToScreen = () => {
    const container = containerRef.current;
    const svgElement = mermaidRef.current?.querySelector('svg');

    if (container && svgElement) {
      const containerRect = container.getBoundingClientRect();
      const svgRect = svgElement.getBoundingClientRect();
      // 重置 transform 以获取原始 SVG 尺寸进行计算
      // 这里的计算略复杂因为 SVG 已经被 transform 了。
      // 简单策略：先重置，计算比例，再应用。

      const widthRatio = containerRect.width / (svgElement.viewBox.baseVal?.width || svgRect.width);
      const heightRatio = containerRect.height / (svgElement.viewBox.baseVal?.height || svgRect.height);

      // 如果 viewBox 获取不到，可能需要更复杂的逻辑，这里简化处理
      const newZoom = Math.min(widthRatio, heightRatio, 1) * 0.9;

      transformRef.current = { x: 0, y: 0, k: newZoom || 1 }; // 居中逻辑可后续优化
      updateTransform();
      setDisplayZoom(Math.round((newZoom || 1) * 100));
    }
  };

  const handleDownload = () => {
    try {
      const svgElement = mermaidRef.current?.querySelector('svg');
      if (!svgElement) {
        toast.error("没有可下载的图表");
        return;
      }
      const svgData = new XMLSerializer().serializeToString(svgElement);
      const blob = new Blob([svgData], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'mermaid-diagram.svg';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("图表已下载");
    } catch (err) {
      console.error('Download error:', err);
      toast.error("下载失败");
    }
  };

  return (
    <div className={`${isFullscreen ? 'fixed inset-0 z-50 bg-background' : 'h-full'} flex flex-col`}>
      {/* Header */}
      <div className="h-12 flex justify-between items-center px-2 flex-shrink-0 border-b bg-background">
        <h3 className="text-sm font-medium">Mermaid 图表</h3>
        <div className="flex gap-2">
          {/* Zoom Controls */}
          <div className="flex gap-0.5 border rounded-md items-center bg-background">
            <Button variant="ghost" size="sm" onClick={handleZoomOut} className="h-7 w-7 p-0" title="缩小">
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <div className="w-10 text-center text-xs select-none">
              {displayZoom}%
            </div>
            <Button variant="ghost" size="sm" onClick={handleZoomIn} className="h-7 w-7 p-0" title="放大">
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Button variant="outline" size="sm" onClick={handleFitToScreen} className="h-7 gap-1 text-xs px-2" title="适应窗口">
            <Move className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">适应</span>
          </Button>

          <Button variant="outline" size="sm" onClick={handleDownload} disabled={!mermaidCode || isLoading || error} className="h-7 gap-1 text-xs px-2">
            <Download className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">下载</span>
          </Button>

          {isFullscreen ? (
            <Button variant="default" size="sm" onClick={() => setIsFullscreen(false)} className="h-7 gap-1 text-xs px-2">
              <Minimize className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">退出</span>
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setIsFullscreen(true)} className="h-7 gap-1 text-xs px-2">
              <Maximize className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">全屏</span>
            </Button>
          )}
        </div>
      </div>

      {/* Canvas Area */}
      <div className="flex-1 border rounded-lg relative min-h-0 bg-gray-50 dark:bg-gray-900 overflow-hidden select-none">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
            <div className="flex items-center space-x-2">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              <span className="text-muted-foreground">渲染中...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
            <div className="text-center p-4">
              <p className="text-destructive mb-2">渲染失败</p>
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
          </div>
        )}

        {!isLoading && !error && !mermaidCode && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-muted-foreground">请生成Mermaid代码以查看图表</p>
          </div>
        )}

        {/* Container for Pan/Zoom */}
        <div
          ref={containerRef}
          className="w-full h-full overflow-hidden cursor-grab active:cursor-grabbing relative"
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
        // Touch events omitted for brevity but logic is similar (update Refs not State)
        >
          {/* Content Wrapper - Applied Transforms */}
          <div
            ref={mermaidRef}
            className="w-full h-full flex items-center justify-center p-4 origin-top-left absolute top-0 left-0 will-change-transform"
            style={{
              // Initial transform
              transform: `scale(${transformRef.current?.k || 1}) translate(${transformRef.current?.x || 0}px, ${transformRef.current?.y || 0}px)`
            }}
          />
        </div>

        {/* Hints */}
        <div className="absolute bottom-2 left-2 bg-background/90 border rounded px-2 py-1 text-xs text-muted-foreground pointer-events-none">
          Shift+滚轮缩放 | 拖拽移动
        </div>
      </div>
    </div>
  );
}