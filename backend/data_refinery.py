import os
import glob
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm # 建议安装: pip install tqdm，如果没有安装，脚本会自动降级处理

# --- 引用你的 Agent ---
# 假设 Agent.py 在同级目录
from Agent import deepseek_agent

# ================= 配置区 =================
RAW_DATA_DIR = "./knowledge/mermaid_code"
EXPERIENCE_DB = "./knowledge/experience/router.json"
MODEL_NAME = "deepseek-chat" # 使用 Chat 模型即可，成本低速度快

# 过滤阈值
MIN_LINES = 5
MAX_LINES = 100
# ==========================================

class DataRefinery:
    def __init__(self):
        print(f"--- 初始化 DataRefinery [模型: {MODEL_NAME}] ---")
        self.llm = deepseek_agent(model_name=MODEL_NAME)
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(EXPERIENCE_DB), exist_ok=True)
        
        # 加载现有经验库 (防止重复炼丹)
        self.existing_hashes = set()
        if os.path.exists(EXPERIENCE_DB):
            try:
                with open(EXPERIENCE_DB, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        # 计算源码的 hash 用于去重
                        if "source_code" in item:
                            code_hash = hashlib.md5(item["source_code"].strip().encode()).hexdigest()
                            self.existing_hashes.add(code_hash)
                print(f"📚 已加载现有经验库: {len(self.existing_hashes)} 条经验")
            except Exception as e:
                print(f"⚠️ 读取现有经验库失败: {e}，将重新创建。")
                self.existing_hashes = set()

    def _count_lines(self, file_path):
        """快速统计行数"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except:
            return 0

    def _analyze_single_file(self, file_path):
        """
        核心处理逻辑：读取 -> 校验 -> LLM分析 -> 返回结构化数据
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read().strip()
            
            # 1. 基础哈希去重 check
            code_hash = hashlib.md5(code.encode()).hexdigest()
            if code_hash in self.existing_hashes:
                return None # 跳过已存在的

            # 2. 构造 Prompt
            # 我们要求 LLM 做两件事：鉴别真伪 + 提炼经验
            system_prompt = (
                "You are a Mermaid Code Analyst. Your task is to analyze the provided code snippet.\n"
                "1. **Validation**: Check if it is valid Mermaid code. (Ignore minor syntax errors, focus on structure).\n"
                "2. **Extraction**: If valid, extract the 'Scenario' (What is this graph about?) and 'Design Strategy' (Why use this chart type? Layout? Key features?).\n\n"
                "Output STRICT JSON format:\n"
                "{\n"
                "  \"is_mermaid\": true/false,\n"
                "  \"q\": \"Brief description of the content/scenario (e.g., User Login Flow)\",\n"
                "  \"a\": \"Brief explanation of design choices (e.g., Used SequenceDiagram to show time-ordered interactions...)\"\n"
                "}"
            )

            user_msg = f"Code snippet:\n```mermaid\n{code}\n```"
            
            # 3. 调用 LLM
            response = self.llm.chat(
                [{"role": "user", "content": user_msg}], 
                system_prompt=system_prompt, 
                json_mode=True
            )
            
            result = json.loads(response)
            
            # 4. 结果处理
            if result.get("is_mermaid") is True:
                # 成功提炼
                return {
                    "q": result.get("q", "Unknown Scenario"),
                    "a": result.get("a", "Standard Layout"),
                    "source_code": code # 按照要求，保留源码作为案底
                }
            else:
                # LLM 认为这不是 Mermaid 代码 (可能是误爬的 markdown 文本)
                return "INVALID"

        except Exception as e:
            # print(f"Error processing {file_path}: {e}")
            return None

    def run(self):
        print(f"🚀 开始扫描目录: {RAW_DATA_DIR}")
        all_files = glob.glob(os.path.join(RAW_DATA_DIR, "*.mmd"))
        
        # 1. 第一轮过滤：硬规则 (行数)
        candidates = []
        for p in all_files:
            lines = self._count_lines(p)
            if MIN_LINES <= lines <= MAX_LINES:
                candidates.append(p)
        
        print(f"🔍 扫描到 {len(all_files)} 个文件，经行数过滤({MIN_LINES}-{MAX_LINES})后剩余 {len(candidates)} 个候选。")
        
        new_experiences = []
        invalid_count = 0
        skipped_count = 0
        
        # 2. 第二轮：并发 LLM 提炼
        # 根据你的 API 额度调整 max_workers，DeepSeek 通常 5-10 并发没问题
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 提交任务
            future_to_file = {executor.submit(self._analyze_single_file, fp): fp for fp in candidates}
            
            # 进度条处理
            try:
                iterator = tqdm(as_completed(future_to_file), total=len(candidates), desc="炼丹进度")
            except ImportError:
                iterator = as_completed(future_to_file)
                print("提示: 安装 tqdm 可显示进度条 (pip install tqdm)")

            for future in iterator:
                res = future.result()
                
                if res == "INVALID":
                    invalid_count += 1
                elif res is None:
                    skipped_count += 1
                else:
                    new_experiences.append(res)
                    # 实时写入哈希防止本次运行重复 (虽然 glob 不会重，但为了逻辑严谨)
                    code_hash = hashlib.md5(res['source_code'].encode()).hexdigest()
                    self.existing_hashes.add(code_hash)

        print(f"\n📊 炼丹报告:")
        print(f"   ✅ 新增经验: {len(new_experiences)} 条")
        print(f"   🚫 过滤无效: {invalid_count} 条")
        print(f"   ⏭️ 跳过重复: {skipped_count} 条")

        # 3. 结果保存
        if new_experiences:
            self._save_to_json(new_experiences)
        else:
            print("没有提取到新经验。")

    def _save_to_json(self, new_items):
        """将新经验追加到 JSON 文件"""
        final_data = []
        
        # 读取旧数据
        if os.path.exists(EXPERIENCE_DB):
            try:
                with open(EXPERIENCE_DB, 'r', encoding='utf-8') as f:
                    final_data = json.load(f)
            except:
                final_data = []
        
        # 追加新数据
        final_data.extend(new_items)
        
        # 写入
        with open(EXPERIENCE_DB, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
            
        print(f"💾 经验池已更新，当前总容量: {len(final_data)} 条。")
        print(f"📂 文件路径: {EXPERIENCE_DB}")

if __name__ == "__main__":
    refinery = DataRefinery()
    refinery.run()