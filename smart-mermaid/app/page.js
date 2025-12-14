"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Wand2, Network, FolderOpen, BrainCircuit, FileText, FileSearch } from "lucide-react"; // 引入图标
import { Header } from "@/components/header";
import { SettingsDialog } from "@/components/settings-dialog";
import { TextInput } from "@/components/text-input";
import { FileUpload } from "@/components/file-upload";
import { DiagramTypeSelector } from "@/components/diagram-type-selector";
import { ModelSelector } from "@/components/model-selector";
import { MermaidEditor } from "@/components/mermaid-editor";
import { MermaidRenderer } from "@/components/mermaid-renderer";
import { generateMermaidFromText } from "@/lib/ai-service";
import { isWithinCharLimit } from "@/lib/utils";
import { isPasswordVerified, hasCustomAIConfig } from "@/lib/config-service";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
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
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [passwordVerified, setPasswordVerified] = useState(false);
  const [hasCustomConfig, setHasCustomConfig] = useState(false);

  // 状态控制开关
  const [useGraph, setUseGraph] = useState(false); // 知识图谱模式
  const [useFileContext, setUseFileContext] = useState(true); // 【新增】是否依赖文件上下文

  const [renderMode, setRenderMode] = useState("mermaid");
  
  const [showRealtime, setShowRealtime] = useState(false);
  const [leftTab, setLeftTab] = useState("manual");
  const [historyEntries, setHistoryEntries] = useState([]);

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

  const handleTextChange = (text) => {
    setInputText(text);
  };

  const handleDiagramTypeChange = (type) => {
    setDiagramType(type);
  };

  const handleMermaidCodeChange = (code) => {
    setMermaidCode(code);
  };

  const handleStreamChunk = (chunk) => {
    setStreamingContent(prev => prev + chunk);
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
  // -----------------------

  const handleErrorChange = (error, hasErr) => {
    setErrorMessage(error);
    setHasError(hasErr);
  };

  const handleModelChange = useCallback((modelId) => {
    console.log('Selected model:', modelId);
  }, []);

  const handleGenerateClick = async () => {
    if (!inputText.trim()) {
      toast.error("请输入文本内容");
      return;
    }

    if (!isWithinCharLimit(inputText, maxChars)) {
      toast.error(`文本超过${maxChars}字符限制`);
      return;
    }

    setIsGenerating(true);
    setIsStreaming(showRealtime);
    setStreamingContent("");

    try {
      // 【修改】传入 useGraph 和 useFileContext
      const { mermaidCode: generatedCode, error } = await generateMermaidFromText(
        inputText,
        diagramType,
        showRealtime ? handleStreamChunk : null,
        useGraph,
        useFileContext // 【新增】
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
      try {
        addHistoryEntry({
          query: inputText,
          code: generatedCode,
          diagramType
        });
        setTimeout(async () => {
          setHistoryEntries(await getHistory());
        }, 100);
      } catch (e) {
        console.error("Failed to save history:", e);
      }
      toast.success("图表生成成功");
    } catch (error) {
      console.error("Generation error:", error);
      toast.error("生成图表时发生错误");
    } finally {
      setIsGenerating(false);
      setIsStreaming(false);
    }
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
                <div className="flex flex-col gap-2 pb-2">
                  {/* 第一行：Tabs 和 全局开关 */}
                  <div className="flex justify-between items-start flex-wrap gap-2">
                    <TabsList className="h-9">
                      <TabsTrigger value="manual">手动输入</TabsTrigger>
                      <TabsTrigger value="file">文件上传</TabsTrigger>
                      <TabsTrigger value="history">历史记录</TabsTrigger>
                    </TabsList>
                  </div>

                  {/* 第二行：生成配置开关组 */}
                  <div className="flex flex-wrap gap-2 py-1">
                    {/* 文件依赖开关 */}
                    <div className="flex items-center space-x-2 bg-muted/50 px-3 py-1.5 rounded-md border flex-1 min-w-[140px] justify-between">
                        <div className="flex items-center gap-2">
                           <FileSearch className="h-4 w-4 text-muted-foreground" />
                           <Label htmlFor="file-ctx-mode" className="text-xs font-medium cursor-pointer">
                               依赖文件
                           </Label>
                        </div>
                        <Switch id="file-ctx-mode" checked={useFileContext} onCheckedChange={setUseFileContext} className="scale-75" />
                    </div>

                    {/* 知识图谱开关 (只有开启依赖文件时才有效) */}
                    <div className={`flex items-center space-x-2 bg-muted/50 px-3 py-1.5 rounded-md border flex-1 min-w-[140px] justify-between transition-opacity ${!useFileContext ? 'opacity-50 pointer-events-none' : ''}`}>
                        <div className="flex items-center gap-2">
                           {useGraph ? <BrainCircuit className="h-4 w-4 text-primary" /> : <FileText className="h-4 w-4 text-muted-foreground" />}
                           <Label htmlFor="graph-mode" className="text-xs font-medium cursor-pointer">
                               {useGraph ? "RAG图谱" : "文档直读"}
                           </Label>
                        </div>
                        <Switch id="graph-mode" checked={useGraph} onCheckedChange={setUseGraph} className="scale-75" />
                    </div>
                  </div>

                  {/* 第三行：Model & Type Selectors */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <ModelSelector onModelChange={handleModelChange} />
                    <div className="flex-1 min-w-0">
                      <DiagramTypeSelector
                        value={diagramType}
                        onChange={handleDiagramTypeChange}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex-1 flex flex-col overflow-hidden mt-1">
                  <div className="h-28 md:h-40 flex-shrink-0">
                    <TabsContent value="manual" className="h-full mt-0">
                      <TextInput
                        value={inputText}
                        onChange={handleTextChange}
                        maxChars={maxChars}
                      />
                    </TabsContent>
                    <TabsContent value="file" className="h-full mt-0">
                      {/* 传入 autoBuild 参数 */}
                      <FileUpload autoBuild={useGraph} />
                    </TabsContent>
                    <TabsContent value="history" className="h-full mt-0">
                      <HistoryList
                        items={historyEntries}
                        onSelect={(item) => {
                          setInputText(item.query || item.inputText || "");
                          setMermaidCode(item.code || item.mermaidCode || "");
                          setLeftTab("manual");
                        }}
                      />
                    </TabsContent>
                  </div>

                  <div className="h-16 flex items-center gap-2 flex-shrink-0">
                    <Button
                      onClick={handleGenerateClick}
                      disabled={isGenerating || !inputText.trim() || !isWithinCharLimit(inputText, maxChars)}
                      className="h-10 flex-1"
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
                    <div className="flex items-center gap-2 px-2 bg-muted/30 rounded border h-10">
                       <span className="text-xs text-muted-foreground whitespace-nowrap">流式</span>
                       <Switch
                        checked={showRealtime}
                        onCheckedChange={setShowRealtime}
                        className="scale-75"
                       />
                    </div>
                  </div>

                  <div className="flex-1 min-h-0">
                    <MermaidEditor
                      code={mermaidCode}
                      onChange={handleMermaidCodeChange}
                      streamingContent={streamingContent}
                      isStreaming={isStreaming}
                      errorMessage={errorMessage}
                      hasError={hasError}
                      onStreamChunk={handleStreamChunk}
                      showRealtime={showRealtime}
                    />
                  </div>
                </div>
              </Tabs>
            </div>

            {/* 右侧面板 */}
            <div className="col-span-1 md:col-span-2 flex flex-col h-full">
              {/* Header */}
              <div className="h-12 flex justify-between items-center flex-shrink-0">
                <div className="flex items-center gap-2 bg-muted p-1 rounded-lg">
                   <Button 
                      variant={renderMode === "mermaid" ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setRenderMode("mermaid")}
                      className="h-8 text-xs px-3"
                   >
                     Mermaid
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
                      disabled={!useGraph || !useFileContext} // 如果关闭了图谱模式或不依赖文件，禁用图谱视图
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

              <div className="flex-1 mt-4 overflow-y-auto min-h-[600px] border rounded-lg bg-background">
                {renderMode === "mermaid" && (
                  <MermaidRenderer
                    mermaidCode={mermaidCode}
                    onChange={handleMermaidCodeChange}
                    onErrorChange={handleErrorChange}
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

      <footer className="h-12 border-t flex items-center justify-center flex-shrink-0">
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