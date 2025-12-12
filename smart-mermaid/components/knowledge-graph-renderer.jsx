"use client";

import React, { useEffect, useRef, useState, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useTheme } from "next-themes";
import { Loader2 } from "lucide-react";

export function KnowledgeGraphRenderer({ graphData, width, height }) {
  const fgRef = useRef();
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ w: 800, h: 600 });

  // 确保客户端渲染
  useEffect(() => {
    setMounted(true);
    // 初始调整一次大小
    if (containerRef.current) {
        setDimensions({
            w: containerRef.current.offsetWidth,
            h: containerRef.current.offsetHeight
        });
    }

    // 监听窗口大小变化
    const handleResize = () => {
        if (containerRef.current) {
            setDimensions({
                w: containerRef.current.offsetWidth,
                h: containerRef.current.offsetHeight
            });
        }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 当数据初次加载或显著变化时，适当调整力导向参数（可选）
  useEffect(() => {
      if(fgRef.current) {
          fgRef.current.d3Force('charge').strength(-120);
          fgRef.current.d3Force('link').distance(70);
      }
  }, [graphData]);

  if (!mounted) return null;

  // 颜色配置
  const isDark = theme === 'dark';
  const bgColor = isDark ? "#020817" : "#ffffff"; // 适配 shadcn/ui background
  const nodeDefaultColor = isDark ? "#60a5fa" : "#2563eb"; // blue-400 : blue-600
  const linkColor = isDark ? "#475569" : "#cbd5e1"; // slate-600 : slate-300
  const textColor = isDark ? "#e2e8f0" : "#1e293b"; // slate-200 : slate-800

  return (
    <div 
        ref={containerRef} 
        className="w-full h-full border rounded-md overflow-hidden relative bg-background"
    >
       {/* 空状态提示 */}
       {(!graphData || graphData.nodes.length === 0) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground z-10 pointer-events-none gap-2">
            <Loader2 className="h-8 w-8 animate-spin opacity-20" />
            <p className="text-sm">等待图谱数据...</p>
          </div>
       )}

      <ForceGraph2D
        ref={fgRef}
        width={dimensions.w}
        height={dimensions.h}
        graphData={graphData}
        backgroundColor={bgColor}
        
        // 节点配置
        nodeLabel="label"
        nodeRelSize={6}
        nodeColor={node => node.color || nodeDefaultColor}
        
        // 连线配置
        linkColor={() => linkColor}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkWidth={1}
        
        // 自定义节点绘制 (画圆 + 下方文字)
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.label;
          const fontSize = 12 / globalScale; // 文字大小随缩放调整
          
          // 1. 绘制节点圆圈
          const r = node.val ? Math.sqrt(node.val) * 2 : 4; // 根据 val 大小调整半径
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
          ctx.fillStyle = node.color || nodeDefaultColor;
          ctx.fill();
          
          // 2. 绘制选中/高亮边框 (如果需要)
          // if (node.id === 'xxx') { ... }

          // 3. 绘制文字 (只有当缩放比例够大或者是重要节点时才显示，避免太乱，这里简单处理全部显示)
          if (globalScale > 0.8) {
            ctx.font = `${fontSize}px Sans-Serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillStyle = textColor;
            // 文字画在节点下方
            ctx.fillText(label, node.x, node.y + r + 1); 
          }
          
          // 4. 定义交互区域 (用于鼠标 hover 检测)
          node.__bckgDimensions = [r*2 + 4, r*2 + 4]; // 简单粗略
        }}
        nodePointerAreaPaint={(node, color, ctx) => {
          const r = node.val ? Math.sqrt(node.val) * 2 : 4;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI, false);
          ctx.fill();
        }}
      />
    </div>
  );
}