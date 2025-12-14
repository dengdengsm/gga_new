"use client";

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useTheme } from "next-themes";
import { Loader2 } from "lucide-react";
import { forceRadial, forceCollide } from 'd3-force';
import dynamic from 'next/dynamic';

// 动态引入，关闭 SSR
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground bg-background/50">
      <Loader2 className="h-8 w-8 animate-spin mb-2" />
      <p className="text-sm">正在加载图谱引擎...</p>
    </div>
  )
});

export function KnowledgeGraphRenderer({ graphData, width, height }) {
  // 1. 使用 ref 存储实例，但不依赖它触发渲染
  const fgRef = useRef();
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ w: 800, h: 600 });

  // 2. 抽离核心配置逻辑：应用力导向参数
  const applyCustomForces = useCallback((fgInstance) => {
    if (!fgInstance) return;

    // 1. 刚性连线
    fgInstance.d3Force('link')
      .distance(50)
      .strength(0.8);

    // 2. 向心引力（实心圆面）
    fgInstance.d3Force('radial', forceRadial(0, 0, 0).strength(0.2));

    // 3. 斥力
    fgInstance.d3Force('charge').strength(-120);

    // 4. 防重叠
    fgInstance.d3Force('collide', forceCollide(node => {
      const r = node.val ? Math.sqrt(node.val) * 2 : 4;
      return r + 5;
    }).strength(1));

    // 5. 重启模拟器
    fgInstance.d3ReheatSimulation();
  }, []);

  // 3. 【关键修复】使用 Callback Ref 替代普通 Ref
  // 当 ForceGraph2D 真正挂载完成时，React 会调用这个函数，并传入实例
  const onFgRefChange = useCallback((node) => {
    if (node) {
      fgRef.current = node; // 保存到 ref 以便后续使用
      applyCustomForces(node); // 挂载瞬间，立即应用力！
    }
  }, [applyCustomForces]);

  // 4. 监听数据变化（防止数据更新后配置丢失）
  useEffect(() => {
    if (fgRef.current && graphData) {
      // 数据变了，重新应用一次力，确保不被重置
      applyCustomForces(fgRef.current);
    }
  }, [graphData, applyCustomForces]);

  // --- 核心修复：使用 ResizeObserver 监听容器大小 ---
  useEffect(() => {
    setMounted(true);

    // 创建观察器：一旦容器大小变了，就更新 dimensions
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ w: width, h: height });
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, []); // 这里的依赖是空数组，只在挂载时运行一次

  if (!mounted) return null;

  const isDark = theme === 'dark';
  const bgColor = isDark ? "#020817" : "#ffffff";
  const nodeDefaultColor = isDark ? "#60a5fa" : "#2563eb";
  const linkColor = isDark ? "#475569" : "#cbd5e1";
  const textColor = isDark ? "#e2e8f0" : "#1e293b";

  return (
    <div
      ref={containerRef}
      className="w-full h-full border rounded-md overflow-hidden relative bg-background"
    >
      {(!graphData || graphData.nodes.length === 0) && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground z-10 pointer-events-none gap-2">
          <Loader2 className="h-8 w-8 animate-spin opacity-20" />
          <p className="text-sm">等待图谱数据...</p>
        </div>
      )}

      <ForceGraph2D
        ref={onFgRefChange} // <--- 这里改用了 Callback Ref
        width={dimensions.w}
        height={dimensions.h}
        graphData={graphData}
        backgroundColor={bgColor}

        nodeLabel="label"
        nodeRelSize={6}
        nodeColor={node => node.color || nodeDefaultColor}

        linkColor={() => linkColor}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkWidth={1}

        // 预热时间：给一点时间让力生效后再显示，避免初始炸裂
        cooldownTicks={100}
        onEngineStop={() => {
          // 双重保险：引擎停止时如果发现还没收敛好，可以再次微调（可选）
          if (fgRef.current) fgRef.current.zoomToFit(400);
        }}

        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.label;
          const fontSize = 12 / globalScale;

          const r = node.val ? Math.sqrt(node.val) * 2 : 4;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
          ctx.fillStyle = node.color || nodeDefaultColor;
          ctx.fill();

          if (globalScale > 0.8) {
            ctx.font = `${fontSize}px Sans-Serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillStyle = textColor;
            ctx.fillText(label, node.x, node.y + r + 1);
          }

          node.__bckgDimensions = [r * 2 + 4, r * 2 + 4];
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