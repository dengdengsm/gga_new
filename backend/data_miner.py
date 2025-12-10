
import os
import re
import time
import requests
import hashlib
import json
import base64
import random
from concurrent.futures import ThreadPoolExecutor

# --- 你的现有模块 ---
import utils
from code_revise import CodeReviseAgent

# ================= 暴力配置区 =================
# ⚠️ 依然需要你的 Token
GITHUB_TOKEN = "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" 

# 保存路径
SAVE_DIR = "./knowledge/mermaid_code"
MISTAKE_DB = "./knowledge/experience/mistakes.json"

# 【关键升级】全套 Mermaid 核心语法关键词 (基于你的图片和官方文档)
# 只要代码中不包含这些词中的任何一个，直接视为垃圾数据丢弃
VALID_KEYWORDS = [
    # 基础流程图
    "graph", "flowchart", 
    # 时序图与类图
    "sequencediagram", "classdiagram", 
    # 状态与关系图
    "statediagram", "statediagram-v2", "erdiagram", 
    # 用户旅程与甘特图
    "journey", "gantt", 
    # 饼图与象限图
    "pie", "quadrantchart", 
    # 需求图与 Git图
    "requirementdiagram", "gitgraph", 
    # C4 架构图
    "c4context", "c4container", "c4component",
    # 思维导图与时间轴
    "mindmap", "timeline", 
    # 实验性/新特性 (对应你图片里的 architecture, block, packet 等)
    "zenuml", "sankey-beta", "sankey", "xychart-beta", "xychart",
    "block-beta", "block", "packet-beta", "packet", 
    "kanban", "architecture-beta", "architecture", "treemap"
]

# 搜索策略：直接针对这些高级图表进行搜索
SEARCH_QUERIES = [
    "extension:mmd",                 # 基础盘
    "filename:*.md mermaid",         # 广撒网
    # 针对稀有图表的定向爆破
    "filename:*.md architecture-beta",
    "filename:*.md packet-beta",
    "filename:*.md block-beta",
    "filename:*.md kanban",
    "filename:*.md xychart",
    "filename:*.md c4context",
    "filename:*.md mindmap",
    "filename:*.md timeline",
    "filename:*.md zenuml",
]

# 翻页深度 (暴力模式)
MAX_PAGES = 5  
PER_PAGE = 100 
# ==========================================

