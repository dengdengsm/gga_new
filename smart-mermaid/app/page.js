"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Wand2, Network, GitGraph } from "lucide-react"; // 引入 GitGraph 图标作为 Graphviz 的临时图标
import { Header } from "@/components/header";
import { SettingsDialog } from "@/components/settings-dialog";
import { TextInput } from "@/components/text-input";
import { FileUpload } from "@/components/file-upload";
import { DiagramTypeSelector } from "@/components/diagram-type-selector";
import { MermaidEditor } from "@/components/mermaid-editor";
import { MermaidRenderer } from "@/components/mermaid-renderer";
import { GraphvizRenderer } from "@/components/graphviz-renderer"; // [新增] 引入 Graphviz 渲染器
import { GenerationControls } from "@/components/generation-controls";
import { generateMermaidFromText } from "@/lib/ai-service";
import { isWithinCharLimit, cn } from "@/lib/utils";
import { isPasswordVerified, hasCustomAIConfig } from "@/lib/config-service";
import { HistoryList } from "@/components/history-list";
import { getHistory, addHistoryEntry } from "@/lib/history-service";
import dynamic from "next/dynamic";

// 动态导入渲染组件
const ExcalidrawRenderer = dynamic(() => import("@/components/excalidraw-renderer"), { ssr: false });
const KnowledgeGraphRenderer = dynamic(() => import("@/components/knowledge-graph-renderer").then(mod => mod.KnowledgeGraphRenderer), { ssr: false });

