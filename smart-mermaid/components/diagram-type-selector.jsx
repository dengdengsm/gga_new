"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// 完整的 Mermaid 图表类型列表及其简述
const DIAGRAM_TYPES = [
  { 
    value: "auto", 
    label: "自动选择 (Auto)", 
    description: "让 AI 根据你的描述自动分析并决定最合适的图表类型。" 
  },
  { 
    value: "flowchart", 
    label: "流程图 (Flowchart)", 
    description: "最常用的图表，用于展示步骤、决策过程或工作流。" 
  },
  { 
    value: "graphviz", 
    label: "Graphviz (DOT)", 
    description: "使用 DOT 语言绘制的通用图表，支持复杂的层级布局和精细的节点控制。" 
  },
  { 
    value: "sequenceDiagram", 
    label: "时序图 (Sequence)", 
    description: "展示对象之间交互的顺序，常用于系统设计和API调用分析。" 
  },
  { 
    value: "classDiagram", 
    label: "类图 (Class)", 
    description: "描述系统的静态结构，包括类、属性、方法及其关系。" 
  },
  { 
    value: "stateDiagram-v2", 
    label: "状态图 (State)", 
    description: "描述系统或对象在其生命周期内的状态变化过程。" 
  },
  { 
    value: "erDiagram", 
    label: "实体关系图 (ER)", 
    description: "展示实体及其之间的关系，常用于数据库结构设计。" 
  },
  { 
    value: "journey", 
    label: "用户旅程图 (Journey)", 
    description: "描述用户与产品交互的详细步骤和情绪体验。" 
  },
  { 
    value: "gantt", 
    label: "甘特图 (Gantt)", 
    description: "用于项目管理，展示项目进度、时间安排和依赖关系。" 
  },
  { 
    value: "pie", 
    label: "饼图 (Pie)", 
    description: "简单的统计图表，展示数据的比例分布。" 
  },
  { 
    value: "quadrantChart", 
    label: "象限图 (Quadrant)", 
    description: "将数据分为四个象限进行对比分析，如SWOT分析。" 
  },
  { 
    value: "requirementDiagram", 
    label: "需求图 (Requirement)", 
    description: "用于系统需求工程，展示需求及其相互关系。" 
  },
  { 
    value: "gitGraph", 
    label: "Git 提交图 (GitGraph)", 
    description: "模拟 Git 分支、合并和提交的历史记录。" 
  },
  { 
    value: "c4", 
    label: "C4 架构图 (C4)", 
    description: "用于描述软件架构的上下文、容器和组件视图。" 
  },
  { 
    value: "mindmap", 
    label: "思维导图 (Mindmap)", 
    description: "用于头脑风暴，层级化展示想法和结构。" 
  },
  { 
    value: "timeline", 
    label: "时间轴 (Timeline)", 
    description: "按时间顺序线性展示事件的发展。" 
  },
  { 
    value: "zenuml", 
    label: "ZenUML", 
    description: "使用伪代码风格绘制时序图，更贴近编程习惯。" 
  },
  { 
    value: "sankey-beta", 
    label: "桑基图 (Sankey)", 
    description: "展示流量分布和转移情况，如能量流或资金流。" 
  },
  { 
    value: "xychart-beta", 
    label: "XY 图表 (XY Chart)", 
    description: "展示二维数据关系，支持折线图和柱状图。" 
  },
  { 
    value: "block-beta", 
    label: "块图 (Block)", 
    description: "展示系统的高层级块结构，适用于硬件或架构设计。" 
  },
  { 
    value: "packet-beta", 
    label: "数据包图 (Packet)", 
    description: "展示网络数据包的结构和字段。" 
  },
  { 
    value: "kanban", 
    label: "看板 (Kanban)", 
    description: "用于项目管理，展示任务的状态流转。" 
  },
  { 
    value: "architecture", 
    label: "架构图 (Architecture)", 
    description: "展示云服务或系统架构图（实验性功能）。" 
  }
];

export function DiagramTypeSelector({ value, onChange }) {
  return (
    <div className="flex items-center justify-end w-full md:w-auto">
      {/* <Label htmlFor="diagram-type">图表类型</Label> */}
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id="diagram-type" className="w-full md:w-auto text-xs min-w-[140px]">
          <SelectValue placeholder="选择图表类型" />
        </SelectTrigger>
        <SelectContent>
          <TooltipProvider delayDuration={0}>
            {DIAGRAM_TYPES.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="w-full block text-left truncate">
                      {type.label}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="right" align="start" className="max-w-[260px] text-xs">
                    <p>{type.description}</p>
                  </TooltipContent>
                </Tooltip>
              </SelectItem>
            ))}
          </TooltipProvider>
        </SelectContent>
      </Select>
    </div>
  );
}