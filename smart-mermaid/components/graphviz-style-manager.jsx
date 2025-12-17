"use client";

import { useState, useEffect } from "react";
import { Paintbrush, Plus, Loader2, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { generateGraphStyle } from "@/lib/ai-service";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SelectSeparator,
  SelectGroup,
  SelectLabel
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// --- 预设风格定义 ---
const PRESETS = [
  {
    id: "default",
    name: "默认风格 (Default)",
    css: "",
    svgDefs: "" 
  },
  {
    id: "hand-drawn",
    name: "手绘草图 (Hand Drawn)",
    css: `
      svg { font-family: "Comic Sans MS", "Chalkboard SE", sans-serif !important; }
      .node polygon, .node ellipse, .node path { 
        stroke-width: 2px !important; 
        fill: #fff !important; 
        stroke: #333 !important; 
        filter: url(#hand-drawn-filter); 
      }
      .edge path { 
        stroke: #333 !important; 
        stroke-width: 2px !important; 
        filter: url(#hand-drawn-filter); 
      }
      .edge polygon { 
        fill: #333 !important; 
        stroke: #333 !important; 
        filter: url(#hand-drawn-filter); 
      }
      text { font-weight: bold; fill: #333 !important; }
    `,
    svgDefs: `
      <filter id="hand-drawn-filter" x="-20%" y="-20%" width="140%" height="140%">
        <feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="3" result="noise" />
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="2.5" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    `
  },
  {
    id: "blueprint",
    name: "工程蓝图 (Blueprint)",
    css: `
      svg { background-color: #1a365d !important; font-family: "Courier New", monospace !important; }
      .node polygon, .node ellipse { 
        fill: #1a365d !important; 
        stroke: #fff !important; 
        stroke-dasharray: 5,2; 
        stroke-width: 1.5px !important; 
      }
      .edge path { stroke: #93c5fd !important; stroke-width: 1.5px !important; }
      .edge polygon { fill: #93c5fd !important; stroke: #93c5fd !important; }
      text { fill: #fff !important; }
    `,
    svgDefs: ""
  },
  {
    id: "neon",
    name: "赛博霓虹 (Cyberpunk)",
    css: `
      svg { background-color: #050505 !important; font-family: "Orbitron", sans-serif !important; }
      .node polygon, .node ellipse { 
        fill: rgba(0, 255, 255, 0.1) !important; 
        stroke: #0ff !important; 
        stroke-width: 2px !important; 
        filter: url(#neon-glow); 
      }
      .edge path { stroke: #f0f !important; stroke-width: 2px !important; filter: url(#neon-glow); }
      .edge polygon { fill: #f0f !important; stroke: #f0f !important; }
      text { fill: #fff !important; text-shadow: 0 0 5px #0ff; }
    `,
    svgDefs: `
      <filter id="neon-glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.5" result="coloredBlur" />
        <feMerge>
          <feMergeNode in="coloredBlur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    `
  }
];

export function GraphvizStyleManager({ onStyleChange }) {
  const [activeStyleId, setActiveStyleId] = useState("default");
  const [customStyles, setCustomStyles] = useState([]);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  // 初始化：加载本地保存的样式
  useEffect(() => {
    const saved = localStorage.getItem("graphviz-custom-styles");
    if (saved) {
      try {
        setCustomStyles(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load custom styles", e);
      }
    }
  }, []);

  // 这里的 effect 负责在样式切换时通知父组件
  useEffect(() => {
    const allStyles = [...PRESETS, ...customStyles];
    const selected = allStyles.find(s => s.id === activeStyleId) || PRESETS[0];
    if (onStyleChange) {
      onStyleChange(selected);
    }
  }, [activeStyleId, customStyles, onStyleChange]);

  const handleGenerate = async () => {
    if (!prompt.trim()) return;

    setIsGenerating(true);
    try {
      const result = await generateGraphStyle(prompt);
      
      if (result.error) {
        toast.error(result.error);
        return;
      }

      const newStyle = {
        id: `custom-${Date.now()}`,
        name: prompt.slice(0, 15) + (prompt.length > 15 ? "..." : ""), // 简单的名字
        css: result.css,
        svgDefs: result.svgDefs
      };

      const updatedStyles = [newStyle, ...customStyles];
      setCustomStyles(updatedStyles);
      localStorage.setItem("graphviz-custom-styles", JSON.stringify(updatedStyles));
      
      setActiveStyleId(newStyle.id);
      setIsDialogOpen(false);
      setPrompt("");
      toast.success("新风格已生成并应用！");

    } catch (e) {
      toast.error("生成失败，请重试");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDelete = (e, id) => {
    e.stopPropagation();
    const updated = customStyles.filter(s => s.id !== id);
    setCustomStyles(updated);
    localStorage.setItem("graphviz-custom-styles", JSON.stringify(updated));
    if (activeStyleId === id) setActiveStyleId("default");
    toast.success("样式已删除");
  };

  return (
    <>
      <div className="flex items-center">
        <Paintbrush className="h-4 w-4 text-muted-foreground mr-2" />
        <Select value={activeStyleId} onValueChange={(val) => {
            if (val === "create_new") {
                setIsDialogOpen(true);
            } else {
                setActiveStyleId(val);
            }
        }}>
          <SelectTrigger className="h-8 w-[140px] text-xs">
            <SelectValue placeholder="选择风格" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
                <SelectLabel className="text-xs text-muted-foreground">预设风格</SelectLabel>
                {PRESETS.map(style => (
                <SelectItem key={style.id} value={style.id} className="text-xs">
                    {style.name}
                </SelectItem>
                ))}
            </SelectGroup>
            
            {customStyles.length > 0 && (
                <>
                    <SelectSeparator />
                    <SelectGroup>
                        <SelectLabel className="text-xs text-muted-foreground">我的风格</SelectLabel>
                        {customStyles.map(style => (
                            <div key={style.id} className="relative flex items-center pr-2 group">
                                <SelectItem value={style.id} className="text-xs flex-1 pr-8 truncate">
                                    ✨ {style.name}
                                </SelectItem>
                                <button 
                                    onClick={(e) => handleDelete(e, style.id)}
                                    className="absolute right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-destructive/10 rounded-sm text-muted-foreground hover:text-destructive"
                                >
                                    <Trash2 className="h-3 w-3" />
                                </button>
                            </div>
                        ))}
                    </SelectGroup>
                </>
            )}

            <SelectSeparator />
            <SelectItem value="create_new" className="text-xs font-medium text-primary focus:text-primary cursor-pointer">
                <div className="flex items-center gap-2">
                    <Plus className="h-3.5 w-3.5" />
                    <span>AI 生成新风格...</span>
                </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
                <Wand2 className="h-5 w-5 text-primary" />
                AI 风格生成器
            </DialogTitle>
            <DialogDescription>
              描述你想要的图表视觉风格，AI 将为你编写 CSS 和 SVG 滤镜代码。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="prompt" className="text-sm">风格描述</Label>
              <Input
                id="prompt"
                placeholder="例如：哈利波特羊皮纸风格、黑客帝国数字雨..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
                disabled={isGenerating}
              />
            </div>
            <div className="text-xs text-muted-foreground bg-muted p-3 rounded-md">
                💡 提示：你可以描述颜色、线条质感（如粉笔、墨水）、发光效果或特定主题。
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDialogOpen(false)} disabled={isGenerating}>取消</Button>
            <Button onClick={handleGenerate} disabled={isGenerating || !prompt.trim()}>
              {isGenerating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    生成中...
                  </>
              ) : (
                  "开始生成"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}