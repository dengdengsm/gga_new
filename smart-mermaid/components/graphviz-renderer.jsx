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

/**
 * GraphvizRenderer 组件 (最终修复版)
 * * 修复：彻底解决了“适应屏幕”反而变得极小的 Bug (双重缩放问题)
 * * 逻辑：强制 SVG 使用 viewBox 的真实物理尺寸渲染，确保 transform 缩放基准正确
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
    // 注意：这里我们使用状态里存的 svgSize，或者直接读 viewBox
    // 关键是不要读 getBoundingClientRect()，因为它受当前 scale 影响
    
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
    // 重置回 1:1，并居中显示一部分
    const container = containerRef.current;
    if (!container) return;
    const { width, height } = container.getBoundingClientRect();
    
    // 简单居中画布的(0,0)点到屏幕中心，或者复位到左上角
    // 这里选择复位到左上角稍微偏移一点
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
            // 1. 获取 SVG 的真实视图尺寸 (ViewBox)
            let baseWidth = 0;
            let baseHeight = 0;

            if (svgElement.viewBox && svgElement.viewBox.baseVal) {
              baseWidth = svgElement.viewBox.baseVal.width;
              baseHeight = svgElement.viewBox.baseVal.height;
            } else {
              // 备用：解析 width/height 属性 (通常是 "xxpt")
              baseWidth = parseFloat(svgElement.getAttribute("width")) || 1000;
              baseHeight = parseFloat(svgElement.getAttribute("height")) || 1000;
            }

            // 2. 强制设置 SVG 为真实像素尺寸
            // 这禁止了浏览器默认的 "contain" 缩放行为
            svgElement.style.width = `${baseWidth}px`;
            svgElement.style.height = `${baseHeight}px`;
            
            // 3. 移除可能导致冲突的属性
            svgElement.removeAttribute('width');
            svgElement.removeAttribute('height');
            
            svgElement.style.display = 'block';
            svgElement.style.shapeRendering = 'geometricPrecision'; // 锐利渲染

            // 4. 更新状态供 FitToScreen 使用
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
  }, [code, onErrorChange, onNodeDoubleClick]); // 移除了 handleFitToScreen 依赖，防止循环

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
    if (e.target.closest('button')) return;
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
      const clone = svgElement.cloneNode(true);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.style.transform = ''; 
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
      <div className="h-12 flex justify-between items-center px-4 border-b bg-background/95 backdrop-blur z-20">
        <div className="flex items-center gap-2"><h3 className="text-sm font-semibold">Graphviz</h3>{isLoading && <Loader2 className="h-3 w-3 animate-spin" />}</div>
        <div className="flex items-center gap-2">
          <div className="flex items-center border rounded-md bg-background">
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-l-md" onClick={() => setZoom(transformRef.current.k / 1.5)}><ZoomOut className="h-4 w-4" /></Button>
            <div className="w-14 text-center text-xs font-mono border-x h-4 flex items-center justify-center">{displayZoom}%</div>
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-r-md" onClick={() => setZoom(transformRef.current.k * 1.5)}><ZoomIn className="h-4 w-4" /></Button>
          </div>
          <div className="w-px h-4 bg-border mx-1" />
          <Button variant="outline" size="icon" onClick={handleResetZoom} className="h-8 w-8" title="1:1 原始比例"><ScanSearch className="h-4 w-4" /></Button>
          <Button variant="outline" size="sm" onClick={() => handleFitToScreen(true)} className="h-8 px-2 text-xs gap-1.5"><Move className="h-3.5 w-3.5" /><span>适应</span></Button>
          <Button variant="outline" size="sm" onClick={handleDownload} disabled={!code || isLoading} className="h-8 px-2 text-xs gap-1.5"><Download className="h-3.5 w-3.5" /><span>下载</span></Button>
          <Button variant={isFullscreen ? "secondary" : "ghost"} size="icon" onClick={() => setIsFullscreen(!isFullscreen)} className="h-8 w-8 ml-1">{isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}</Button>
        </div>
      </div>

      <div className="flex-1 relative overflow-hidden bg-gray-50/50 dark:bg-gray-900/50 select-none">
        {isLoading && <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/60 z-10"><Loader2 className="h-8 w-8 animate-spin text-primary mb-2" /><span className="text-xs text-muted-foreground">渲染中...</span></div>}
        {error && <div className="absolute inset-0 flex items-center justify-center p-8 z-10 pointer-events-none"><div className="bg-destructive/10 border border-destructive/20 rounded-lg p-6 max-w-lg text-center backdrop-blur-sm pointer-events-auto"><p className="text-sm text-destructive">{error}</p></div></div>}
        {!isLoading && !error && !code && <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground z-0 pointer-events-none"><Move className="h-12 w-12 mb-4 opacity-20" /><p className="text-sm">等待生成 Graphviz 代码...</p></div>}

        <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing touch-none" onWheel={handleWheel} onMouseDown={handleMouseDown}>
          <div ref={graphRef} className="origin-top-left absolute top-0 left-0" />
        </div>
        <div className="absolute bottom-4 left-4 z-0 pointer-events-none opacity-50 hover:opacity-100 transition-opacity"><div className="bg-background/80 border shadow-sm rounded-md px-2 py-1 text-[10px] text-muted-foreground backdrop-blur-sm">双击节点查看详情 · 滚轮缩放(最高100倍) · 拖拽移动</div></div>
      </div>
    </div>
  );
}