"use client";

import { useEffect, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Trash2, Clock, ChevronRight, Loader2 } from "lucide-react";
import { getHistory, deleteHistoryEntry, clearHistory } from "@/lib/history-service";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export function HistoryList({ onSelect, className }) {
  const [history, setHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  // 初始化加载
  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setIsLoading(true);
    const data = await getHistory();
    setHistory(data);
    setIsLoading(false);
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    const success = await deleteHistoryEntry(id);
    if (success) {
      setHistory((prev) => prev.filter((item) => item.id !== id));
      toast.success("记录已删除");
    } else {
      toast.error("删除失败");
    }
  };

  const handleClearAll = async () => {
    const success = await clearHistory();
    if (success) {
      setHistory([]);
      toast.success("历史记录已清空");
    } else {
      toast.error("清空失败");
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        加载历史记录...
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4 text-center">
        <Clock className="h-12 w-12 mb-2 opacity-20" />
        <p>暂无历史记录</p>
        <p className="text-xs opacity-60 mt-1">生成的图表将保存在当前项目中</p>
      </div>
    );
  }

  return (
    <div className={`flex flex-col h-full ${className}`}>
      <div className="flex items-center justify-between p-4 border-b">
        <h3 className="font-semibold flex items-center gap-2">
          <Clock className="h-4 w-4" />
          历史记录 ({history.length})
        </h3>
        
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 text-muted-foreground hover:text-destructive">
              清空
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>确认清空历史记录？</AlertDialogTitle>
              <AlertDialogDescription>
                此操作将永久删除当前项目下的所有生成记录，无法撤销。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction onClick={handleClearAll} className="bg-destructive hover:bg-destructive/90">
                确认清空
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <ScrollArea className="flex-1">
        <div className="divide-y">
          {history.map((item) => (
            <div
              key={item.id}
              onClick={() => onSelect(item)}
              className="group flex items-start gap-3 p-4 hover:bg-muted/50 cursor-pointer transition-colors relative"
            >
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                    {item.diagramType || "auto"}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {item.timestamp 
                      ? formatDistanceToNow(new Date(item.timestamp), { addSuffix: true, locale: zhCN })
                      : "未知时间"}
                  </span>
                </div>
                <p className="text-sm font-medium leading-tight line-clamp-2 text-foreground/90">
                  {item.query}
                </p>
                <p className="text-xs text-muted-foreground font-mono truncate opacity-60">
                  {item.code.slice(0, 50).replace(/\n/g, ' ')}...
                </p>
              </div>

              <div className="flex flex-col items-end justify-between self-stretch pl-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                  onClick={(e) => handleDelete(e, item.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
                <ChevronRight className="h-4 w-4 text-muted-foreground/30" />
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}