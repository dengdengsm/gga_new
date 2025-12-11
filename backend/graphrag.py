import os
import chromadb
import torch
import json
import uuid
import networkx as nx
import concurrent.futures
from typing import List, Tuple, Set, Dict, Any
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from Agent import deepseek_agent, Message

class LightGraphRAG:
    def __init__(self, persist_dir: str = "./.local_graph_db", prompt_dir: str = "./prompt/graphrag"):
        """
        初始化轻量级 GraphRAG V3.1 (Backbone-Fragment Optimization with Safety Limits)
        Updates:
        - Prompt Hardening: Strict limits on output size (Max 20 ops).
        - Backbone Protection: Explicit constraints against modifying core nodes.
        """
        print("--- 初始化 LightGraphRAG V3.1 (Backbone-Centric Safe Mode) ---")
        
        self.prompt_dir = prompt_dir
        os.makedirs(self.prompt_dir, exist_ok=True) 
        
        # 检查设备
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.encoder = SentenceTransformer("BAAI/bge-m3", device=device)
        
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        self.node_collection = self.client.get_or_create_collection(
            name="graph_nodes",
            metadata={"hnsw:space": "cosine"}
        )

        self.chunk_collection = self.client.get_or_create_collection(
            name="graph_chunks",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.graph_path = os.path.join(persist_dir, "knowledge_graph.json")
        self.graph = nx.Graph()
        self._load_graph()
        
        self.extractor = deepseek_agent(model_name="deepseek-chat")

    def _load_graph(self):
        if os.path.exists(self.graph_path):
            with open(self.graph_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.graph = nx.node_link_graph(data)
        else:
            os.makedirs(os.path.dirname(self.graph_path), exist_ok=True)

    def _save_graph(self):
        data = nx.node_link_data(self.graph)
        with open(self.graph_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def _load_prompt_content(self, prompt_file: str, default_content: str = "") -> str:
        full_path = os.path.join(self.prompt_dir, prompt_file)
        if not os.path.exists(full_path) and default_content:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
            return default_content
        elif os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        return default_content

    def _read_text_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            print("UTF-8 decode failed, trying latin-1...")
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()

    def _add_edge_safe(self, src: str, tgt: str, relation: str, source_id: str, summary: str):
        if self.graph.has_edge(src, tgt):
            edge_data = self.graph[src][tgt]
            if 'evidence' not in edge_data: edge_data['evidence'] = []
            
            exists = any(e.get('chunk_id') == source_id for e in edge_data['evidence'])
            if not exists:
                edge_data['evidence'].append({"chunk_id": source_id, "summary": summary})
        else:
            self.graph.add_edge(src, tgt, relation=relation, evidence=[{"chunk_id": source_id, "summary": summary}])

    # --- Phase 1 ---
    def _extract_chunk_content(self, text_chunk: str, system_prompt: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": f"Text Fragment:\n{text_chunk}"}]
        try:
            response = self.extractor.chat(messages, system_prompt=system_prompt, json_mode=True)
            return json.loads(response)
        except Exception as e:
            print(f"  [Error] 基础提取失败: {e}")
            return {"summary": "", "triples": []}

    # --- Phase 2 ---
    def _refine_adjacent_logic(self, chunk_curr: str, chunk_next: str, 
                             curr_id: str, next_id: str, 
                             prompt_text: str,
                             global_summaries: List[str],
                             known_triples: List[List[str]]) -> List[List[str]]:
        
        summary_context_str = "\n".join([f"- {i+1}. {s}" for i, s in enumerate(global_summaries) if s])
        known_triples_str = "; ".join([f"({t[0]}, {t[1]}, {t[2]})" for t in known_triples])
        
        user_msg = f"""
        === Global Context (Story Flow) ===
        {summary_context_str}

        === Already Extracted Facts (Do NOT Repeat) ===
        {known_triples_str}
        
        === Target Fragments ===
        [Fragment A (Preceding)]:
        {chunk_curr}
        
        [Fragment B (Following)]:
        {chunk_next}
        
        === Task ===
        Based on the Global Context, analyze the logical gap between Fragment A and Fragment B.
        1. Identify *implicit* connections that bridge A and B.
        2. Ignore facts already listed in "Already Extracted Facts".
        3. Extract ONLY new bridging relationships.
        
        Output JSON: {{ "new_edges": [["EntityInA", "connects_to", "EntityInB"]] }}
        """
        
        try:
            response = self.extractor.chat([{"role": "user", "content": user_msg}], system_prompt=prompt_text, json_mode=True)
            data = json.loads(response)
            new_edges = data.get("new_edges", [])
            if new_edges:
                print(f"  [缝合] 检测到 {len(new_edges)} 条潜在关系 (Chunks {curr_id.split('_')[1]}-{next_id.split('_')[1]})")
            return new_edges
        except Exception as e:
            print(f"  [Refine Error] 逻辑缝合失败: {e}")
            return []

    # --- Phase 3 (Global Inference) ---
    def _infer_global_relationships(self, all_contents: List[Dict[str, Any]], prompt_text: str):
        if not all_contents: return
        print(f"\n⚡ 正在进行全局逻辑推导 (建立骨架连接)...")
        
        facts_lines = []
        for item in all_contents[:60]: 
            summ = item.get('summary', '')
            triples_str = "; ".join([f"{t[0]}-{t[1]}->{t[2]}" for t in item.get('triples', [])])
            if summ or triples_str:
                facts_lines.append(f"- {summ} | {triples_str}")

        facts_text = "\n".join(facts_lines)
        messages = [{"role": "user", "content": f"Fragmented Fact List:\n{facts_text}\n\nPlease infer global logic:"}]

        try:
            response = self.extractor.chat(messages, system_prompt=prompt_text)
            for line in response.strip().split('\n'):
                parts = line.split('|')
                if len(parts) == 3:
                    src, rel, tgt = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    if src and rel and tgt:
                        self._add_edge_safe(src, tgt, rel, source_id="global_inference", summary="Global Logic Inference")
        except Exception as e:
            print(f"全局推导失败: {e}")

    # --- Phase 4 (Backbone-Fragment Optimization) ---
    def _optimize_graph_structure(self, prompt_text: str, max_iterations: int = 10):
        """
        基于主干(Backbone)和碎片(Fragment)的图优化策略。
        1. 提取最大的连通分量作为 Backbone (ReadOnly Context)。
        2. 提取其余小的连通分量作为 Fragments (Target)。
        3. 让 LLM 决定 Fragments 是删除(Noise)、合并(Merge)还是连接(Connect)到 Backbone。
        """
        print(f"\n⚡ 启动主干-碎片优化 (Backbone-Centric Rewiring)...")
        
        for i in range(max_iterations):
            # 1. 提取连通分量
            components = list(nx.connected_components(self.graph))
            if len(components) <= 1:
                print("  ✅ 图谱已完全连通，结束优化。")
                break
            
            # 按节点数量排序，最大的为主干
            components.sort(key=len, reverse=True)
            backbone_nodes = components[0]
            fragment_nodes = set().union(*components[1:])
            
            num_fragments = len(components) - 1
            print(f"  [Iter {i+1}] 主干节点: {len(backbone_nodes)} | 碎片区域: {num_fragments} 个 | 待处理节点: {len(fragment_nodes)}")

            # 2. 准备上下文 (Backbone Edges)
            # 为了节省 Token，只取 Backbone 中度数较高的节点的边，或者随机采样
            backbone_subgraph = self.graph.subgraph(backbone_nodes)
            backbone_edges = []
            # 简单采样策略：取前 500 条边
            for u, v, d in list(backbone_subgraph.edges(data=True))[:500]:
                backbone_edges.append(f"{u} --[{d.get('relation','related')}]--> {v}")
            backbone_str = "\n".join(backbone_edges)

            # 3. 准备目标数据 (Fragment Edges)
            fragment_subgraph = self.graph.subgraph(fragment_nodes)
            fragment_edges = []
            # 碎片通常较小，尽可能全部提供
            for u, v, d in list(fragment_subgraph.edges(data=True))[:300]:
                fragment_edges.append(f"{u} --[{d.get('relation','related')}]--> {v}")
            
            # 如果碎片没有内部边（全是孤立点），则列出节点
            fragment_isolates = [n for n in fragment_nodes if self.graph.degree(n) == 0]
            
            fragment_str = "\n".join(fragment_edges)
            if fragment_isolates:
                fragment_str += "\nIsolated Nodes: " + ", ".join(fragment_isolates[:50])

            if not fragment_str.strip():
                # 只有孤立点且已被处理，或者没有边信息，尝试直接移除微小孤立点
                print("  -> 碎片区域无有效边信息，清理微小孤立点。")
                self.graph.remove_nodes_from(list(nx.isolates(self.graph)))
                continue

            # 4. 构造 Prompt (Updated constraints)
            user_msg = f"""
            === The Main Knowledge Backbone (Context, READ ONLY) ===
            This is the largest connected component representing the core logic.
            **STRICT RULE: YOU CANNOT DELETE OR RENAME NODES IN THE BACKBONE.**
            {backbone_str}

            === Disconnected Fragments (Target for Optimization) ===
            These are isolated components/edges. Analyze them against the Backbone.
            {fragment_str}

            === Task ===
            For each Entity or Edge in the Fragments, decide its fate:
            1. **DELETE**: If it looks like noise, typos, or irrelevant data.
            2. **MERGE**: If a fragment entity is a synonym of a Backbone entity. (e.g., "AI" -> "Artificial Intelligence").
               *IMPORTANT*: 'source' must be from Fragment, 'target' must be from Backbone.
            3. **CONNECT**: If the fragment represents valid logic but is missing a link to the Backbone. Create a NEW edge.
            4. **IGNORE**: If it is valid but distinct topic, or you are unsure. DO NOT hallucinate connections.

            === Constraints ===
            1. **Max Output**: Return AT MOST 20 operations to prevent response truncation. Prioritize the most high-confidence changes.
            2. **Preserve Backbone**: Do not output operations that modify the Backbone structure itself (only attach to it).

            === Output Format (JSON) ===
            {{
                "operations": [
                    {{ "type": "DELETE", "nodes": ["noise_node_A"] }},
                    {{ "type": "MERGE", "source": "fragment_node_B", "target": "backbone_node_C" }},
                    {{ "type": "CONNECT", "source": "fragment_node_D", "target": "backbone_node_E", "relation": "rel_name" }}
                ]
            }}
            """

            try:
                # 使用 resolve_prompt 或默认
                system_p = prompt_text if prompt_text else "You are a Knowledge Graph optimizor."
                response = self.extractor.chat([{"role": "user", "content": user_msg}], system_prompt=system_p, json_mode=True)
                data = json.loads(response)
                ops = data.get("operations", [])
                
                if not ops:
                    print("  -> LLM 未提出修改建议。")
                    if i > 2: break 
                    continue

                changed = False
                for op in ops:
                    op_type = op.get("type", "").upper()
                    
                    if op_type == "DELETE":
                        nodes_to_del = op.get("nodes", [])
                        for n in nodes_to_del:
                            # 额外保护：确保只删除 Fragment 中的节点，不删除 Backbone
                            if n in backbone_nodes:
                                print(f"    [SKIP] 试图删除主干节点 {n}，操作已拦截。")
                                continue
                            if self.graph.has_node(n):
                                self.graph.remove_node(n)
                                changed = True
                        if nodes_to_del: print(f"    [DEL] 删除建议: {nodes_to_del}")

                    elif op_type == "MERGE":
                        src = op.get("source")
                        tgt = op.get("target")
                        # 额外保护：确保 src 是 Fragment, tgt 是 Backbone (或至少在图中)
                        if src and tgt and self.graph.has_node(src) and self.graph.has_node(tgt):
                            if src in backbone_nodes and tgt not in backbone_nodes:
                                # 如果 LLM 搞反了方向，且 tgt 是 fragment，我们尝试反转逻辑？
                                # 或者严格拒绝。这里选择严格拒绝以防止破坏主干。
                                print(f"    [SKIP] 拒绝将主干节点 {src} 合并入 {tgt}。")
                                continue
                                
                            # 将 src 的连接移到 tgt
                            for nbr in list(self.graph.neighbors(src)):
                                if nbr == tgt: continue
                                edge_data = self.graph[src][nbr]
                                self._add_edge_safe(tgt, nbr, edge_data.get('relation','merged'), "merge_op", "Merged synonym")
                            self.graph.remove_node(src)
                            changed = True
                            print(f"    [MERGE] 合并: {src} -> {tgt}")

                    elif op_type == "CONNECT":
                        src = op.get("source")
                        tgt = op.get("target")
                        rel = op.get("relation", "related")
                        if src and tgt and self.graph.has_node(src) and self.graph.has_node(tgt):
                            self._add_edge_safe(src, tgt, rel, "connect_op", "Logic Gap Filled")
                            changed = True
                            print(f"    [CONNECT] 连通: {src} --[{rel}]--> {tgt}")

                if not changed:
                    print("  -> 建议操作未引起图谱实质变化。")
                    break

            except Exception as e:
                print(f"  [Iter {i+1} Error] 优化出错: {e}")
                break

        # 最后清理所有仍然孤立的单点（通常是操作后遗留的）
        final_isolates = list(nx.isolates(self.graph))
        if final_isolates:
            self.graph.remove_nodes_from(final_isolates)
            print(f"  [Cleanup] 最终清理 {len(final_isolates)} 个孤立节点。")

    # --- 主流程 ---
    def build_graph(self, file_path: str, 
                    extract_prompt: str = "common_pmp.md",
                    refine_prompt: str = "refine_pmp.md",
                    resolve_prompt: str = "resolve_pmp.md",
                    infer_prompt: str = "infer_pmp.md"):
        
        p_extract = self._load_prompt_content(extract_prompt, default_content="Extract triples and summary JSON.")
        p_refine = self._load_prompt_content(refine_prompt, default_content="Find logic between two chunks JSON.")
        p_resolve = self._load_prompt_content(resolve_prompt, default_content="Backbone-Fragment Optimization JSON.")
        p_infer = self._load_prompt_content(infer_prompt, default_content="Infer global logic Entity|Rel|Entity.")

        try:
            text = self._read_text_file(file_path)
        except Exception as e:
            print(f"文件读取失败: {e}")
            return

        print(f"正在构建图谱: {file_path}")
        splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
        chunks = splitter.split_text(text)
        if not chunks: return
        
        base_name = os.path.basename(file_path)
        chunk_ids = [f"{base_name}_{i}_{str(uuid.uuid4())[:8]}" for i in range(len(chunks))]
        
        print(f"正在向量化 {len(chunks)} 个片段...")
        try:
            embeddings = self.encoder.encode(chunks, normalize_embeddings=True).tolist()
            self.chunk_collection.add(
                ids=chunk_ids,
                documents=chunks,
                metadatas=[{"source": file_path, "index": i} for i in range(len(chunks))],
                embeddings=embeddings
            )
        except Exception as e:
            print(f"向量化失败: {e}")

        # Phase 1: Concurrent Extraction
        print(f"Phase 1: 启动基础提取 (Tasks: {len(chunks)})...")
        file_contents = [None] * len(chunks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_index = {
                executor.submit(self._extract_chunk_content, chunk, p_extract): i 
                for i, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                i = future_to_index[future]
                file_contents[i] = future.result() or {}

        print("写入初步图谱数据...")
        all_summaries = [] 
        for i, data in enumerate(file_contents):
            chunk_id = chunk_ids[i]
            summary = data.get("summary", "No Summary")
            all_summaries.append(summary)
            for item in data.get("triples", []):
                if len(item) < 3: continue
                src, rel, tgt = item[:3]  # 只取前3个，忽略多余的
                self._add_edge_safe(src, tgt, rel, source_id=chunk_id, summary=summary)

        # Phase 2: Concurrent Refinement
        if len(chunks) > 1:
            print(f"Phase 2: 并发逻辑缝合 (Tasks: {len(chunks)-1})...")
            refine_results = [[] for _ in range(len(chunks) - 1)]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                future_to_index = {}
                for i in range(len(chunks) - 1):
                    current_triples = file_contents[i].get("triples", [])
                    next_triples = file_contents[i+1].get("triples", [])
                    known_triples = current_triples + next_triples
                    
                    future = executor.submit(
                        self._refine_adjacent_logic,
                        chunk_curr=chunks[i], 
                        chunk_next=chunks[i+1], 
                        curr_id=chunk_ids[i], 
                        next_id=chunk_ids[i+1], 
                        prompt_text=p_refine,
                        global_summaries=all_summaries, 
                        known_triples=known_triples     
                    )
                    future_to_index[future] = i
                
                for future in concurrent.futures.as_completed(future_to_index):
                    idx = future_to_index[future]
                    try:
                        new_edges = future.result()
                        refine_results[idx] = new_edges
                    except Exception as e:
                        print(f"Task {idx} failed: {e}")

            print("正在整合缝合结果...")
            count_new = 0
            for i, new_edges in enumerate(refine_results):
                if not new_edges: continue
                curr_id = chunk_ids[i]
                next_id = chunk_ids[i+1]
                for edge in new_edges:
                    if not isinstance(edge, list) or len(edge) < 3: continue
                    src, rel, tgt = edge[:3]
                    self._add_edge_safe(src, tgt, rel, source_id=f"link_{curr_id}_{next_id}", summary="Adjacent Logic Inference")
                    count_new += 1
            print(f"✨ 逻辑缝合完成，新增 {count_new} 条跨块逻辑。")

        # Phase 3: Global Inference (Backbone)
        print(f"Phase 3: 宏观逻辑推导...")
        valid_contents = [c for c in file_contents if c]
        self._infer_global_relationships(valid_contents, p_infer)

        # Phase 4: Backbone-Fragment Optimization
        print(f"Phase 4: 主干-碎片实体对齐优化...")
        self._optimize_graph_structure(p_resolve, max_iterations=10)

        # Final Indexing
        final_nodes = list(self.graph.nodes())
        if final_nodes:
            print(f"正在更新节点索引 ({len(final_nodes)} nodes)...")
            try:
                node_embeddings = self.encoder.encode(final_nodes, normalize_embeddings=True).tolist()
                self.node_collection.upsert(
                    ids=[f"node_{n}" for n in final_nodes],
                    documents=final_nodes,
                    embeddings=node_embeddings
                )
            except Exception as e:
                print(f"节点索引更新失败: {e}")

        self._save_graph()
        print(f"✨ 图谱构建完成。Nodes: {self.graph.number_of_nodes()}, Edges: {self.graph.number_of_edges()}")

    def search(self, query: str, top_k: int = 3) -> str:
        print(f"\n[Search] 正在检索: {query}")
        
        query_vec = self.encoder.encode([query], normalize_embeddings=True).tolist()
        node_results = self.node_collection.query(query_embeddings=query_vec, n_results=5)
        found_nodes = node_results['documents'][0] if node_results['documents'] else []
        
        if not found_nodes:
            return "No related entities found."
            
        print(f"  -> 命中实体: {found_nodes}")

        logic_lines = []
        visited_edges = set()

        for node in found_nodes:
            if self.graph.has_node(node):
                edges = self.graph.edges(node, data=True)
                for u, v, data in edges:
                    edge_sig = tuple(sorted([u, v]))
                    if edge_sig in visited_edges: continue
                    
                    rel = data.get('relation', 'related_to')
                    evidence_list = data.get('evidence', [])
                    summaries = list(set([e['summary'] for e in evidence_list]))[:2] 
                    summary_text = f" (Context: {'; '.join(summaries)})" if summaries else ""
                    
                    logic_lines.append(f"- {u} --[{rel}]--> {v}{summary_text}")
                    visited_edges.add(edge_sig)

        chunk_results = self.chunk_collection.query(
            query_embeddings=query_vec,
            n_results=top_k
        )
        
        top_chunks = chunk_results['documents'][0] if chunk_results['documents'] else []
        top_ids = chunk_results['ids'][0] if chunk_results['ids'] else []
        
        source_text_blocks = []
        for i, (txt, cid) in enumerate(zip(top_chunks, top_ids)):
            source_text_blocks.append(f"Source Fragment {i+1} (ID: {cid}):\n{txt}")

        final_context = "### Knowledge Graph Paths\n" + "\n".join(logic_lines) + "\n\n"
        final_context += "### Source References\n" + "\n".join(source_text_blocks)
        
        return final_context

    def clear_db(self):
        try:
            self.client.delete_collection("graph_nodes")
            self.client.delete_collection("graph_chunks")
        except:
            pass
        
        self.node_collection = self.client.get_or_create_collection(name="graph_nodes", metadata={"hnsw:space": "cosine"})
        self.chunk_collection = self.client.get_or_create_collection(name="graph_chunks", metadata={"hnsw:space": "cosine"})
        
        self.graph.clear()
        self._save_graph()
        print("数据库已重置。")
    def reload_db(self, new_persist_dir: str):
        """
        动态切换 GraphRAG 的持久化存储路径 (用于项目切换)
        """
        print(f"🔄 [GraphRAG] 正在切换数据库路径至: {new_persist_dir}")
        
        # 1. 确保目录存在
        os.makedirs(new_persist_dir, exist_ok=True)

        # 2. 重新连接 ChromaDB
        # 直接覆盖 self.client 实例即可指向新路径
        self.client = chromadb.PersistentClient(path=new_persist_dir)
        
        # 3. 重新绑定集合 (Collection)
        # 指针指向新 DB 中的集合
        self.node_collection = self.client.get_or_create_collection(
            name="graph_nodes",
            metadata={"hnsw:space": "cosine"}
        )

        self.chunk_collection = self.client.get_or_create_collection(
            name="graph_chunks",
            metadata={"hnsw:space": "cosine"}
        )
        
        # 4. 重新加载 NetworkX 图谱结构
        self.graph_path = os.path.join(new_persist_dir, "knowledge_graph.json")
        self.graph = nx.Graph() # 先清空内存中的旧图
        self._load_graph()      # 从新路径加载 (若无文件则为空图)
        
        print(f"✅ [GraphRAG] 切换完成。当前节点数: {self.graph.number_of_nodes()}")

if __name__ == "__main__":
    kg = LightGraphRAG()
    
    text = """
    # 模块A：数据采集
    采集器从网络抓取数据，并存入MongoDB中。
    
    # 模块B：数据预处理
    Mongo数据库中的数据被读取后，进行清洗和去重。
    
    # 模块C：特征工程
    清洗后的数据被送入特征提取器，生成向量。
    """
    
    with open("test_v3.txt", "w", encoding='utf-8') as f: f.write(text)
    kg.clear_db()
    kg.build_graph("test_v3.txt")
    print("\n--- 测试搜索 ---")
    print(kg.search("数据库"))