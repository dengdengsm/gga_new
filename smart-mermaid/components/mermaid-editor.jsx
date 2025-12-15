"use client";

import { useState, useRef, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { 
  Copy, Check, Wand2, ArrowLeftRight, 
  History, Star, X, Trash2 
} from "lucide-react";
import { copyToClipboard } from "@/lib/utils";
import { autoFixMermaidCode, toggleMermaidDirection } from "@/lib/mermaid-fixer";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { optimizeMermaidCode } from "@/lib/ai-service";
import { addHistoryEntry } from "@/lib/history-service"; // 【新增】引入历史记录服务
import { 
  getSuggestionHistory, 
  addSuggestionToHistory, 
  addGlobalRule, 
  getGlobalRules,
  removeSuggestionFromHistory,
  removeGlobalRule,
  clearSuggestionHistory,
  clearGlobalRules
} from "@/lib/preference-service";

export function MermaidEditor({ 
  code, 
  onChange, 
  errorMessage, 
  hasError,
  onHistoryChange // 【新增】接收刷新回调
}) {
  const [copied, setCopied] = useState(false);
  const [isFixing, setIsFixing] = useState(false);
  const [showOptimize, setShowOptimize] = useState(false);
  const [optTab, setOptTab] = useState("suggestions");
  
  const [displaySuggestions, setDisplaySuggestions] = useState([]);
  const [activeGlobalRules, setActiveGlobalRules] = useState([]);
  
  const [optInstruction, setOptInstruction] = useState("");
  const [isOptimizing, setIsOptimizing] = useState(false);
  
  const [rememberGlobal, setRememberGlobal] = useState(false);

  const handleChange = (e) => {
    onChange(e.target.value);
  };

  const handleCopy = async () => {
    const success = await copyToClipboard(code);

    if (success) {
      setCopied(true);
      toast.success("已复制到剪贴板");

      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } else {
      toast.error("复制失败");
    }
  };

  const handleAutoFix = async () => {
    if (!code) {
      toast.error("没有代码可以修复");
      return;
    }

    setIsFixing(true);

    try {
      const result = await autoFixMermaidCode(code, errorMessage, null);

      if (result.error) {
        toast.error(result.error);
        if (result.fixedCode !== code) {
          onChange(result.fixedCode);
          toast.info("已应用基础修复");
        }
      } else {
        if (result.fixedCode !== code) {
          onChange(result.fixedCode);
          toast.success("AI修复完成");
        } else {
          toast.info("代码看起来没有问题");
        }
      }
    } catch (error) {
      console.error("修复失败:", error);
      toast.error("修复失败，请稍后重试");
    } finally {
      setIsFixing(false);
    }
  };

  const handleToggleDirection = () => {
    if (!code) {
      toast.error("没有代码可以切换方向");
      return;
    }

    const toggledCode = toggleMermaidDirection(code);
    if (toggledCode !== code) {
      onChange(toggledCode);
      toast.success("图表方向已切换");
    } else {
      toast.info("未检测到可切换的方向");
    }
  };

  const loadSuggestions = () => {
    const history = getSuggestionHistory();
    const globals = getGlobalRules(); 
    
    const merged = Array.from(new Set([...globals, ...history]));
    
    setDisplaySuggestions(merged);
    setActiveGlobalRules(globals);
  };

  useEffect(() => {
    if (showOptimize && optTab === 'suggestions') {
      loadSuggestions();
    }
  }, [showOptimize, optTab]);

  const handleDeleteSuggestion = (e, text) => {
    e.stopPropagation();
    removeSuggestionFromHistory(text);
    removeGlobalRule(text);
    loadSuggestions(); 
    toast.success("建议已删除");
  };

  const handleClearAll = () => {
    if (!confirm("确定要清空所有历史建议和全局规则吗？此操作无法撤销。")) {
      return;
    }
    clearSuggestionHistory();
    clearGlobalRules();
    loadSuggestions();
    toast.success("所有记录已清空");
  };

  const doOptimize = async (instructionText) => {
    if (!code) {
      toast.error("没有代码可以优化");
      return;
    }
    if (!instructionText || !instructionText.trim()) {
      toast.error("请输入优化需求");
      return;
    }

    const trimmedInstruction = instructionText.trim();
    setIsOptimizing(true);

    try {
      addSuggestionToHistory(trimmedInstruction);

      if (rememberGlobal && optTab === 'custom') {
        addGlobalRule(trimmedInstruction);
        toast.info("已添加到全局偏好");
        setRememberGlobal(false);
      }
      
      if (optTab === 'suggestions') loadSuggestions();

      const globalRules = getGlobalRules();
      
      let finalInstruction = trimmedInstruction;
      if (globalRules.length > 0) {
        finalInstruction = `[Current Request]: ${trimmedInstruction}\n\n[User Global Preferences]:\n- ${globalRules.join('\n- ')}`;
      }

      const { optimizedCode, error } = await optimizeMermaidCode(code, finalInstruction, null);
      
      if (error) {
        toast.error(error);
        return;
      }

      if (!optimizedCode) {
        toast.error("优化失败，请重试");
        return;
      }

      onChange(optimizedCode);
      toast.success("优化完成");

      // 【新增】保存优化结果到历史记录
      try {
        addHistoryEntry({
          query: `[优化] ${trimmedInstruction}`, // 加个前缀区分
          code: optimizedCode,
          diagramType: 'optimization' // 标记为优化类型
        });
        // 刷新列表
        if (onHistoryChange) {
            onHistoryChange();
        }
      } catch (e) {
        console.error("Failed to save optimization history:", e);
      }
      
      if (optTab === 'custom') {
        setOptInstruction("");
      }

    } catch (e) {
      console.error(e);
      toast.error("优化失败，请稍后重试");
    } finally {
      setIsOptimizing(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 编辑器标题栏 */}
      <div className="flex justify-between items-center h-8 mb-2">
        <h3 className="text-sm font-medium">Mermaid 代码</h3>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowOptimize(v => !v)}
            disabled={!code}
            className="h-7 gap-1 text-xs"
            title="继续优化"
          >
            继续优化
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleAutoFix}
            disabled={!code || isFixing || !hasError}
            className="h-7 gap-1 text-xs"
            title={hasError ? "使用AI智能修复代码问题" : "当前代码没有错误，无需修复"}
          >
            {isFixing ? (
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-current"></div>
            ) : (
              <Wand2 className="h-3 w-3" />
            )}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleToggleDirection}
            disabled={!code}
            className="h-7 gap-1 text-xs"
            title="切换图表方向 (横向/纵向)"
          >
            <ArrowLeftRight className="h-3 w-3" />
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            disabled={!code}
            className="h-7 gap-1 text-xs"
          title={copied ? "已复制" : "复制代码"}
          >
            {copied ? (
              <Check className="h-3 w-3" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
          </Button>
        </div>
      </div>

      {/* 代码编辑器容器 */}
      <div className="flex-1 min-h-0">
        <Textarea
          value={code}
          onChange={handleChange}
          placeholder="生成的 Mermaid 代码将显示在这里..."
          className="w-full h-full font-mono text-sm mermaid-editor overflow-y-auto resize-none"
          disabled={isFixing || isOptimizing}
          spellCheck={false}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
        />
      </div>

      {/* 继续优化面板 */}
      {showOptimize && (
        <div className="mt-2 border rounded-md p-2 h-48 flex flex-col bg-muted/10">
          <Tabs value={optTab} onValueChange={setOptTab} className="flex flex-col h-full">
            <div className="flex items-center justify-between mb-2">
              <TabsList className="h-7">
                <TabsTrigger value="suggestions" className="text-xs gap-1">
                  <History className="h-3 w-3" /> 历史建议
                </TabsTrigger>
                <TabsTrigger value="custom" className="text-xs">自定义输入</TabsTrigger>
              </TabsList>
              
              <div className="flex items-center gap-2">
                <div className="text-xs text-muted-foreground">
                  {isOptimizing ? "正在优化…" : null}
                </div>
                {/* 清空按钮 (只在建议Tab显示) */}
                {optTab === 'suggestions' && displaySuggestions.length > 0 && (
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-6 w-6 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                    onClick={handleClearAll}
                    title="清空所有历史建议和全局规则"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>

            <TabsContent value="suggestions" className="flex-1 overflow-auto mt-0">
              {displaySuggestions.length > 0 ? (
                <div className="flex flex-col gap-2"> 
                  <div className="flex flex-wrap gap-2">
                    {displaySuggestions.map((s, idx) => {
                      const isGlobal = activeGlobalRules.includes(s);
                      
                      return (
                        <div 
                          key={idx} 
                          className={`group flex items-stretch rounded-md overflow-hidden border transition-all max-w-full
                            ${isGlobal ? 'bg-amber-100 border-amber-300 dark:bg-amber-900/30 dark:border-amber-700' : 'bg-secondary border-transparent hover:border-input'}
                          `}
                        >
                          {/* 左侧：应用建议按钮 */}
                          <Button 
                            variant="ghost" 
                            size="sm" 
                            className={`h-auto py-2 px-3 text-xs whitespace-normal text-left break-words max-w-full justify-start rounded-none flex-1
                              ${isGlobal ? 'text-amber-900 dark:text-amber-100 hover:bg-amber-200 dark:hover:bg-amber-900/50' : ''}
                            `}
                            disabled={isOptimizing}
                            onClick={() => doOptimize(s)}
                            title={isGlobal ? "这是一条全局规则，每次生成都会自动应用" : "点击应用此建议"}
                          >
                            {isGlobal && <Star className="h-3 w-3 mr-1.5 text-amber-500 fill-amber-500 flex-shrink-0 inline" />}
                            {s}
                          </Button>
                          
                          {/* 右侧：删除按钮 */}
                          <div className={`border-l ${isGlobal ? 'border-amber-300 dark:border-amber-700' : 'border-white/10 dark:border-black/10'}`}></div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className={`h-full px-2 rounded-none transition-colors
                              ${isGlobal 
                                ? 'text-amber-700 hover:text-red-600 hover:bg-red-100 dark:text-amber-400 dark:hover:bg-red-900/30' 
                                : 'text-muted-foreground hover:text-destructive hover:bg-destructive/10'}
                            `}
                            onClick={(e) => handleDeleteSuggestion(e, s)}
                            disabled={isOptimizing}
                            title="删除此建议"
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                  暂无历史优化建议
                </div>
              )}
            </TabsContent>

            <TabsContent value="custom" className="flex-1 mt-0 flex flex-col min-h-0">
              <Textarea
                value={optInstruction}
                onChange={(e) => setOptInstruction(e.target.value)}
                placeholder="输入你的优化需求，例如：将方向改为LR，并用subgraph分组模块。"
                className="flex-1 text-sm resize-none mb-2"
                disabled={isOptimizing}
              />
              <div className="flex justify-between items-center">
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="remember-global"
                    checked={rememberGlobal}
                    onChange={(e) => setRememberGlobal(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                    disabled={isOptimizing}
                  />
                  <Label 
                    htmlFor="remember-global" 
                    className="text-xs cursor-pointer flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <Star className="h-3 w-3" />
                    记住并应用到所有生成
                  </Label>
                </div>
                <Button size="sm" onClick={() => doOptimize(optInstruction)} disabled={!optInstruction.trim() || isOptimizing} className="h-7">
                  应用优化
                </Button>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}