export default function Home() {
  const [inputText, setInputText] = useState("");
  const [mermaidCode, setMermaidCode] = useState("");
  const [diagramType, setDiagramType] = useState("auto");
  const [isGenerating, setIsGenerating] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [passwordVerified, setPasswordVerified] = useState(false);
  const [hasCustomConfig, setHasCustomConfig] = useState(false);

  // --- 生成策略状态 ---
  const [useGraph, setUseGraph] = useState(false);
  const [useFileContext, setUseFileContext] = useState(true);
  const [useHistory, setUseHistory] = useState(false);
  const [useMistakes, setUseMistakes] = useState(false);
  const [richness, setRichness] = useState(0.5);

  // 渲染模式：mermaid | graphviz | excalidraw | graph
  const [renderMode, setRenderMode] = useState("mermaid");

  const [leftTab, setLeftTab] = useState("manual");
  const [historyEntries, setHistoryEntries] = useState([]);

  // --- 布局状态 ---
  const [isEditorCollapsed, setIsEditorCollapsed] = useState(false);

  // 知识图谱相关状态
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const graphPollingInterval = useRef(null);

  const [errorMessage, setErrorMessage] = useState(null);
  const [hasError, setHasError] = useState(false);

  const maxChars = parseInt(process.env.NEXT_PUBLIC_MAX_CHARS || "20000");
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    setPasswordVerified(isPasswordVerified());
    setHasCustomConfig(hasCustomAIConfig());
    setHistoryEntries(getHistory());
  }, []);

  const refreshHistory = async () => {
    const history = await getHistory();
    setHistoryEntries(history);
  };

  const handleTextChange = (text) => {
    setInputText(text);
  };

  const handleDiagramTypeChange = (type) => {
    setDiagramType(type);
    // [新增] 如果用户手动选择了 Graphviz，自动切换视图
    if (type === 'graphviz') {
      setRenderMode('graphviz');
    } else if (type !== 'auto' && renderMode === 'graphviz') {
      // 如果用户从 Graphviz 切回其他类型（非自动），切回 Mermaid 视图
      setRenderMode('mermaid');
    }
  };

  const handleMermaidCodeChange = (code) => {
    setMermaidCode(code);
  };

  const handleSettingsClick = () => {
    setShowSettingsDialog(true);
  };

  const handlePasswordVerified = (verified) => {
    setPasswordVerified(verified);
  };

  const handleConfigUpdated = () => {
    setHasCustomConfig(hasCustomAIConfig());
  };

  useEffect(() => {
    if (renderMode === "excalidraw") {
      const t = setTimeout(() => {
        try {
          window.dispatchEvent(new CustomEvent('resetView'));
        } catch { }
      }, 0);
      return () => clearTimeout(t);
    }
  }, [renderMode]);

  // --- 知识图谱轮询逻辑 ---
  const fetchGraphData = async () => {
    if (!useGraph && renderMode === 'graph') return;

    try {
      const res = await fetch(`${API_URL}/api/graph/data`);
      if (res.ok) {
        const data = await res.json();
        setGraphData(prev => {
          if (prev.nodes.length !== data.nodes.length || prev.links.length !== data.links.length) {
            return data;
          }
          return prev;
        });
      }
    } catch (error) {
      console.error("Failed to fetch graph data:", error);
    }
  };

  useEffect(() => {
    if (renderMode === 'graph' && useGraph) {
      fetchGraphData();
      graphPollingInterval.current = setInterval(fetchGraphData, 2000);
    } else {
      if (graphPollingInterval.current) {
        clearInterval(graphPollingInterval.current);
        graphPollingInterval.current = null;
      }
    }

    return () => {
      if (graphPollingInterval.current) {
        clearInterval(graphPollingInterval.current);
      }
    };
  }, [renderMode, useGraph]);

  const handleErrorChange = (error, hasErr) => {
    setErrorMessage(error);
    setHasError(hasErr);
  };

  const handleGenerateClick = async (overrideText = null) => {
    const textToUse = (typeof overrideText === 'string') ? overrideText : inputText;

    if (!textToUse.trim()) {
      toast.error("请输入文本内容");
      return;
    }

    if (!isWithinCharLimit(textToUse, maxChars)) {
      toast.error(`文本超过${maxChars}字符限制`);
      return;
    }

    setIsGenerating(true);

    try {
      const { mermaidCode: generatedCode, error } = await generateMermaidFromText(
        textToUse,
        diagramType,
        null,
        useGraph,
        useFileContext,
        richness,
        useHistory,
        useMistakes
      );

      if (error) {
        toast.error(error);
        return;
      }

      if (!generatedCode) {
        toast.error("生成图表失败，请重试");
        return;
      }

      setMermaidCode(generatedCode);
      
      // [新增] 智能视图切换
      // 如果明确是 Graphviz 类型，切到 Graphviz 视图
      // 如果当前在 Graphviz 视图但生成了 Mermaid (且不是 auto)，切回 Mermaid
      if (diagramType === 'graphviz') {
        setRenderMode('graphviz');
      } else if (renderMode === 'graphviz' && diagramType !== 'auto') {
        setRenderMode('mermaid');
      }

      try {
        addHistoryEntry({
          query: textToUse,
          code: generatedCode,
          diagramType
        });
        setTimeout(refreshHistory, 100);
      } catch (e) {
        console.error("Failed to save history:", e);
      }
      toast.success("图表生成成功");
    } catch (error) {
      console.error("Generation error:", error);
      toast.error("生成图表时发生错误");
    } finally {
      setIsGenerating(false);
    }
  };

  // 下钻分析 (支持 Mermaid 和 Graphviz)
  const handleDrillDown = (nodeLabel) => {
    if (!nodeLabel) return;

    // 简单清洗 label
    const cleanLabel = nodeLabel.replace(/['"]+/g, '');
    const promptText = `Please generate a detailed subgraph/diagram for the node [${cleanLabel}] showing its internal logic or structure.`;

    let newText;

    if (useFileContext) {
      newText = promptText;
    } else {
      newText = inputText + "\n\n" + promptText;
    }

    setInputText(newText);
    setLeftTab("manual");
    handleGenerateClick(newText);

    toast.info(`正在生成节点 "${cleanLabel}" 的详情...`);
  };

  return (
    <div className="flex flex-col min-h-screen">
      <Header
        onSettingsClick={handleSettingsClick}
        isPasswordVerified={passwordVerified}
        hasCustomConfig={hasCustomConfig}
      />

      <main className="flex-1">
        <div className="h-full p-4 md:p-6">
          <div
            className="h-full grid gap-4 md:gap-6 grid-cols-1 md:grid-cols-3 transition-all duration-300"
          >
            {/* 左侧面板 */}
            <div className="col-span-1 flex flex-col h-full overflow-hidden">

              <Tabs value={leftTab} onValueChange={setLeftTab} className="flex flex-col h-full">

                <div className="flex justify-between items-center pb-3 gap-2 flex-wrap">
                  <TabsList className="h-9">
                    <TabsTrigger value="manual">手动输入</TabsTrigger>
                    <TabsTrigger value="file">文件上传</TabsTrigger>
                    <TabsTrigger value="history">历史记录</TabsTrigger>
                  </TabsList>

                  <div className="flex items-center gap-2 flex-1 justify-end min-w-0">
                    <div className="w-[140px] flex-shrink-0">
                      <DiagramTypeSelector
                        value={diagramType}
                        onChange={handleDiagramTypeChange}
                      />
                    </div>

                    <GenerationControls
                      useFileContext={useFileContext}
                      setUseFileContext={setUseFileContext}
                      useGraph={useGraph}
                      setUseGraph={setUseGraph}
                      richness={richness}
                      useMistakes={useMistakes}
                      setUseMistakes={setUseMistakes}
                      setRichness={setRichness}
                    />
                  </div>
                </div>

                <div className="flex-1 flex flex-col overflow-hidden mt-0">
                  <div className={cn(
                    "flex-shrink-0 transition-all duration-300",
                    isEditorCollapsed ? "flex-1 min-h-0" : "h-40 md:h-52"
                  )}>
                    <TabsContent value="manual" className="h-full mt-0">
                      <TextInput
                        value={inputText}
                        onChange={handleTextChange}
                        maxChars={maxChars}
                      />
                    </TabsContent>
                    <TabsContent value="file" className="h-full mt-0">
                      <FileUpload autoBuild={useGraph} />
                    </TabsContent>
                    <TabsContent value="history" className="h-full mt-0">
                      <HistoryList
                        items={historyEntries}
                        onSelect={(item) => {
                          setInputText(item.query || item.inputText || "");
                          setMermaidCode(item.code || item.mermaidCode || "");
                          setLeftTab("manual");
                          // 如果历史记录中有图表类型，恢复它并切换视图
                          if (item.diagramType) {
                            setDiagramType(item.diagramType);
                            if (item.diagramType === 'graphviz') setRenderMode('graphviz');
                            else setRenderMode('mermaid');
                          }
                        }}
                      />
                    </TabsContent>
                  </div>

                  <div className="h-16 flex items-center gap-2 flex-shrink-0 pt-2">
                    <Button
                      onClick={() => handleGenerateClick()}
                      disabled={isGenerating || !inputText.trim() || !isWithinCharLimit(inputText, maxChars)}
                      className="h-10 flex-1 shadow-sm"
                    >
                      {isGenerating ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-background mr-2"></div>
                          {useFileContext ? (useGraph ? "检索图谱并生成..." : "读取文档并生成...") : "仅根据文本生成..."}
                        </>
                      ) : (
                        <>
                          <Wand2 className="mr-2 h-4 w-4" />
                          生成图表
                        </>
                      )}
                    </Button>
                  </div>

                  <div className={cn(
                    "pt-2 transition-all duration-300",
                    isEditorCollapsed ? "h-auto flex-shrink-0" : "flex-1 min-h-0"
                  )}>
                    <MermaidEditor
                      code={mermaidCode}
                      onChange={handleMermaidCodeChange}
                      errorMessage={errorMessage}
                      hasError={hasError}
                      onHistoryChange={refreshHistory}
                      isCollapsed={isEditorCollapsed}
                      onToggleCollapse={() => setIsEditorCollapsed(!isEditorCollapsed)}
                      onDrillDown={handleDrillDown}
                    />
                  </div>
                </div>
              </Tabs>
            </div>

            {/* 右侧面板 */}
            <div className="col-span-1 md:col-span-2 flex flex-col h-full">
              {/* Header */}
              <div className="h-12 flex justify-between items-center flex-shrink-0">
                <div className="flex items-center gap-2 bg-muted p-1 rounded-lg overflow-x-auto no-scrollbar">
                  <Button
                    variant={renderMode === "mermaid" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setRenderMode("mermaid")}
                    className="h-8 text-xs px-3"
                  >
                    Mermaid
                  </Button>
                  
                  {/* [新增] Graphviz 切换按钮 */}
                  <Button
                    variant={renderMode === "graphviz" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setRenderMode("graphviz")}
                    className="h-8 text-xs px-3 gap-1"
                    title="Graphviz DOT 渲染器"
                  >
                    <GitGraph className="h-3.5 w-3.5" />
                    <span>Graphviz</span>
                  </Button>

                  <Button
                    variant={renderMode === "excalidraw" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setRenderMode("excalidraw")}
                    className="h-8 text-xs px-3"
                  >
                    Excalidraw
                  </Button>
                  <Button
                    variant={renderMode === "graph" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setRenderMode("graph")}
                    className="h-8 text-xs px-3 gap-1"
                    disabled={!useGraph || !useFileContext}
                    title={!useGraph || !useFileContext ? "需开启'依赖文件'和'RAG图谱'模式" : "查看知识图谱"}
                  >
                    <Network className="h-3 w-3" />
                    知识图谱
                  </Button>
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {renderMode === 'graph' && useGraph && useFileContext && (
                    <span className="flex items-center animate-pulse">
                      <span className="h-2 w-2 rounded-full bg-green-500 mr-2"></span>
                      Live Sync
                    </span>
                  )}
                </div>
              </div>

              <div className="flex-1 mt-4 overflow-y-auto min-h-[600px] border rounded-lg bg-background shadow-sm">
                {renderMode === "mermaid" && (
                  <MermaidRenderer
                    mermaidCode={mermaidCode}
                    onChange={handleMermaidCodeChange}
                    onErrorChange={handleErrorChange}
                    onNodeDoubleClick={handleDrillDown}
                  />
                )}
                
                {/* [新增] Graphviz 渲染器挂载 */}
                {renderMode === "graphviz" && (
                  <GraphvizRenderer
                    code={mermaidCode} // 复用 mermaidCode 状态存储 DOT 代码
                    onChange={handleMermaidCodeChange}
                    onErrorChange={handleErrorChange}
                    onNodeDoubleClick={handleDrillDown}
                  />
                )}

                {renderMode === "excalidraw" && (
                  <ExcalidrawRenderer
                    mermaidCode={mermaidCode}
                    onErrorChange={handleErrorChange}
                  />
                )}
                
                {renderMode === "graph" && useGraph && useFileContext && (
                  <KnowledgeGraphRenderer
                    graphData={graphData}
                  />
                )}
                {renderMode === "graph" && (!useGraph || !useFileContext) && (
                  <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                    <Network className="h-12 w-12 mb-4 opacity-20" />
                    <p>知识图谱可视化不可用</p>
                    <p className="text-sm mt-2">请确保已开启“依赖文件”和“RAG图谱”模式</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="h-12 border-t flex items-center justify-center flex-shrink-0 bg-muted/20">
        <div className="text-center text-sm text-muted-foreground">
          AI 驱动的文本转 Mermaid 图表 Web 应用 &copy; {new Date().getFullYear()}
        </div>
      </footer>

      <SettingsDialog
        open={showSettingsDialog}
        onOpenChange={setShowSettingsDialog}
        onPasswordVerified={handlePasswordVerified}
        onConfigUpdated={handleConfigUpdated}
      />
    </div>
  );
}