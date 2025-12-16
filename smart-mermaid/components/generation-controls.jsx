"use client"

import React from 'react'
import { Settings2, FileSearch, BrainCircuit, History, ShieldAlert } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Slider } from "@/components/ui/react-slider"
import { cn } from "@/lib/utils"

export function GenerationControls({
  useFileContext,
  setUseFileContext,
  useGraph,
  setUseGraph,
  // 2. 接收新参数
  useHistory,
  setUseHistory,
  useMistakes,
  setUseMistakes,
  richness,
  setRichness
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button 
          variant="outline" 
          size="icon" 
          className="h-9 w-9 flex-shrink-0 border-dashed border-muted-foreground/30 hover:border-primary hover:bg-primary/5"
          title="生成策略设置"
        >
          <Settings2 className="h-4 w-4 text-muted-foreground transition-colors hover:text-primary" />
        </Button>
      </PopoverTrigger>
      
      <PopoverContent className="w-80 p-4" align="end" sideOffset={5}>
        <div className="space-y-4">
          <div className="space-y-2">
            <h4 className="font-medium leading-none text-sm flex items-center gap-2">
              <Settings2 className="h-3.5 w-3.5 text-primary" />
              生成策略配置
            </h4>
            <p className="text-xs text-muted-foreground">
              调整 AI 读取上下文的方式与生成细节。
            </p>
          </div>
          
          <div className="h-px bg-border" />

          {/* 开关组 */}
          <div className="space-y-3">
            {/* 依赖文件 */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileSearch className="h-3.5 w-3.5 text-muted-foreground" />
                <Label htmlFor="file-ctx-pop" className="text-xs font-medium cursor-pointer">
                  依赖文件上下文
                </Label>
              </div>
              <Switch 
                id="file-ctx-pop" 
                checked={useFileContext} 
                onCheckedChange={setUseFileContext} 
                className="scale-75 origin-right" 
              />
            </div>

            {/* 知识图谱 */}
            <div className={cn(
                "flex items-center justify-between transition-opacity duration-200",
                !useFileContext && "opacity-50 pointer-events-none"
              )}>
              <div className="flex items-center gap-2">
                <BrainCircuit className={cn("h-3.5 w-3.5", useGraph ? "text-indigo-500" : "text-muted-foreground")} />
                <Label htmlFor="graph-mode-pop" className="text-xs font-medium cursor-pointer">
                  {useGraph ? "RAG 知识图谱" : "普通文档直读"}
                </Label>
              </div>
              <Switch 
                id="graph-mode-pop" 
                checked={useGraph} 
                onCheckedChange={setUseGraph} 
                className="scale-75 origin-right data-[state=checked]:bg-indigo-500" 
              />
            </div>

            {/* 3. 新增：历史经验 (Router) */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="h-3.5 w-3.5 text-muted-foreground" />
                <Label htmlFor="history-mode-pop" className="text-xs font-medium cursor-pointer">
                  参考历史经验 (Router)
                </Label>
              </div>
              <Switch 
                id="history-mode-pop" 
                checked={useHistory} 
                onCheckedChange={setUseHistory} 
                className="scale-75 origin-right" 
              />
            </div>

            {/* 4. 新增：错题修正 (Code Revise) */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-3.5 w-3.5 text-muted-foreground" />
                <Label htmlFor="mistakes-mode-pop" className="text-xs font-medium cursor-pointer">
                  启用错题修正 (Revise)
                </Label>
              </div>
              <Switch 
                id="mistakes-mode-pop" 
                checked={useMistakes} 
                onCheckedChange={setUseMistakes} 
                className="scale-75 origin-right" 
              />
            </div>

          </div>

          <div className="h-px bg-border" />

          {/* 丰富度滑块 (保持不变) */}
          <div className="space-y-3 pt-1">
            <div className="flex items-center justify-between">
              <Label className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                Richness (信息密度)
              </Label>
              <span className="text-[10px] font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                {richness}
              </span>
            </div>
            
            <Slider 
              value={[richness]} 
              max={1} 
              step={0.1} 
              onValueChange={(vals) => setRichness(vals[0])}
              className="w-full"
            />
            
            <div className="flex justify-between text-[9px] text-muted-foreground/60 px-0.5 font-medium">
              <span>Summarize</span>
              <span>Detailed</span>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}