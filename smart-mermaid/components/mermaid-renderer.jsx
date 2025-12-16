"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  Download,
  ZoomIn,
  ZoomOut,
  Minimize,
  Maximize,
  Move,
  Loader2,
  RefreshCw
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * MermaidRenderer 组件 (清晰度修复版)
 * * 修复：移除了 will-change-transform 导致的 SVG 模糊问题
 * * 优化：保留了智能交互和适应屏幕算法
 */
export function MermaidRenderer({ 
  mermaidCode, 
  onChange, 
  onErrorChange, 
  onNodeDoubleClick,
  className 
}) {
  const containerRef = useRef(null);
  const contentRef = useRef(null);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  
  const [displayZoom, setDisplayZoom] = useState(100);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  
  const isDraggingRef = useRef(false);
  const startPosRef = useRef({ x: 0, y: 0 });

  // 初始化 Mermaid
  useEffect(() => {
    const initMermaid = async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          flowchart: { 
            useMaxWidth: false, 
            htmlLabels: true,
            curve: 'basis'
          },
          sequence: { useMaxWidth: false },
          gantt: { useMaxWidth: false },
          journey: { useMaxWidth: false },
        });
      } catch (e) {
        console.error("Mermaid init failed", e);
      }
    };
    initMermaid();
  }, []);

  const updateTransform = useCallback(() => {
    if (contentRef.current) {
      const { x, y, k } = transformRef.current;
      contentRef.current.style.transformOrigin = "0 0";
      // 使用 translate3d 开启硬件加速，但不使用 will-change 以避免模糊
      contentRef.current.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${k})`;
    }
  }, []);

  const setZoom = useCallback((newZoom, syncDisplay = true) => {
    const clampedZoom = Math.max(0.1, Math.min(10, newZoom));
    transformRef.current.k = clampedZoom;
    updateTransform();
    if (syncDisplay) setDisplayZoom(Math.round(clampedZoom * 100));
  }, [updateTransform]);

  const handleFitToScreen = useCallback(() => {
    const container = containerRef.current;
    const svgElement = contentRef.current?.querySelector('svg');

    if (!container || !svgElement) return;

    const { width: containerWidth, height: containerHeight } = container.getBoundingClientRect();
    if (containerWidth === 0 || containerHeight === 0) return;

    let contentWidth = 0;
    let contentHeight = 0;

    if (svgElement.viewBox && svgElement.viewBox.baseVal) {
      contentWidth = svgElement.viewBox.baseVal.width;
      contentHeight = svgElement.viewBox.baseVal.height;
    } else {
      try {
        const bbox = svgElement.getBBox();
        contentWidth = bbox.width;
        contentHeight = bbox.height;
      } catch (e) {
        const rect = svgElement.getBoundingClientRect();
        contentWidth = rect.width / transformRef.current.k;
        contentHeight = rect.height / transformRef.current.k;
      }
    }

    if (!contentWidth || !contentHeight) return;

    const widthRatio = containerWidth / contentWidth;
    const heightRatio = containerHeight / contentHeight;
    let bestScale = Math.min(widthRatio, heightRatio) * 0.95;

    bestScale = Math.min(bestScale, 1.5);
    bestScale = Math.max(bestScale, 0.1);

    const centeredX = (containerWidth - contentWidth * bestScale) / 2;
    const centeredY = (containerHeight - contentHeight * bestScale) / 2;

    transformRef.current = { x: centeredX, y: centeredY, k: bestScale };
    updateTransform();
    setDisplayZoom(Math.round(bestScale * 100));
  }, [updateTransform]);

  useEffect(() => {
    let mounted = true;
    
    const renderDiagram = async () => {
      if (!mermaidCode) {
        setIsLoading(false);
        if (contentRef.current) contentRef.current.innerHTML = '';
        if (onErrorChange) onErrorChange(null, false);
        return;
      }

      try {
        setIsLoading(true);
        setError(null);
        
        const mermaid = (await import("mermaid")).default;
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        
        try {
          await mermaid.parse(mermaidCode);
        } catch (parseError) {
          throw new Error(`Syntax Error: ${parseError.message}`);
        }

        const { svg } = await mermaid.render(id, mermaidCode);
        
        if (mounted && contentRef.current) {
          contentRef.current.innerHTML = svg;
          
          const svgElement = contentRef.current.querySelector('svg');
          if (svgElement) {
            svgElement.style.width = '100%';
            svgElement.style.height = '100%';
            svgElement.style.overflow = 'visible';
            // 强制使用几何精度渲染，确保线条锐利
            svgElement.style.shapeRendering = 'geometricPrecision';
            svgElement.style.textRendering = 'geometricPrecision';

            const nodeSelectors = [
              '.node', '.actor', '.messageText', '.classTitle', 
              '.state', '.entityBox', '.reqBox', '.mindmap-node'
            ];
            
            const interactiveElements = svgElement.querySelectorAll(nodeSelectors.join(','));

            interactiveElements.forEach(el => {
              el.style.cursor = 'pointer';
              el.style.transition = 'opacity 0.2s'; // 移除 filter transition 以减少渲染开销
              
              el.addEventListener('mouseenter', () => {
                el.style.opacity = '0.8';
              });
              el.addEventListener('mouseleave', () => {
                el.style.opacity = '1';
              });

              el.addEventListener('dblclick', (e) => {
                e.preventDefault();
                e.stopPropagation();
                let text = "";
                const textNode = el.querySelector('div, span, text');
                if (textNode) {
                    text = textNode.textContent;
                } else {
                    text = el.textContent;
                }
                text = text.trim().replace(/[\r\n]+/g, ' ');
                if (text && onNodeDoubleClick) {
                  onNodeDoubleClick(text);
                }
              });
            });
          }

          setIsLoading(false);
          if (onErrorChange) onErrorChange(null, false);
          setTimeout(handleFitToScreen, 50);
        }

      } catch (err) {
        console.warn("Mermaid Render Error:", err);
        if (mounted) {
          let msg = err.message;
          if (msg.includes("Parse error")) {
            msg = "Mermaid 语法解析错误，请检查代码格式。";
          }
          setError(msg);
          setIsLoading(false);
          if (onErrorChange) onErrorChange(msg, true);
        }
      }
    };

    renderDiagram();

    return () => {
      mounted = false;
    };
  }, [mermaidCode, onErrorChange, onNodeDoubleClick, handleFitToScreen]);

  // --- 交互处理 ---
  const handleWheel = useCallback((e) => {
    if (!containerRef.current.contains(e.target)) return;
    e.preventDefault();
    e.stopPropagation();

    const rect = containerRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const currentK = transformRef.current.k;
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newK = Math.max(0.1, Math.min(10, currentK * delta));

    const worldX = (mouseX - transformRef.current.x) / currentK;
    const worldY = (mouseY - transformRef.current.y) / currentK;
    
    const newX = mouseX - worldX * newK;
    const newY = mouseY - worldY * newK;

    transformRef.current = { x: newX, y: newY, k: newK };
    updateTransform();

    if (window.mermaidZoomTimeout) clearTimeout(window.mermaidZoomTimeout);
    window.mermaidZoomTimeout = setTimeout(() => {
      setDisplayZoom(Math.round(newK * 100));
    }, 50);
  }, [updateTransform]);

  const handleMouseDown = (e) => {
    if (e.target.closest('button')) return;
    isDraggingRef.current = true;
    startPosRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      x: transformRef.current.x,
      y: transformRef.current.y
    };
    if (containerRef.current) containerRef.current.style.cursor = 'grabbing';
  };

  const handleMouseMove = useCallback((e) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    const dx = e.clientX - startPosRef.current.mouseX;
    const dy = e.clientY - startPosRef.current.mouseY;
    transformRef.current.x = startPosRef.current.x + dx;
    transformRef.current.y = startPosRef.current.y + dy;
    updateTransform(); // 直接 DOM 操作，无 React Render，速度极快且不模糊
  }, [updateTransform]);

  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false;
    if (containerRef.current) containerRef.current.style.cursor = 'grab';
  }, []);

  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const handleDownload = () => {
    try {
      const svgElement = contentRef.current?.querySelector('svg');
      if (!svgElement) {
        toast.error("没有可下载的图表");
        return;
      }
      const clone = svgElement.cloneNode(true);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.style.transform = ''; 
      const svgData = new XMLSerializer().serializeToString(clone);
      const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `mermaid-diagram-${Date.now()}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("图表已下载");
    } catch (err) {
      console.error(err);
      toast.error("下载失败");
    }
  };

  return (
    <div 
      className={cn(
        "flex flex-col bg-background relative",
        isFullscreen ? "fixed inset-0 z-50 h-screen w-screen" : "h-full w-full",
        className
      )}
    >
      {/* Toolbar */}
      <div className="h-12 flex justify-between items-center px-4 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 flex-shrink-0 z-20">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground/80">Mermaid Render</h3>
          {isLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center border rounded-md shadow-sm bg-background">
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-none rounded-l-md" onClick={() => setZoom(transformRef.current.k / 1.2)} title="缩小"><ZoomOut className="h-4 w-4" /></Button>
            <div className="w-12 text-center text-xs font-mono select-none border-x h-4 flex items-center justify-center">{displayZoom}%</div>
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-none rounded-r-md" onClick={() => setZoom(transformRef.current.k * 1.2)} title="放大"><ZoomIn className="h-4 w-4" /></Button>
          </div>
          <div className="w-px h-4 bg-border mx-1" />
          <Button variant="outline" size="sm" onClick={handleFitToScreen} className="h-8 px-2 lg:px-3 text-xs gap-1.5"><Move className="h-3.5 w-3.5" /><span className="hidden lg:inline">适应</span></Button>
          <Button variant="outline" size="sm" onClick={handleDownload} disabled={!mermaidCode || isLoading || !!error} className="h-8 px-2 lg:px-3 text-xs gap-1.5"><Download className="h-3.5 w-3.5" /><span className="hidden lg:inline">下载</span></Button>
          <Button variant={isFullscreen ? "secondary" : "ghost"} size="icon" onClick={() => setIsFullscreen(!isFullscreen)} className="h-8 w-8 ml-1">{isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}</Button>
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 relative overflow-hidden bg-gray-50/50 dark:bg-gray-900/50 select-none">
        {isLoading && <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/60 backdrop-blur-[1px] z-10"><Loader2 className="h-8 w-8 animate-spin text-primary mb-2" /><span className="text-xs text-muted-foreground">Generating...</span></div>}
        {error && <div className="absolute inset-0 flex items-center justify-center p-8 z-10 pointer-events-none"><div className="bg-destructive/10 border border-destructive/20 rounded-lg p-6 max-w-lg text-center backdrop-blur-sm pointer-events-auto"><h4 className="text-destructive font-semibold mb-2">渲染失败</h4><p className="text-xs text-destructive/90 font-mono whitespace-pre-wrap text-left break-words overflow-auto max-h-[200px]">{error}</p></div></div>}
        {!isLoading && !error && !mermaidCode && <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground z-0 pointer-events-none"><RefreshCw className="h-12 w-12 mb-4 opacity-20" /><p className="text-sm">等待生成 Mermaid 代码...</p></div>}
        
        <div 
          ref={containerRef}
          className="w-full h-full cursor-grab active:cursor-grabbing touch-none"
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
        >
          {/* 修复重点：移除了 will-change-transform 
              保留 transform-origin: 0 0 
          */}
          <div 
            ref={contentRef}
            className="origin-top-left absolute top-0 left-0"
            // style 会由 updateTransform 动态控制
          />
        </div>
        <div className="absolute bottom-4 left-4 z-0 pointer-events-none opacity-50 hover:opacity-100 transition-opacity"><div className="bg-background/80 border shadow-sm rounded-md px-2 py-1 text-[10px] text-muted-foreground backdrop-blur-sm">双击节点交互 · 滚轮缩放 · 拖拽移动</div></div>
      </div>
    </div>
  );
}