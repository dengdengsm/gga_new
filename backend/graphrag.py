import os
import json
import networkx as nx
import numpy as np
import pickle
import torch
import heapq
import time
import re
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional, Set, Tuple
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 假设 Agent 已经按照之前的接口实现好
from Agent import deepseek_agent, qwen_doc_agent
import logging

# 关闭 httpx (OpenAI/DeepSeek 底层通讯库) 的 INFO 日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# 如果还有其他干扰，可以尝试关闭这些常见库的日志
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
# ==========================================
# Configuration & Utils
# ==========================================

MAX_RETRIES = 2
RETRY_DELAY = 1

def clean_json_response(response: str) -> str:
    """清洗 LLM 可能返回的 markdown 标记"""
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0]
    elif "```" in response:
        response = response.split("```")[1].split("```")[0]
    return response.strip()

# ==========================================
# LightGraphRAG V6.0 (Pyramid Architecture)
# ==========================================

class LightGraphRAG:
    """
    LightGraphRAG V6.0: The "Pyramid" Architecture
    
    Structure:
    - Layer 1: Global Backbone (Qwen-Long) -> Defines the "Skeleton".
    - Layer 2: Intermediate Bridge (DeepSeek + Large Chunks) -> Connects flesh to skeleton.
    - Layer 3: Local Detail (DeepSeek + Small Chunks) -> Adds capillary details (Graph-Constrained).
    
    Features:
    - Strict Provenance Tracking (Node -> Set[ChunkIDs]).
    - Intent-Driven Graph Construction.
    - Connectivity-Enforced Local Extraction.
    """
    
    def __init__(self, persist_dir: str = "./graph_db_v6"):
        print("--- 初始化 LightGraphRAG V6.0 (Pyramid Architecture) ---")
        self.persist_dir = persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)
        
        # 1. Graph Data Structure
        # Nodes: id, description, type (backbone/intermediate/leaf), source_chunks (Set), importance (float)
        # Edges: src, dst, description, weight, source_chunk_id
        self.graph = nx.DiGraph()
        self.graph_version = 0

        self.lock = threading.Lock() # ✅ 新增：全局图写入锁
        
        # 2. Chunk Storage
        # 我们维护两套切片：Big Chunks 用于层级2，Small Chunks 用于层级3和最终检索
        self.small_chunks = [] # List[Dict]
        self.big_chunks = []   # List[Dict]
        
        # 3. Embedding Model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"   🚀 Loading Embedding Model (BGE-M3) on {device}...")
        try:
            self.embed_model = SentenceTransformer("BAAI/bge-m3", device=device)
        except Exception as e:
            print(f"   ❌ Embedding Model Load Failed: {e}")
            self.embed_model = None
            
        # 4. Initialize Agents
        print("   🤖 Initializing LLM Agents...")
        self.local_extractor = deepseek_agent(model_name="deepseek-chat") # 64k context
        self.global_planner = qwen_doc_agent(model_name="qwen-long")      # Long context
        
        # 5. Load State
        self.load_graph()

    # =========================================================================
    # Phase 0: Pre-processing
    # =========================================================================

    def _chunk_document_dual_layer(self, doc_path: str):
        """同时生成大粒度(4000)和小粒度(600)切片"""
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            base_id = os.path.basename(doc_path)
            total_len = len(text)
            
            # 1. Big Chunks (For Layer 2: Intermediate Structure)
            # Size: 1500, Overlap: 200
            self.big_chunks = []
            chunk_size_big = 1500
            for i in range(0, total_len, chunk_size_big - 200):
                self.big_chunks.append({
                    "id": f"big_{i//chunk_size_big}",
                    "text": text[i : i + chunk_size_big],
                    "source": base_id
                })
                
            # 2. Small Chunks (For Layer 3 & Retrieval)
            # Size: 300, Overlap: 100
            self.small_chunks = []
            chunk_size_small = 500
            for i in range(0, total_len, chunk_size_small - 100):
                self.small_chunks.append({
                    "id": f"small_{i//chunk_size_small}",
                    "text": text[i : i + chunk_size_small],
                    "source": base_id,
                    "vec": None # To be calculated
                })
            
            print(f"   🔪 Sliced: {len(self.big_chunks)} Big Chunks, {len(self.small_chunks)} Small Chunks.")
            
            # Encode Small Chunks for retrieval
            self._batch_encode_small_chunks()
            
        except Exception as e:
            print(f"❌ File read error: {e}")

    def _batch_encode_small_chunks(self):
        """Only encode small chunks for vector search"""
        if not self.embed_model or not self.small_chunks: return
        print("   📊 Vectorizing Small Chunks...")
        texts = [c['text'] for c in self.small_chunks]
        embeddings = self.embed_model.encode(texts, normalize_embeddings=True,show_progress_bar=False)
        for i, chunk in enumerate(self.small_chunks):
            chunk['vec'] = embeddings[i]

    # =========================================================================
    # Phase 1: Global Backbone Extraction (Qwen)
    # =========================================================================

    def _stage1_extract_backbone(self, doc_path: str, user_intent: str):
        """
        Layer 1: 主干提取
        目标：提取全篇的核心概念和最宏观的流程/关系。
        特点：chunk_id 为空，因为是全篇总结。
        """
        print(f"\n🏗️ [Layer 1] Global Backbone Extraction (Intent: {user_intent})...")
        
        system_prompt = (
            "You are a Knowledge Graph Architect responsible for the 'Skeleton' of the graph.\n"
            "Your goal is to identify the **top-level** entities and relationships that govern the document."
        )
        
        user_prompt = (
            f"User Intent: \"{user_intent}\"\n"
            "Task:\n"
            "1. Read the ENTIRE document.\n"
            "2. Extract 10-20 **Backbone Nodes**. These must be the most critical concepts (System Names, Key Modules, Core Theories).\n"
            "3. Extract **Backbone Edges** that show high-level flow or architecture.\n"
            "4. **Ignore** minor details, implementation specifics, or examples.\n\n"
            "Output JSON Schema:\n"
            "{\n"
            "  \"nodes\": [{\"id\": \"CoreConcept\", \"desc\": \"High-level definition\"}],\n"
            "  \"edges\": [{\"src\": \"NodeA\", \"dst\": \"NodeB\", \"desc\": \"Architectural relationship\"}]\n"
            "}"
        )
        
        try:
            resp = self.global_planner.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                file_path=doc_path, # Qwen Agent handles file reading
                json_mode=True
            )
            data = json.loads(clean_json_response(resp))
            
            count = self._update_graph(data, chunk_id="global_summary", node_type="backbone", weight_boost=5.0)
            print(f"   ✅ Backbone Established: {count} elements added.")
            return data.get("nodes", []) # Return list of dicts for next stage context
        except Exception as e:
            print(f"   ❌ Layer 1 Failed: {e}")
            return []

    # =========================================================================
    # Phase 2: Intermediate Structure (DeepSeek + Big Chunks)
    # =========================================================================
    def _stage2_intermediate_enrichment(self, backbone_nodes: List[Dict], user_intent: str):
        """
        [Layer 2 - Concurrent] 中层填充 (多线程并发版)
        """
        print(f"\n🌉 [Layer 2] Intermediate Structure Enrichment ({len(self.big_chunks)} Big Chunks)...")
        
        # 准备上下文 (只读操作，不需要锁)
        backbone_ids = [n['id'] for n in backbone_nodes]
        backbone_context_str = ", ".join(backbone_ids[:50])
        
        # 定义单个 Chunk 的处理任务
        def process_single_chunk(chunk):
            system_prompt = (
                "You are a Structural Engineer. Your goal is to Bridge local details to the Global Backbone."
                "Prioritize connecting to existing nodes, but also establish local self-contained structures."
            )
            
            user_prompt = (
                f"User Intent: \"{user_intent}\"\n"
                f"**Global Backbone Context**: {backbone_context_str}\n\n"
                f"Current Text Fragment ({chunk['id']}):\n"
                f"```\n{chunk['text']}\n```\n\n"
                "Task:\n"
                "1. **PRIORITY 1 - Anchor to Backbone**: Identify how entities in this text relate to the 'Global Backbone Context'. Create edges connecting local entities to these Backbone Nodes.\n"
                "2. **PRIORITY 2 - Local Structure**: Extract important entities/relationships that are defined LOCALLY in this text, even if they don't directly touch the Backbone yet.\n"
                "3. **Completeness**: Do not ignore a valid relationship just because it's not in the backbone.\n\n"
                "4. **Find As More Nodes And Edges As You Can**"
                "Output JSON:\n"
                "{\n"
                "  \"nodes\": [{\"id\": \"EntityName\", \"desc\": \"Contextual definition\"}],\n"
                "  \"edges\": [{\"src\": \"Source\", \"dst\": \"Target\", \"desc\": \"Relation\"}]\n"
                "}"
            )
            
            try:
                # 1. 网络请求
                resp = self.local_extractor.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    json_mode=True
                )
                
                # === 🛠️ [DEBUG] 打印原始响应的前50个字符，看看是不是根本没返回 JSON ===
                # print(f"   [Raw Resp Snippet] {resp[:50].replace('\n', ' ')}...") 
                
                cleaned_resp = clean_json_response(resp) # 建议把 clean 拿出来单独赋值，方便调试
                data = json.loads(cleaned_resp)
                
                # 2. 图写入
                with self.lock:
                    self._update_graph(data, chunk_id=chunk['id'], weight_boost=5.0)
                return True
                
            except json.JSONDecodeError as je:
                # 🚨 这是最常见的错误：LLM 返回的不是合法 JSON
                print(f"   ❌ [Stage 2 JSON Error] Chunk: {chunk['id']}")
                print(f"      -> Resp received: {resp}") # 打印出来看看它到底回了什么鬼
                return False
            except Exception as e:
                # 🚨 其他错误（网络超时等）
                print(f"   ❌ [Stage 2 Error] Chunk {chunk['id']}: {e}")
                return False

        # 使用线程池并发执行
        # max_workers 建议设为 5-10，太高会触发 API Rate Limit
        with ThreadPoolExecutor(max_workers=8) as executor:
            # 提交所有任务
            futures = [executor.submit(process_single_chunk, chunk) for chunk in self.big_chunks]
            
            # 等待完成并显示简单进度
            completed_count = 0
            for future in as_completed(futures):
                completed_count += 1
                if completed_count % 2 == 0:
                    print(f"   Processed {completed_count}/{len(self.big_chunks)} big chunks...", end='\r')
        
        print(f"\n   ✅ Layer 2 Complete.")

    # =========================================================================
    # Phase 3: Local Drill-down (Concurrent)
    # =========================================================================

    def _stage3_local_drilldown(self, user_intent: str):
        """
        [Layer 3 - Concurrent] 细节下钻 (多线程并发版)
        """
        print(f"\n💎 [Layer 3] Semantic Local Drill-down (Concurrent)...")
        
        # 1. 筛选高优节点 (读操作，无需锁)
        node_importance = nx.get_node_attributes(self.graph, 'importance')
        if not node_importance: return

        sorted_nodes = sorted(
            self.graph.nodes(), 
            key=lambda n: (node_importance.get(n, 0), self.graph.degree(n)), 
            reverse=True
        )
        focus_targets = sorted_nodes
        print(f"   🎯 Focus Targets: {focus_targets[:5]}... (Total {len(focus_targets)})")
        
        # 线程安全的去重集合
        processed_chunk_ids = set()
        chunk_lock = threading.Lock() # 专门保护 processed_chunk_ids 的小锁

        # 定义单个 Focus Node 的处理任务
        def process_single_focus_node(focus_node_id):
            # 获取节点描述 (读图，建议加 try-except 防止别的线程删了节点)
            try:
                node_desc = self.graph.nodes[focus_node_id].get('description', '')
            except KeyError:
                return 0
                
            rich_query = f"{focus_node_id}: {node_desc}"
            
            # 检索 (只读，并发安全)
            hits = self._search_small_chunks(query=rich_query, top_k=50)
            
            tasks_run = 0
            for chunk in hits:
                # 检查是否已处理 (加锁检查)
                with chunk_lock:
                    if chunk['id'] in processed_chunk_ids:
                        continue
                    processed_chunk_ids.add(chunk['id'])
                
                # 执行提取
                self._extract_constrained_details_concurrent(chunk, focus_node_id, node_desc, user_intent)
                tasks_run += 1
            return tasks_run

        # 并发执行
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_single_focus_node, target) for target in focus_targets]
            
            # 等待结果
            total_chunks_analyzed = 0
            for future in as_completed(futures):
                total_chunks_analyzed += future.result()
                print(f"   Drilling down... ({total_chunks_analyzed} chunks analyzed)", end='\r')

        print(f"\n   ✅ Layer 3 Complete. Analyzed {len(processed_chunk_ids)} unique small chunks.")

    def _extract_constrained_details_concurrent(self, chunk: Dict, focus_node: str, focus_desc: str, user_intent: str):
        """
        并发版的 Layer 3 提取器
        区别：内部使用了 self.lock 来保护 _update_graph
        """
        system_prompt = (
            "You are a Detail Analyst. Your primary mission is to expand the graph around the Focus Node."
            "Simultaneously, capture other high-value dense relationships in the text."
        )
        
        user_prompt = (
            f"User Intent: \"{user_intent}\"\n"
            f"**Primary Focus Node**: '{focus_node}' (Context: {focus_desc})\n\n"
            f"Text Fragment ({chunk['id']}):\n"
            f"```\n{chunk['text']}\n```\n\n"
            "Task:\n"
            f"1. **Core Task**: Extract every possible relationship involving **'{focus_node}'**. Explain HOW it interacts with others.\n"
            f"2. **Secondary Task**: If you identify other clear, high-value relationships between entities in this text (even if '{focus_node}' is not involved), extract them as well to densify the graph.\n"
            f"3. **Constraint**: Do not hallucinate connections. If '{focus_node}' is not mentioned or implied, focus on what IS present.\n\n"
            "4. **Find As More Nodes And Edges As You Can**"
            "Output JSON:\n"
            "{\n"
            "  \"nodes\": [{\"id\": \"Entity\", \"desc\": \"Definition\"}],\n"
            "  \"edges\": [{\"src\": \"Source\", \"dst\": \"Target\", \"desc\": \"Specific relation\"}]\n"
            "}"
        )
        
        try:
            # LLM 推理
            resp = self.local_extractor.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                json_mode=True
            )
            
            # === 🛠️ [DEBUG] 检查响应 ===
            if not resp:
                print(f"   ⚠️ [Stage 3] Empty response for focus: {focus_node}")
                return

            cleaned_resp = clean_json_response(resp)
            data = json.loads(cleaned_resp)
            
            # 检查是否有数据，如果没有提取到，也打印一下
            if not data.get("nodes") and not data.get("edges"):
                 # 这说明 LLM 觉得这段话跟 Focus Node 没关系，或者是 Prompt 限制太死了
                # print(f"   ℹ️ [Stage 3] No relations found for {focus_node} in chunk {chunk['id']}")
                pass 
            
            # 图更新
            with self.lock:
                self._update_graph(data, chunk_id=chunk['id'], weight_boost=1.0)
                
        except json.JSONDecodeError:
            # 🚨 必须把这个打印出来，DeepSeek 经常在 JSON 后面加废话导致解析失败
            print(f"   ❌ [Stage 3 JSON Fail] Focus: {focus_node} | Chunk: {chunk['id']}")
            print(f"      -> Content: {resp}") 
        except Exception as e:
            # 🚨 之前这里是 pass，现在必须看报错
            print(f"   ❌ [Stage 3 Exception] {e}")
    # =========================================================================
    # Common Graph Updater
    # =========================================================================

    def _update_graph(self, data: Dict, chunk_id: str, weight_boost: float, node_type:str = "derived") -> int:
        """
        统一的图更新入口。
        负责：
        1. 节点/边的去重与合并。
        2. Provenance (source_chunks) 的更新。
        3. 权重的累加。
        """
        # === 🛠️ [DEBUG START] ===
        new_nodes = len(data.get("nodes", []))
        new_edges = len(data.get("edges", []))
        if new_nodes > 0 or new_edges > 0:
            print(f"   [Graph Update] Source: {chunk_id} | Type: {node_type} | +Nodes: {new_nodes} | +Edges: {new_edges}")
        else:
            print(f"   ⚠️ [Graph Update] Source: {chunk_id} returned EMPTY data!")
        # === 🛠️ [DEBUG END] ===
        
        count = 0
        # ... 原有代码继续 ...
        count = 0
        
        # 1. Update Nodes
        for n_data in data.get("nodes", []):
            nid = n_data.get('id')
            if not nid: continue
            
            count += 1
            if not self.graph.has_node(nid):
                self.graph.add_node(nid, 
                                    description=n_data.get('desc', ''), 
                                    type=node_type,
                                    source_chunks={chunk_id} if chunk_id else set(),
                                    importance=weight_boost)
            else:
                # Merge logic
                node = self.graph.nodes[nid]
                if chunk_id:
                    node['source_chunks'].add(chunk_id)
                node['importance'] += weight_boost
                
                # 如果现有描述太短，且新描述较长，更新描述
                if len(n_data.get('desc', '')) > len(node.get('description', '')):
                    node['description'] = n_data['desc']

        # 2. Update Edges
        for e_data in data.get("edges", []):
            src, dst = e_data.get('src'), e_data.get('dst')
            if not src or not dst: continue
            
            # Ensure endpoints exist (Auto-create if missing to avoid errors)
            for pt in [src, dst]:
                if not self.graph.has_node(pt):
                    self.graph.add_node(pt, description="Inferred", type="inferred", source_chunks={chunk_id}, importance=1.0)
            
            # Add/Merge Edge
            desc = e_data.get('desc', 'related')
            weight = weight_boost
            
            if self.graph.has_edge(src, dst):
                # 如果边已存在，我们将新描述追加进去，形成丰富的上下文
                old_data = self.graph.edges[src, dst]
                if desc not in old_data['description']:
                    old_data['description'] += f" | {desc}"
                old_data['weight'] += weight
                # 记录 chunk_id (这里简单覆盖，或者扩展为列表)
                if chunk_id:
                    old_data['source_chunk_id'] = chunk_id 
            else:
                self.graph.add_edge(src, dst, 
                                    description=desc, 
                                    weight=weight, 
                                    source_chunk_id=chunk_id)
        self.graph_version += 1
        return count
    
    # =========================================================================
    # Phase 4: Graph Optimization (Backbone-Centric Rewiring)
    # =========================================================================

    def _stage4_graph_optimization(self, max_iterations: int = 3):
        """
        Stage 4: 图谱结构优化
        基于连通分量分析，清洗噪音，合并同义词，强制连通孤岛。
        """
        print(f"\n⚡ [Stage 4] Graph Optimization (Backbone-Centric Rewiring)...")
        
        for i in range(max_iterations):
            # 1. 提取弱连通分量 (针对 DiGraph)
            # 弱连通意味着把边看作无向时是连通的，这符合我们对“孤岛”的定义
            components = list(nx.weakly_connected_components(self.graph))
            
            if len(components) <= 1:
                print("   ✅ Graph is fully connected. Optimization finished.")
                break
            
            # 按节点数量排序，最大的为主干
            components.sort(key=len, reverse=True)
            backbone_nodes = components[0]
            fragment_nodes = set().union(*components[1:])
            
            # 如果主干太小（比如刚开始构建），可能不需要优化，或者逻辑不同
            if len(backbone_nodes) < 3:
                print("   ⚠️ Graph too small to optimize.")
                break

            print(f"   🔄 [Iter {i+1}] Backbone: {len(backbone_nodes)} nodes | Fragments: {len(components)-1} clusters | Orphan Nodes: {len(fragment_nodes)}")

            # 2. 准备上下文 (Backbone Context)
            # 采样一些 Backbone 的核心边，让 LLM 知道主干里有什么
            backbone_subgraph = self.graph.subgraph(backbone_nodes)
            # 优先选择 importance 高的节点的边
            sorted_edges = sorted(backbone_subgraph.edges(data=True), 
                                  key=lambda x: self.graph.nodes[x[0]].get('importance', 0) + self.graph.nodes[x[1]].get('importance', 0), 
                                  reverse=True)
            
            backbone_desc_lines = []
            for u, v, d in sorted_edges[:100]: # 限制 Token，只给 Top 100 边
                u_desc = self.graph.nodes[u].get('description', '')[:50]
                v_desc = self.graph.nodes[v].get('description', '')[:50]
                rel = d.get('description', 'related')[:30]
                backbone_desc_lines.append(f"({u}) --[{rel}]--> ({v})")
            
            backbone_str = "\n".join(backbone_desc_lines)

            # 3. 准备目标数据 (Fragment Context)
            # 对于孤岛，我们需要把它们的内容发给 LLM
            fragment_subgraph = self.graph.subgraph(fragment_nodes)
            fragment_lines = []
            
            # 提取碎片中的边
            for u, v, d in list(fragment_subgraph.edges(data=True))[:80]:
                u_desc = self.graph.nodes[u].get('description', 'No desc')
                v_desc = self.graph.nodes[v].get('description', 'No desc')
                fragment_lines.append(f"EDGE: ({u} [desc: {u_desc}]) --[{d.get('description','?')}]--> ({v})")
            
            # 提取碎片中的孤立点 (没有边的点)
            isolates = [n for n in fragment_nodes if fragment_subgraph.degree(n) == 0]
            for node in isolates[:30]:
                desc = self.graph.nodes[node].get('description', 'No desc')
                fragment_lines.append(f"NODE: {node} [desc: {desc}]")
                
            fragment_str = "\n".join(fragment_lines)
            
            if not fragment_str.strip():
                print("   -> No meaningful fragments found. Cleaning leftovers.")
                self.graph.remove_nodes_from(list(nx.isolates(self.graph)))
                continue

            # 4. LLM 决策
            self._execute_optimization_prompt(backbone_str, fragment_str, backbone_nodes)
            self.graph_version += 1

        # 最终清理：移除仍然无法连接的微小孤立点
        final_isolates = list(nx.isolates(self.graph))
        if final_isolates:
            self.graph.remove_nodes_from(final_isolates)
            print(f"   🧹 Final Cleanup: Removed {len(final_isolates)} stubborn isolated nodes.")

    def _execute_optimization_prompt(self, backbone_str, fragment_str, backbone_nodes):
        """执行优化指令并应用修改"""
        system_prompt = "You are a Knowledge Graph Cleaner & Linker."
        
        user_prompt = (
            f"=== MAIN KNOWLEDGE BACKBONE (READ ONLY) ===\n"
            f"These nodes are the core truth. DO NOT DELETE THEM.\n"
            f"{backbone_str}\n\n"
            f"=== DISCONNECTED FRAGMENTS (TARGETS) ===\n"
            f"These entities are currently disconnected from the Backbone.\n"
            f"{fragment_str}\n\n"
            f"=== TASK ===\n"
            "Analyze the Fragments and decide their fate:\n"
            "1. **DELETE**: If it is noise, generic headers (e.g. 'Table 1'), or irrelevant.\n"
            "2. **MERGE**: If a fragment entity is a SYNONYM of a Backbone entity. (e.g., 'LLMs' -> 'Large Language Models').\n"
            "   * 'source' must be Fragment Node, 'target' must be Backbone Node.\n"
            "3. **CONNECT**: If the fragment is valid but missing a link. Create a specific relationship to a Backbone Node.\n\n"
            "=== OUTPUT JSON ===\n"
            "{\n"
            "  \"operations\": [\n"
            "    {\"type\": \"DELETE\", \"nodes\": [\"bad_node_1\"]},\n"
            "    {\"type\": \"MERGE\", \"source\": \"fragment_node\", \"target\": \"backbone_node\"},\n"
            "    {\"type\": \"CONNECT\", \"source\": \"fragment_node\", \"target\": \"backbone_node\", \"desc\": \"connection logic\", \"weight\": 3}\n"
            "  ]\n"
            "}"
        )
        
        try:
            resp = self.local_extractor.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                json_mode=True
            )
            data = json.loads(clean_json_response(resp))
            ops = data.get("operations", [])
            
            if not ops: 
                print("   -> LLM suggests no changes.")
                return

            print(f"   -> Executing {len(ops)} operations...")
            
            for op in ops:
                op_type = op.get("type", "").upper()
                
                if op_type == "DELETE":
                    for n in op.get("nodes", []):
                        if n in backbone_nodes: continue # 保护主干
                        if self.graph.has_node(n):
                            self.graph.remove_node(n)
                            
                elif op_type == "MERGE":
                    src = op.get("source")
                    tgt = op.get("target")
                    self._merge_nodes(src, tgt, backbone_nodes)
                            
                elif op_type == "CONNECT":
                    src = op.get("source")
                    tgt = op.get("target")
                    desc = op.get("desc", "Connected by optimizer")
                    weight = op.get("weight", 2.0)
                    if self.graph.has_node(src) and self.graph.has_node(tgt):
                        self.graph.add_edge(src, tgt, description=desc, weight=weight, source_chunk_id="optimization")

        except Exception as e:
            print(f"   ⚠️ Optimization step failed: {e}")

    def _merge_nodes(self, src, tgt, backbone_nodes):
        """
        安全的节点合并逻辑：Src -> Tgt
        1. 转移边
        2. 合并元数据 (source_chunks, importance)
        3. 删除 Src
        """
        if not (self.graph.has_node(src) and self.graph.has_node(tgt)): return
        
        # 防止反向合并（把主干合到了碎片里）
        if src in backbone_nodes and tgt not in backbone_nodes:
            # Swap logic to protect backbone
            src, tgt = tgt, src
            
        # 1. Merge Attributes
        tgt_node = self.graph.nodes[tgt]
        src_node = self.graph.nodes[src]
        
        # 合并 chunks
        tgt_node['source_chunks'].update(src_node.get('source_chunks', set()))
        # 累加 importance
        tgt_node['importance'] = tgt_node.get('importance', 1.0) + src_node.get('importance', 1.0)
        # 描述取最长的
        if len(src_node.get('description', '')) > len(tgt_node.get('description', '')):
            tgt_node['description'] = src_node['description']

        # 2. Transfer Edges
        # Out edges: src -> nbr  ==>  tgt -> nbr
        for _, nbr, data in list(self.graph.out_edges(src, data=True)):
            if nbr == tgt: continue # 避免自环
            if self.graph.has_edge(tgt, nbr):
                # 边已存在，合并权重
                self.graph[tgt][nbr]['weight'] += data.get('weight', 1.0)
            else:
                self.graph.add_edge(tgt, nbr, **data)
        
        # In edges: nbr -> src  ==>  nbr -> tgt
        for nbr, _, data in list(self.graph.in_edges(src, data=True)):
            if nbr == tgt: continue
            if self.graph.has_edge(nbr, tgt):
                self.graph[nbr][tgt]['weight'] += data.get('weight', 1.0)
            else:
                self.graph.add_edge(nbr, tgt, **data)
                
        # 3. Remove Source
        self.graph.remove_node(src)
        # print(f"      [Merged] {src} -> {tgt}")

    # =========================================================================
    # Main Build Entry
    # =========================================================================

    def build_graph(self, doc_path: str, user_intent: str = "General Analysis"):
        print(f"🚀 Starting Build Process for {doc_path}...")
        
        # Step 0: Slice
        self._chunk_document_dual_layer(doc_path)
        if not self.big_chunks: return
        
        # Step 1: Layer 1 - Global Backbone
        backbone_nodes = self._stage1_extract_backbone(doc_path, user_intent)
        self.graph_version += 1
        # Step 2: Layer 2 - Intermediate
        self._stage2_intermediate_enrichment(backbone_nodes, user_intent)
        self.graph_version += 1
        # Step 3: Layer 3 - Local Drill-down
        self._stage3_local_drilldown(user_intent)
        self.graph_version +=1
        # Step 4: Graph Optimization ---
        self._stage4_graph_optimization(max_iterations=3)
        self.graph_version+=1
        # Save
        self.save_graph()
        print(f"\n✅ Graph Build Complete.")
        print(f"   Nodes: {self.graph.number_of_nodes()}")
        print(f"   Edges: {self.graph.number_of_edges()}")

    # =========================================================================
    # Graph-First Retrieval Engine
    # =========================================================================

    def _get_chunk_text_by_id(self, chunk_id: str) -> Optional[str]:
        """
        [Helper] 根据 ID 从内存列表中查找原始文本。
        优先查找 Small Chunks (细节)，其次 Big Chunks (背景)。
        """
        if not chunk_id: return None
        
        # 1. Try Small Chunks (Priority)
        for c in self.small_chunks:
            if c['id'] == chunk_id:
                return c['text']
        
        # 2. Try Big Chunks (Fallback)
        for c in self.big_chunks:
            if c['id'] == chunk_id:
                return c['text']
                
        return None

    def search(self, query: str, top_k: int = 3) -> str:
        """
        [Drill-Down Optimized Search Engine]
        
        执行逻辑:
        1. **Semantic Anchor**: Query <-> (Node + Description). 寻找语义最接近的概念锚点。
        2. **Graph Expansion**: 扩散 1-Hop，获取关系描述。
        3. **Weighted Voting**: 
           - 投票给 Chunk。
           - Small Chunk 权重 > Big Chunk。
           - 包含 Anchor 的 Chunk 权重倍增。
        4. **Rich Context Assembly**: 
           - 组装定义(Definitions)、关系(Relations)、证据(Evidence)。
        """
        if self.graph.number_of_nodes() == 0: 
            return "Knowledge Graph is empty."
        
        print(f"\n🔎 [Drill-Down] Searching Graph for: \"{query}\"")
        query_vec = self._get_embedding(query)
        
        # =================================================
        # Step 1: Anchor Identification (Pure Semantic)
        # =================================================
        node_candidates = []
        for n, attr in self.graph.nodes(data=True):
            # 组合 "ID + Description" 以捕捉精准语义
            desc = attr.get('description', 'No description')
            node_rich_text = f"{n}: {desc}"
            
            n_vec = self._get_embedding(node_rich_text)
            score = self._cosine_similarity(query_vec, n_vec)
            
            # 语义过滤 (Threshold 0.35)
            if score > 0.35: 
                node_candidates.append((score, n, desc))
        
        # 排序并截取 Top 5 锚点
        node_candidates.sort(key=lambda x: x[0], reverse=True)
        top_anchors = node_candidates[:5] # List of (score, node_id, desc)
        anchor_ids = [n for s, n, d in top_anchors]
        
        print(f"   ⚓ Top Anchors: {anchor_ids}")
        
        if not anchor_ids: 
            return "No relevant concepts found in the Knowledge Graph."

        # =================================================
        # Step 2: Subgraph Expansion (Contextualization)
        # =================================================
        subgraph_nodes = set(anchor_ids)
        edge_context = []
        
        for anchor in anchor_ids:
            # Outgoing Edges
            for nbr in self.graph.successors(anchor):
                if nbr not in subgraph_nodes:
                    subgraph_nodes.add(nbr)
                    attr = self.graph.edges[anchor, nbr]
                    edge_context.append(f"• {anchor} -> {nbr}: {attr.get('description','')}")
            
            # Incoming Edges (溯源)
            for nbr in self.graph.predecessors(anchor):
                if nbr not in subgraph_nodes:
                    subgraph_nodes.add(nbr)
                    attr = self.graph.edges[nbr, anchor]
                    edge_context.append(f"• {nbr} -> {anchor}: {attr.get('description','')}")

        # =================================================
        # Step 3: Weighted Voting (Detail First)
        # =================================================
        chunk_votes = Counter()
        chunk_to_entities = defaultdict(list) # 记录每个 Chunk 命中了哪些图谱节点
        
        for node in subgraph_nodes:
            s_chunks = self.graph.nodes[node].get('source_chunks', set())
            
            for cid in s_chunks:
                if not cid or cid == "global_summary": continue
                
                # 记录实体命中情况，用于最后展示
                chunk_to_entities[cid].append(node)
                
                # 打分逻辑
                score = 1.0
                # A. Anchor Bonus: 包含核心锚点
                if node in anchor_ids:
                    score += 2.0
                
                # B. Granularity Bonus: 小切片优先
                if cid.startswith("small_"):
                    score += 1.5 
                elif cid.startswith("big_"):
                    score += 0.5 
                
                chunk_votes[cid] += score

        top_chunk_ids = [cid for cid, v in chunk_votes.most_common(top_k)]
        print(f"   🗳️  Top Chunks (Weighted): {top_chunk_ids}")

        # =================================================
        # Step 4: Rich Context Assembly
        # =================================================
        final_context = []
        
        # --- Section 1: Core Concept Definitions (对齐术语) ---
        final_context.append("### 🧠 Core Concepts & Definitions")
        for score, n, desc in top_anchors:
            final_context.append(f"- **{n}**: {desc} (Confidence: {score:.2f})")
            
        # --- Section 2: Knowledge Graph Logic (推理路径) ---
        final_context.append("\n### 🕸️ Graph Logic Pathways")
        if edge_context:
            # 排序：优先展示描述更长、更详细的边
            sorted_edges = sorted(list(set(edge_context)), key=lambda x: len(x), reverse=True)
            final_context.extend(sorted_edges[:15]) # 展示 Top 15 条边
        else:
            final_context.append("(No explicit relationships found in subgraph)")

        # --- Section 3: Source Evidence (原始片段) ---
        final_context.append("\n### 📖 Detailed Source Evidence")
        for cid in top_chunk_ids:
            text = self._get_chunk_text_by_id(cid)
            if not text: continue
            
            # 获取该 Chunk 命中的图谱实体，辅助 LLM 理解这段话的重点
            hit_nodes = chunk_to_entities.get(cid, [])
            hit_anchors = [n for n in hit_nodes if n in anchor_ids]
            other_hits = [n for n in hit_nodes if n not in anchor_ids][:5] # 限制显示数量
            
            header_info = f"**[Source ID: {cid}]**"
            if hit_anchors:
                header_info += f"\n*Key Anchors Hit*: {', '.join(hit_anchors)}"
            if other_hits:
                header_info += f"\n*Related Entities*: {', '.join(other_hits)}..."
                
            final_context.append(f"\n{header_info}")
            final_context.append(f"```text\n{text}\n```")
            final_context.append("---")
            
        return "\n".join(final_context)
    
    # =========================================================================
    # Helpers
    # =========================================================================

    def _search_small_chunks(self, query: str, top_k: int = 3) -> List[Dict]:
        """Utility for Layer 3"""
        if not self.small_chunks: return []
        q_vec = self._get_embedding(query)
        scores = []
        for c in self.small_chunks:
            if c['vec'] is None: continue
            s = self._cosine_similarity(q_vec, c['vec'])
            scores.append((s, c))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [c for s, c in scores[:top_k]]

    def _get_embedding(self, text: str) -> np.ndarray:
        if not self.embed_model: return np.zeros(1024)
        return self.embed_model.encode(text, normalize_embeddings=True,show_progress_bar=False)

    def _cosine_similarity(self, v1, v2):
        return float(np.dot(v1, v2))

    def clear_graph(self):
        """
        [System] 重置内存状态
        用于 reload_db 时彻底清除旧数据，或者在重新 build_graph 前清空当前状态。
        """
        # 1. 重置图结构
        self.graph = nx.DiGraph()
        
        # 2. 重置切片列表
        self.small_chunks = []
        self.big_chunks = []
        
        # 3. (可选) 如果你有缓存机制，也可以在这里清理
        
        print("🧹 [System] Memory cleared (Graph & Chunks reset).")
    # =========================================================================
    # Persistence (JSON Edition - Compatible with your old workflow)
    # =========================================================================

    def save_graph(self):
        """
        保存图谱到 JSON (为了兼容性和可读性)
        """
        try:
            # 1. 准备图数据
            # NetworkX 的 node_link_data 可以把图转为 JSON 友好的字典
            # 但我们需要先处理 Set 类型的属性，因为 JSON 不支持 Set
            G_export = self.graph.copy()
            for n in G_export.nodes():
                # Set -> List
                s = G_export.nodes[n].get('source_chunks', set())
                G_export.nodes[n]['source_chunks'] = list(s)
            
            # 转换为字典结构
            graph_json_data = nx.node_link_data(G_export)
            
            # 2. 写入 graph.json
            with open(os.path.join(self.persist_dir, "graph.json"), "w", encoding='utf-8') as f:
                json.dump(graph_json_data, f, ensure_ascii=False, indent=2)
            
            # 3. 写入 chunks.pkl (向量数据还是推荐 pickle，因 numpy array 转 json 较麻烦)
            with open(os.path.join(self.persist_dir, "chunks.pkl"), "wb") as f:
                pickle.dump({"small": self.small_chunks, "big": self.big_chunks}, f)
                
            print(f"💾 Graph saved to {self.persist_dir}/graph.json")
        except Exception as e:
            print(f"❌ Save failed: {e}")

    def load_graph(self):
        """
        从 JSON 加载图谱
        """
        try:
            graph_path = os.path.join(self.persist_dir, "graph.json")
            chunk_path = os.path.join(self.persist_dir, "chunks.pkl")
            
            # 1. 加载图结构
            if os.path.exists(graph_path):
                with open(graph_path, 'r', encoding='utf-8') as f:
                    graph_json_data = json.load(f)
                
                # 恢复图对象 (Directed Graph)
                self.graph = nx.node_link_graph(graph_json_data, directed=True)
                
                # 恢复数据类型 (List -> Set, String -> Float)
                for n in self.graph.nodes():
                    # 恢复 source_chunks 为 Set
                    val = self.graph.nodes[n].get('source_chunks', [])
                    self.graph.nodes[n]['source_chunks'] = set(val) if isinstance(val, list) else set()
                        
                    # 恢复 importance 为 float
                    imp = self.graph.nodes[n].get('importance', 1.0)
                    self.graph.nodes[n]['importance'] = float(imp)
            else:
                print("ℹ️ No existing graph found, initializing new.")
                self.graph = nx.DiGraph()

            # 2. 加载切片数据
            if os.path.exists(chunk_path):
                with open(chunk_path, "rb") as f:
                    data = pickle.load(f)
                    self.small_chunks = data.get("small", [])
                    self.big_chunks = data.get("big", [])
                    
            print(f"📂 Loaded: {self.graph.number_of_nodes()} nodes from JSON.")
            
        except Exception as e:
            print(f"⚠️ Load warning (Starting fresh): {e}")
            self.graph = nx.DiGraph()
            self.small_chunks = []
            self.big_chunks = []

    def reload_db(self, new_persist_dir: str):
        """
        [System] 安全切换项目数据库 (Auto-Save & Switch)
        
        功能:
        1. 自动保存: 切换前强制保存当前项目数据到旧目录。
        2. 环境重置: 清空内存，防止旧项目数据混入新项目。
        3. 路径切换: 指向新目录并加载数据 (支持 JSON/Pickle)。
        """
        print(f"🔄 [GraphRAG] Requesting project switch to: {new_persist_dir}")
        
        # 1. [Auto-Save] 自动保存当前进度
        # 只有当内存里确实有数据时才保存，避免空跑
        if self.graph.number_of_nodes() > 0 or len(self.small_chunks) > 0:
            print(f"💾 [Auto-Save] Saving current workspace to: {self.persist_dir} ...")
            self.save_graph() # 调用刚才修改过的 JSON 版 save_graph
        else:
            print("ℹ️ [Info] Current workspace is empty, skipping auto-save.")

        # 2. [Switch Dir] 切换路径变量
        self.persist_dir = new_persist_dir
        # 确保新目录存在，不存在则创建
        os.makedirs(self.persist_dir, exist_ok=True)

        # 3. [Clear RAM] 彻底清空内存对象
        # 这一步至关重要！否则上一个项目的节点会残留在 self.graph 里
        self.clear_graph() 
        
        # 4. [Load New] 加载新项目数据
        # 尝试读取新目录下的 graph.json 和 chunks.pkl
        # 如果是新目录（无文件），load_graph 会自动初始化空状态
        self.load_graph()
        
        print(f"✅ [Switch Complete] Now working on: {new_persist_dir}")
        print(f"   Current State: {self.graph.number_of_nodes()} Nodes, {len(self.small_chunks)} Small Chunks.")

    def get_graph_snapshot(self):
        """获取图谱快照 (带 Debug 打印)"""
        try:

            current_ver = self.graph_version
            node_count = self.graph.number_of_nodes()
            edge_count = self.graph.number_of_edges()
            
            nodes = []
            for n, attr in self.graph.nodes(data=True):
                degree = self.graph.degree(n)
                size = 5 + (degree * 0.5) if degree else 5
                nodes.append({
                    "id": str(n),
                    "label": str(n),
                    "color": "#4F8BF9",
                    "val": size,
                    "title": attr.get("description", "") 
                })
            
            links = []
            for u, v, data in self.graph.edges(data=True):
                links.append({
                    "source": str(u), 
                    "target": str(v), 
                    "label": data.get("description", "") # 修复字段名
                })

            # 🛠️ [DEBUG] 打印一下，看看前端到底有没有来拿数据
            print(f"📡 [Snapshot] Frontend requested. Ver: {current_ver} | Nodes: {node_count}")

            return {
                "version": current_ver, 
                "nodes": nodes, 
                "links": links
            }
        except Exception as e:
            print(f"❌ [Snapshot Error] {e}")
            return {"version": 0, "nodes": [], "links": []}