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
  ScanSearch
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { GraphvizStyleManager } from "@/components/graphviz-style-manager";

/**
 * GraphvizRenderer 组件
 * * 集成了 AI 样式生成功能
 * * 保持了原有的双重缩放修复和适应屏幕逻辑
 */
export function GraphvizRenderer({ 
  code, 
  onNodeDoubleClick, 
  onErrorChange,
  className 
}) {
  const containerRef = useRef(null);
  const graphRef = useRef(null);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  
  // 样式状态
  const [currentStyle, setCurrentStyle] = useState({ css: "", svgDefs: "" });

  const MIN_ZOOM = 0.05;
  const MAX_ZOOM = 100;

  const [displayZoom, setDisplayZoom] = useState(100);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 }); // 记录 SVG 真实尺寸

  const isDraggingRef = useRef(false);
  const startPosRef = useRef({ x: 0, y: 0 });

  const updateTransform = useCallback(() => {
    if (graphRef.current) {
      const { x, y, k } = transformRef.current;
      graphRef.current.style.transformOrigin = "0 0";
      graphRef.current.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${k})`;
    }
  }, []);

  const setZoom = useCallback((newZoom, syncDisplay = true) => {
    const clampedZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom));
    transformRef.current.k = clampedZoom;
    updateTransform();
    if (syncDisplay) setDisplayZoom(Math.round(clampedZoom * 100));
  }, [updateTransform]);

  /**
   * 适应屏幕算法
   */
  const handleFitToScreen = useCallback((forceFit = false) => {
    const container = containerRef.current;
    if (!container || svgSize.width === 0 || svgSize.height === 0) return;

    const { width: containerWidth, height: containerHeight } = container.getBoundingClientRect();
    if (containerWidth === 0 || containerHeight === 0) return;

    // 计算比例
    const widthRatio = containerWidth / svgSize.width;
    const heightRatio = containerHeight / svgSize.height;

    // 留 5% 边距
    let bestScale = Math.min(widthRatio, heightRatio) * 0.95;

    // 智能逻辑：非强制模式下，如果图太大导致缩得太小，就限制最小比例
    if (!forceFit) {
       if (bestScale < 0.3) {
           bestScale = Math.min(0.5, 1.0); 
       }
    }

    // 居中计算
    const centeredX = (containerWidth - svgSize.width * bestScale) / 2;
    const centeredY = (containerHeight - svgSize.height * bestScale) / 2;

    transformRef.current = { x: centeredX, y: centeredY, k: bestScale };
    updateTransform();
    setDisplayZoom(Math.round(bestScale * 100));
  }, [updateTransform, svgSize]);

  const handleResetZoom = () => {
    transformRef.current = { x: 20, y: 20, k: 1.0 };
    updateTransform();
    setDisplayZoom(100);
  };

  useEffect(() => {
    let mounted = true;

    const renderGraph = async () => {
      if (!code) {
        setIsLoading(false);
        if (graphRef.current) graphRef.current.innerHTML = '';
        if (onErrorChange) onErrorChange(null, false);
        return;
      }

      try {
        setIsLoading(true);
        setError(null);

        const { Graphviz } = await import("@hpcc-js/wasm");
        const graphviz = await Graphviz.load();

        if (!mounted) return;

        const svgString = graphviz.layout(code, "svg", "dot");

        if (graphRef.current) {
          graphRef.current.innerHTML = svgString;

          const svgElement = graphRef.current.querySelector('svg');
          if (svgElement) {
            // --- 核心修复开始 ---
            let baseWidth = 0;
            let baseHeight = 0;

            if (svgElement.viewBox && svgElement.viewBox.baseVal) {
              baseWidth = svgElement.viewBox.baseVal.width;
              baseHeight = svgElement.viewBox.baseVal.height;
            } else {
              baseWidth = parseFloat(svgElement.getAttribute("width")) || 1000;
              baseHeight = parseFloat(svgElement.getAttribute("height")) || 1000;
            }

            // 强制设置 SVG 为真实像素尺寸
            svgElement.style.width = `${baseWidth}px`;
            svgElement.style.height = `${baseHeight}px`;
            
            svgElement.removeAttribute('width');
            svgElement.removeAttribute('height');
            svgElement.style.display = 'block';
            
            // 注意：不再强制设置 shapeRendering，由 CSS 控制
            // svgElement.style.shapeRendering = 'geometricPrecision';

            setSvgSize({ width: baseWidth, height: baseHeight });
            // --- 核心修复结束 ---

            // 节点交互
            const nodes = svgElement.querySelectorAll('.node');
            nodes.forEach(node => {
              node.style.cursor = 'pointer';
              node.style.transition = 'opacity 0.2s';
              node.addEventListener('dblclick', (e) => {
                e.preventDefault(); e.stopPropagation();
                const text = node.textContent?.trim();
                if (text && onNodeDoubleClick) onNodeDoubleClick(text);
              });
              node.addEventListener('mouseenter', () => node.style.opacity = '0.7');
              node.addEventListener('mouseleave', () => node.style.opacity = '1.0');
            });
          }

          setIsLoading(false);
          if (onErrorChange) onErrorChange(null, false);
        }
      } catch (err) {
        console.error("Graphviz Render Error:", err);
        if (mounted) {
          setError(err.message || "Render error");
          setIsLoading(false);
          if (onErrorChange) onErrorChange(err.message, true);
        }
      }
    };

    renderGraph();

    return () => {
      mounted = false;
      if (graphRef.current) graphRef.current.innerHTML = '';
    };
  }, [code, onErrorChange, onNodeDoubleClick]);

  // 监听 svgSize 变化来触发首次适应
  useEffect(() => {
    if (svgSize.width > 0 && svgSize.height > 0) {
      handleFitToScreen(false); // 首次加载，智能适应
    }
  }, [svgSize, handleFitToScreen]);


  // --- 交互 ---
  const handleWheel = useCallback((e) => {
    if (!containerRef.current.contains(e.target)) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey || true) {
      e.preventDefault(); e.stopPropagation();
      const rect = containerRef.current.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const { x, y, k } = transformRef.current;
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      const newK = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, k * delta));
      const worldX = (mouseX - x) / k;
      const worldY = (mouseY - y) / k;
      const newX = mouseX - worldX * newK;
      const newY = mouseY - worldY * newK;
      transformRef.current = { x: newX, y: newY, k: newK };
      updateTransform();
      if (window.gZoomT) clearTimeout(window.gZoomT);
      window.gZoomT = setTimeout(() => setDisplayZoom(Math.round(newK * 100)), 50);
    }
  }, [updateTransform]);

  const handleMouseDown = (e) => {
    // 忽略特定元素的点击，避免拖拽冲突
    if (e.target.closest('button') || e.target.closest('[role="combobox"]')) return;
    
    isDraggingRef.current = true;
    startPosRef.current = { mouseX: e.clientX, mouseY: e.clientY, x: transformRef.current.x, y: transformRef.current.y };
    if (containerRef.current) containerRef.current.style.cursor = 'grabbing';
  };

  const handleMouseMove = useCallback((e) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    const dx = e.clientX - startPosRef.current.mouseX;
    const dy = e.clientY - startPosRef.current.mouseY;
    transformRef.current.x = startPosRef.current.x + dx;
    transformRef.current.y = startPosRef.current.y + dy;
    updateTransform();
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
      const svgElement = graphRef.current?.querySelector('svg');
      if (!svgElement) return;
      
      // 克隆节点以应用内联样式（虽然 CSS 已经控制了大部分）
      const clone = svgElement.cloneNode(true);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.style.transform = ''; 
      
      // 如果有自定义 Defs，需要手动插入到克隆的 SVG 中以便下载文件包含滤镜
      if (currentStyle.svgDefs) {
        const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
        defs.innerHTML = currentStyle.svgDefs;
        clone.prepend(defs);
      }
      
      // 将当前生效的 CSS 也内联进去（高级功能，可选，这里简化处理不完全内联 CSS 类）
      // 简单方案：只保留 Defs。CSS 类在外部文件查看时可能失效，
      // 但对于 SVG 滤镜效果，只要 Defs 在，且 ID 匹配，就能看到。

      const svgData = new XMLSerializer().serializeToString(clone);
      const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `graphviz-${Date.now()}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("已下载");
    } catch (err) { toast.error("下载失败"); }
  };

  return (
    <div className={cn("flex flex-col bg-background relative", isFullscreen ? "fixed inset-0 z-50 h-screen w-screen" : "h-full w-full", className)}>
      
      {/* 1. 动态 CSS 注入 */}
      {currentStyle.css && (
        <style dangerouslySetInnerHTML={{ __html: currentStyle.css }} />
      )}

      {/* 2. 动态 SVG 滤镜注入 (隐藏) */}
      <svg width="0" height="0" className="absolute w-0 h-0 pointer-events-none">
        {currentStyle.svgDefs && (
          <defs dangerouslySetInnerHTML={{ __html: currentStyle.svgDefs }} />
        )}
      </svg>

      <div className="h-12 flex justify-between items-center px-4 border-b bg-background/95 backdrop-blur z-20">
        <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Graphviz</h3>
            {isLoading && <Loader2 className="h-3 w-3 animate-spin" />}
        </div>
        
        <div className="flex items-center gap-2">
          {/* 3. 样式管理器 */}
          <GraphvizStyleManager onStyleChange={setCurrentStyle} />

          <div className="w-px h-4 bg-border mx-1" />

          <div className="flex items-center border rounded-md bg-background">
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-l-md" onClick={() => setZoom(transformRef.current.k / 1.5)}><ZoomOut className="h-4 w-4" /></Button>
            <div className="w-14 text-center text-xs font-mono border-x h-4 flex items-center justify-center">{displayZoom}%</div>
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-r-md" onClick={() => setZoom(transformRef.current.k * 1.5)}><ZoomIn className="h-4 w-4" /></Button>
          </div>
          
          <Button variant="outline" size="icon" onClick={handleResetZoom} className="h-8 w-8 ml-1" title="1:1 原始比例"><ScanSearch className="h-4 w-4" /></Button>
          <Button variant="outline" size="sm" onClick={() => handleFitToScreen(true)} className="h-8 px-2 text-xs gap-1.5"><Move className="h-3.5 w-3.5" /><span>适应</span></Button>
          <Button variant="outline" size="sm" onClick={handleDownload} disabled={!code || isLoading} className="h-8 px-2 text-xs gap-1.5"><Download className="h-3.5 w-3.5" /><span>下载</span></Button>
          <Button variant={isFullscreen ? "secondary" : "ghost"} size="icon" onClick={() => setIsFullscreen(!isFullscreen)} className="h-8 w-8 ml-1">{isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}</Button>
        </div>
      </div>

      <div className={cn(
          "flex-1 relative overflow-hidden select-none transition-colors duration-300",
          // 移除硬编码的背景色，让 CSS 控制，或者保留默认值
          !currentStyle.css && "bg-gray-50/50 dark:bg-gray-900/50"
        )}>
        {isLoading && <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/60 z-10"><Loader2 className="h-8 w-8 animate-spin text-primary mb-2" /><span className="text-xs text-muted-foreground">渲染中...</span></div>}
        {error && <div className="absolute inset-0 flex items-center justify-center p-8 z-10 pointer-events-none"><div className="bg-destructive/10 border border-destructive/20 rounded-lg p-6 max-w-lg text-center backdrop-blur-sm pointer-events-auto"><p className="text-sm text-destructive">{error}</p></div></div>}
        {!isLoading && !error && !code && <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground z-0 pointer-events-none"><Move className="h-12 w-12 mb-4 opacity-20" /><p className="text-sm">等待生成 Graphviz 代码...</p></div>}

        <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing touch-none" onWheel={handleWheel} onMouseDown={handleMouseDown}>
          <div ref={graphRef} className="origin-top-left absolute top-0 left-0" />
        </div>
      </div>
    </div>
  );
}