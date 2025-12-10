"use client";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { FileCode2, Github, Settings } from "lucide-react";

export function Header({ 
  onSettingsClick, 
  isPasswordVerified = false,
  hasCustomConfig = false 
}) {
  // 仅保留状态标记（可选），移除了具体的数字统计
  const hasUnlimitedAccess = isPasswordVerified || hasCustomConfig;

  return (
    <header className="border-b">
      <div className="flex h-16 items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-2">
          <FileCode2 className="h-6 w-6" />
          <span className="text-lg font-bold">Smart Mermaid</span>
          <span className="text-sm font-bold">简化您的图表创作</span>

        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            {/* 如果需要显示"已解锁"状态可以保留，不需要可直接删除此代码块 */}
            {hasUnlimitedAccess && (
              <span className="text-green-600 font-semibold">无限量</span>
            )}
          </div>
          
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={onSettingsClick}
            title="设置"
          >
            <Settings className="h-5 w-5" />
          </Button>
          
          {/* 请修改下方的 href 为您自己的 GitHub 仓库地址 */}
          <a 
            href="https://github.com/dengdengsm/gga_new.git"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:opacity-80"
          >
            <Github className="h-5 w-5" />
          </a>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}