class GitHubMiner:
    def __init__(self, token, save_dir):
        self.token = token
        self.save_dir = save_dir
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        os.makedirs(self.save_dir, exist_ok=True)
        
        self.reviser = CodeReviseAgent(
            knowledge_base_dir="./knowledge_base",
            mistake_file_path=MISTAKE_DB
        )
        self.session = requests.Session()

    def _check_rate_limit(self, response):
        """防御机制：API 余额不足时强制休眠"""
        remaining = int(response.headers.get("x-ratelimit-remaining", 10))
        reset_time = int(response.headers.get("x-ratelimit-reset", 0))
        
        if remaining < 5:
            now = int(time.time())
            sleep_time = reset_time - now + 5
            if sleep_time > 0:
                print(f"\n⚠️ [触发熔断] API 额度耗尽！正在休眠 {sleep_time} 秒...")
                time.sleep(sleep_time)
                print("♻️ 满血复活，继续挖掘！")

    def search_github_aggressive(self, query):
        """【暴力模式】分页搜索"""
        url = "https://api.github.com/search/code"
        all_items = []
        
        print(f"\n💣 正在轰炸搜索词: [{query}]")
        
        for page in range(1, MAX_PAGES + 1):
            params = {"q": query, "per_page": PER_PAGE, "page": page}
            
            try:
                while True:
                    resp = self.session.get(url, headers=self.headers, params=params)
                    
                    if resp.status_code == 200:
                        items = resp.json().get("items", [])
                        if not items:
                            print(f"   -> 第 {page} 页无数据，停止翻页。")
                            return all_items
                        
                        print(f"   -> 第 {page} 页: 捕获 {len(items)} 个目标")
                        all_items.extend(items)
                        time.sleep(2.5) # 手动降速防止 403
                        break 
                        
                    elif resp.status_code == 403:
                        retry_after = int(resp.headers.get("Retry-After", 60))
                        print(f"   🚫 搜索过热 (403)，冷却 {retry_after} 秒...")
                        time.sleep(retry_after + 2)
                        continue
                    else:
                        print(f"   ❌ 搜索出错: {resp.status_code}")
                        return all_items

            except Exception as e:
                print(f"   ❌ 网络异常: {e}")
                time.sleep(5)

        return all_items

    def _is_valid_mermaid_content(self, code):
        """
        【核心过滤逻辑】
        正则提取出来的内容，必须包含 VALID_KEYWORDS 中的至少一个。
        不区分大小写。
        """
        code_lower = code.lower()
        
        # 1. 长度检查：太短的肯定不是正经图
        if len(code.strip()) < 10:
            return False
            
        # 2. 关键词命中检查 (The "Accept Full Set or Reject" Logic)
        for kw in VALID_KEYWORDS:
            if kw in code_lower:
                return True
                
        return False

    def download_and_extract(self, item):
        """下载并提取"""
        file_url = item.get("url")
        path = item.get("path")
        
        try:
            resp = self.session.get(file_url, headers=self.headers)
            self._check_rate_limit(resp)
            
            if resp.status_code != 200: return 0
            
            content_json = resp.json()
            if "content" not in content_json: return 0
                
            raw_content = base64.b64decode(content_json["content"]).decode('utf-8', errors='ignore')
            extracted_codes = []
            
            # 策略 A: .mmd 文件 (直接视为代码，但仍需过关键词检查)
            if path.endswith(".mmd"):
                extracted_codes.append(raw_content)
                
            # 策略 B: .md 文件 (正则提取 ```mermaid ... ```)
            else:
                # 正则：强制匹配 ```mermaid (内容) ```
                # 注意：这里我们放宽了 mermaid 后面可能跟的字符，只要在 ``` 块内即可
                pattern = r"```\s*mermaid\s*\n(.*?)\n\s*```"
                matches = re.findall(pattern, raw_content, re.DOTALL | re.IGNORECASE)
                extracted_codes.extend(matches)

            count = 0
            for code in extracted_codes:
                code = code.strip()
                
                # 【严格过滤】找不到关键词直接废除
                if not self._is_valid_mermaid_content(code):
                    continue
                
                # 哈希去重
                file_hash = hashlib.md5(code.encode('utf-8')).hexdigest()
                save_path = os.path.join(self.save_dir, f"{file_hash}.mmd")
                
                if not os.path.exists(save_path):
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(code)
                    count += 1
            return count

        except Exception as e:
            return 0

    def verify_and_learn(self):
        """闭环学习与清理"""
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".mmd")]
        total = len(files)
        if total == 0: return

        print(f"\n🎓 启动批量审阅 (库存: {total} 个文件)...")
        stats = {"valid": 0, "fixed": 0, "deleted": 0}
        
        for i, filename in enumerate(files):
            if i % 10 == 0: print(f"   ...进度 {i}/{total}")
            
            file_path = os.path.join(self.save_dir, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                original_code = f.read()
            
            # 1. 校验
            res = utils.quick_validate_mermaid(original_code)
            if res['valid']:
                stats["valid"] += 1
                continue
            
            # 2. 尝试修复
            fixed_code = self.reviser.revise_code(original_code, error_message=res['error'])
            
            # 3. 二次校验
            retry_res = utils.quick_validate_mermaid(fixed_code)
            if retry_res['valid']:
                stats["fixed"] += 1
                try:
                    self.reviser.record_mistake(original_code, res['error'], fixed_code)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                except: pass
            else:
                stats["deleted"] += 1
                os.remove(file_path) 

        print(f"\n📊 挖掘报告:")
        print(f"   ✅ 原生优质: {stats['valid']}")
        print(f"   🔧 修复挽回: {stats['fixed']}")
        print(f"   🗑️ 删除废料: {stats['deleted']}")
        print(f"   💰 当前库存: {len(os.listdir(self.save_dir))} 个高质量片段")

    def run(self):
        print("🚀 GitHub Mermaid 数据挖掘机 (Full-Spectrum Mode) 启动...")
        print(f"   🎯 目标: 全量 Mermaid 语法 ({len(VALID_KEYWORDS)} 种关键词)")
        
        total_extracted = 0
        
        for query in SEARCH_QUERIES:
            items = self.search_github_aggressive(query)
            if not items: continue
            
            print(f"   📥 开始下载解析 {len(items)} 个文件...")
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(self.download_and_extract, items))
                count = sum(results)
                total_extracted += count
                print(f"   -> 本轮入库: {count} 片段")
        
        print(f"\n✅ 挖掘结束，累计获取 {total_extracted} 个新片段。")
        
        if total_extracted > 0:
            self.verify_and_learn()

if __name__ == "__main__":
    if "xx" in GITHUB_TOKEN:
        print("❌ 别急着跑！先把 Token 填进去！")
    else:
        miner = GitHubMiner(GITHUB_TOKEN, SAVE_DIR)
        miner.run()
