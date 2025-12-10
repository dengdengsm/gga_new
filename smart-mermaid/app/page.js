"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Wand2, PanelLeftClose, PanelLeftOpen } from "lucide-react";
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
import { HistoryList } from "@/components/history-list";
import { getHistory, addHistoryEntry } from "@/lib/history-service";
import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from "@/components/ui/dialog";
import dynamic from "next/dynamic";

const ExcalidrawRenderer = dynamic(() => import("@/components/excalidraw-renderer"), { ssr: false });

export default function Home() {
  const [inputText, setInputText] = useState("");
  const [mermaidCode, setMermaidCode] = useState("");
  const [diagramType, setDiagramType] = useState("auto");
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  // 已移除 remainingUsage 和 showLimitDialog 状态
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showContactDialog, setShowContactDialog] = useState(false);
  const [passwordVerified, setPasswordVerified] = useState(false);
  const [hasCustomConfig, setHasCustomConfig] = useState(false);
  
  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);
  const [renderMode, setRenderMode] = useState("excalidraw"); 
  const [showRealtime, setShowRealtime] = useState(false);
  const [leftTab, setLeftTab] = useState("manual");
  const [historyEntries, setHistoryEntries] = useState([]);

  const [errorMessage, setErrorMessage] = useState(null);
  const [hasError, setHasError] = useState(false);
  
  const maxChars = parseInt(process.env.NEXT_PUBLIC_MAX_CHARS || "20000");

  useEffect(() => {
    // Check password verification status
    setPasswordVerified(isPasswordVerified());
    // Check custom AI config status
    setHasCustomConfig(hasCustomAIConfig());
    // Load history list
    setHistoryEntries(getHistory());
  }, []);

  const handleTextChange = (text) => {
    setInputText(text);
  };

  const handleFileTextExtracted = (text) => {
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

  const handleContactClick = () => {
    setShowContactDialog(true);
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
        } catch {}
      }, 0);
      return () => clearTimeout(t);
    }
  }, [renderMode]);

  const handleErrorChange = (error, hasErr) => {
    setErrorMessage(error);
    setHasError(hasErr);
  };

  const toggleLeftPanel = () => {
    setIsLeftPanelCollapsed(!isLeftPanelCollapsed);
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

    // 已移除 checkUsageLimit 检查逻辑

    setIsGenerating(true);
    setIsStreaming(showRealtime);
    setStreamingContent("");

    try {
      const { mermaidCode: generatedCode, error } = await generateMermaidFromText(
        inputText,
        diagramType,
        showRealtime ? handleStreamChunk : null
      );

      if (error) {
        toast.error(error);
        return;
      }

      if (!generatedCode) {
        toast.error("生成图表失败，请重试");
        return;
      }

      // 已移除 incrementUsage 逻辑

      setMermaidCode(generatedCode);
      try {
        addHistoryEntry({ inputText, mermaidCode: generatedCode, diagramType });
        setHistoryEntries(getHistory());
      } catch {}
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
    <div className="flex flex-col h-screen overflow-hidden">
      <Header 
        // 已移除 usageLimit 和 remainingUsage 属性
        onSettingsClick={handleSettingsClick}
        onContactClick={handleContactClick}
        isPasswordVerified={passwordVerified}
        hasCustomConfig={hasCustomConfig}
      />
      
      <main className="flex-1 overflow-hidden">
        <div className="h-full p-4 md:p-6">
          <div 
            className={`h-full grid gap-4 md:gap-6 transition-all duration-300 ${
              isLeftPanelCollapsed ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-3'
            }`}
          >
            {/* 左侧面板 */}
            <div className={`${
              isLeftPanelCollapsed ? 'hidden md:hidden' : 'col-span-1'
            } flex flex-col h-full overflow-hidden`}>
              
              <Tabs value={leftTab} onValueChange={setLeftTab} className="flex flex-col h-full">
                <div className="h-auto md:h-12 flex flex-col md:flex-row justify-between items-start md:items-center gap-2 flex-shrink-0 pb-2 md:pb-0">
                  <TabsList className="h-9 w-full md:w-auto">
                    <TabsTrigger value="manual" className="flex-1 md:flex-none">手动输入</TabsTrigger>
                    <TabsTrigger value="file" className="flex-1 md:flex-none">文件上传</TabsTrigger>
                    <TabsTrigger value="history" className="flex-1 md:flex-none">历史记录</TabsTrigger>
                  </TabsList>
                  <div className="flex items-center gap-2 w-full md:w-auto flex-wrap">
                    <ModelSelector onModelChange={handleModelChange} />
                    <div className="flex-1 md:flex-none min-w-0">
                      <DiagramTypeSelector 
                        value={diagramType} 
                        onChange={handleDiagramTypeChange} 
                      />
                    </div>
                  </div>
                </div>
                
                <div className="flex-1 flex flex-col overflow-hidden mt-2 md:mt-4">
                  <div className="h-28 md:h-40 flex-shrink-0">
                    <TabsContent value="manual" className="h-full mt-0">
                      <TextInput 
                        value={inputText} 
                        onChange={handleTextChange} 
                        maxChars={maxChars}
                      />
                    </TabsContent>
                    <TabsContent value="file" className="h-full mt-0">
                      <FileUpload onTextExtracted={handleFileTextExtracted} />
                    </TabsContent>
                    <TabsContent value="history" className="h-full mt-0">
                      <HistoryList
                        items={historyEntries}
                        onSelect={(item) => {
                          setInputText(item.inputText);
                          setMermaidCode(item.mermaidCode);
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
                          生成中...
                        </>
                      ) : (
                        <>
                          <Wand2 className="mr-2 h-4 w-4" />
                          生成图表
                        </>
                      )}
                    </Button>
                    <div className="flex items-center">
                      <Switch 
                        checked={showRealtime} 
                        onCheckedChange={setShowRealtime}
                        title="实时生成"
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
            <div className={`${
              isLeftPanelCollapsed ? 'col-span-1' : 'col-span-1 md:col-span-2'
            } flex flex-col h-full overflow-hidden`}>
              <div className="h-12 flex justify-between items-center flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={toggleLeftPanel}
                  className="h-9"
                >
                  {isLeftPanelCollapsed ? (
                    <>
                      <PanelLeftOpen className="h-4 w-4" />
                      <span className="hidden sm:inline ml-2">显示</span>
                    </>
                  ) : (
                    <>
                      <PanelLeftClose className="h-4 w-4" />
                      <span className="hidden sm:inline ml-2">隐藏</span>
                    </>
                  )}
                </Button>

                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={renderMode === "mermaid"}
                      onCheckedChange={(checked) => setRenderMode(checked ? "mermaid" : "excalidraw")}
                      title="切换渲染器：Excalidraw / Mermaid"
                    />
                    <span className="text-xs text-muted-foreground">
                      {renderMode === "mermaid" ? "Mermaid" : "Excalidraw"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex-1 min-h-0 mt-4" style={{ minHeight: '600px' }}>
                {renderMode === "excalidraw" ? (
                  <ExcalidrawRenderer
                    mermaidCode={mermaidCode}
                    onErrorChange={handleErrorChange}
                  />
                ) : (
                  <MermaidRenderer
                    mermaidCode={mermaidCode}
                    onChange={handleMermaidCodeChange}
                    onErrorChange={handleErrorChange}
                  />
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

      <Dialog open={showContactDialog} onOpenChange={setShowContactDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>联系作者</DialogTitle>
            <DialogDescription>
              <div className="py-4">
                <p className="mb-2">如需技术支持，请扫描下方二维码联系作者（注明目的）</p>
                <div className="flex justify-center my-4">
                  <img src="/qrcode.png" alt="联系二维码" className="w-48" />
                </div>
                <p className="text-sm text-muted-foreground">
                  提示：您也可以在设置中配置自己的AI服务密钥。
                </p>
              </div>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center">
            <Button variant="secondary" onClick={() => setShowContactDialog(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* 已移除 Usage Limit Dialog */}
    </div>
  );
}