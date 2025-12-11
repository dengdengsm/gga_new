"use client";

import { useState, useEffect } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FileCode2, Github, Settings, FolderGit2, Plus } from "lucide-react";
import { getProjects, createProject, switchProject } from "@/lib/project-service";
import { toast } from "sonner";

export function Header({ 
  onSettingsClick, 
  isPasswordVerified = false,
  hasCustomConfig = false 
}) {
  const hasUnlimitedAccess = isPasswordVerified || hasCustomConfig;
  
  // --- 项目管理状态 ---
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState("default");
  const [isNewProjectOpen, setIsNewProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [loading, setLoading] = useState(false);

  // 初始化加载项目
  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      const data = await getProjects();
      const validProjects = data.projects || ["default"];
      setProjects(validProjects);

      // --- 核心修复：从本地缓存恢复上次选中的项目 ---
      // 解决刷新后“回到默认”或“前后端状态不一致”的问题
      const cachedProject = typeof window !== 'undefined' ? localStorage.getItem("lastActiveProject") : null;
      
      if (cachedProject && validProjects.includes(cachedProject)) {
        // 如果缓存的项目有效，UI 先显示它
        setCurrentProject(cachedProject);
        
        // 关键逻辑：如果后端当前的指针 (data.current) 和我们想要的不一致
        // (例如后端重启了变成了 default)，我们必须静默发送请求把后端纠正过来
        if (data.current !== cachedProject) {
           console.log(`[Auto-Sync] Restoring project context to: ${cachedProject}`);
           switchProject(cachedProject).catch(e => console.error("Auto-sync failed", e));
        }
      } else {
        // 没有缓存或缓存无效，听后端的
        setCurrentProject(data.current || "default");
      }
    } catch (e) {
      console.error("Failed to load projects", e);
    }
  };

  const handleProjectChange = async (value) => {
    if (value === "NEW_PROJECT_ACTION") {
      setIsNewProjectOpen(true);
      return;
    }

    if (value === currentProject) return;

    setLoading(true);
    const res = await switchProject(value);
    if (res.status === "success") {
      toast.success(`已切换至项目: ${value}`);
      
      // --- 核心修复：记录用户的选择 ---
      if (typeof window !== 'undefined') {
        localStorage.setItem("lastActiveProject", value);
      }

      // 强制刷新页面以重新加载该项目的历史记录和上下文
      window.location.reload();
    } else {
      toast.error(res.message || "切换失败");
      setLoading(false);
    }
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    
    // 简单的格式校验
    if (!/^[a-zA-Z0-9_-]+$/.test(newProjectName)) {
      toast.error("项目名只能包含英文、数字、下划线");
      return;
    }

    setLoading(true);
    const res = await createProject(newProjectName);
    if (res.status === "success") {
      toast.success("项目创建成功");
      setNewProjectName("");
      setIsNewProjectOpen(false);
      
      // --- 核心修复：新项目创建成功也记录缓存 ---
      if (typeof window !== 'undefined') {
        localStorage.setItem("lastActiveProject", newProjectName);
      }
      
      // 创建后切换逻辑
      await handleProjectChange(newProjectName);
    } else {
      toast.error(res.message || "创建失败");
      setLoading(false);
    }
  };

  return (
    <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-16 items-center justify-between px-4 md:px-6">
        
        {/* 左侧：Logo & Title */}
        <div className="flex items-center gap-2">
          <FileCode2 className="h-6 w-6 text-primary" />
          <div className="hidden md:flex flex-col leading-none">
            <span className="text-lg font-bold">Smart Mermaid</span>
            <span className="text-[10px] text-muted-foreground font-mono">PROJECT EDITION</span>
          </div>
        </div>

        {/* 中间：项目选择器 */}
        <div className="flex-1 flex justify-center max-w-xs mx-4">
          <Select 
            value={currentProject} 
            onValueChange={handleProjectChange} 
            disabled={loading}
          >
            <SelectTrigger className="w-full h-9 border-dashed border-primary/20 focus:ring-0">
              <div className="flex items-center gap-2 text-sm font-medium">
                <FolderGit2 className="h-4 w-4 text-muted-foreground" />
                <SelectValue placeholder="选择项目" />
              </div>
            </SelectTrigger>
            <SelectContent>
              {projects.map((p) => (
                <SelectItem key={p} value={p} className="cursor-pointer">
                  {p}
                </SelectItem>
              ))}
              <div className="h-px bg-border my-1" />
              <SelectItem value="NEW_PROJECT_ACTION" className="text-primary font-medium cursor-pointer">
                <div className="flex items-center gap-2">
                  <Plus className="h-4 w-4" /> 新建项目...
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* 右侧：功能按钮 */}
        <div className="flex items-center gap-2">
          <div className="hidden md:flex items-center gap-2 text-sm text-muted-foreground mr-2">
            {hasUnlimitedAccess && (
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium dark:bg-green-900/30 dark:text-green-400">
                PRO
              </span>
            )}
          </div>
          
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={onSettingsClick}
            title="AI设置"
          >
            <Settings className="h-5 w-5" />
          </Button>
          
          <a 
            href="https://github.com/dengdengsm/gga_new.git"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-10 w-10"
          >
            <Github className="h-5 w-5" />
          </a>
          <ThemeToggle />
        </div>
      </div>

      {/* 新建项目弹窗 */}
      <Dialog open={isNewProjectOpen} onOpenChange={setIsNewProjectOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>创建新项目</DialogTitle>
            <DialogDescription>
              请输入项目名称（仅支持英文、数字、下划线）。新项目将拥有独立的知识库和历史记录。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Input
                id="name"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="my_new_project"
                className="col-span-4"
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsNewProjectOpen(false)}>取消</Button>
            <Button onClick={handleCreateProject} disabled={loading}>
              {loading ? "创建中..." : "创建并切换"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </header>
  );
}