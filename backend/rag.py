import os
import chromadb
import torch
import json
import uuid
from typing import List, Dict
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

class LocalKnowledgeBase:
    def __init__(self, persist_dir: str = "./.local_rag_db"):
        """
        初始化本地知识库
        """
        print("--- 初始化 RAG 引擎 (支持 Q&A Key-Value 模式) ---")
        
        # 1. 显存够大，直接上 BAAI/bge-m3 (约 2.5GB)，中英文效果顶级
        # 如果下载慢，请提前下载好模型文件夹，把下面的字符串换成路径
        model_name = "BAAI/bge-m3"
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"正在加载 Embedding 模型 ({model_name}) 到 {device}...")
        
        self.encoder = SentenceTransformer(model_name, device=device)
        
        # 2. 初始化本地向量数据库 (ChromaDB)
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # 获取或创建集合
        # hnsw:space='cosine' 表示使用余弦相似度，最适合文本匹配
        self.collection = self.client.get_or_create_collection(
            name="general_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        print("引擎就绪。")

    def add_markdown(self, file_path: str):
        """
        核心功能1：读取 MD 文件 -> 智能切分 -> 向量化入库
        """
        if not os.path.exists(file_path):
            # 容错处理：如果文件不存在，仅打印警告，不中断程序
            print(f"警告: 文件未找到: {file_path}")
            return

        print(f"正在处理规则文档: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        # --- 第一步：按 Markdown 标题层级切分 (保留结构) ---
        # 这样能保证检索到“代码规则”时，知道它是属于哪个大类的
        headers = [
            ("#", "H1"),
            ("##", "H2"),
            ("###", "H3"),
        ]
        md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
        header_splits = md_splitter.split_text(text)

        # --- 第二步：按字符长度二次切分 (防止单段过长) ---
        # bge-m3 支持 8192 长度，但为了检索精准，建议切细一点，比如 512 或 1024
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=100, # 重叠一部分，防止断章取义
            separators=["\n\n", "\n", "。", "！", "!", ""]
        )
        final_splits = text_splitter.split_documents(header_splits)

        # --- 第三步：批量向量化并存储 ---
        documents = []
        metadatas = []
        ids = []

        base_name = os.path.basename(file_path)
        
        for idx, doc in enumerate(final_splits):
            documents.append(doc.page_content)
            # 把文件来源记录在元数据里
            meta = doc.metadata.copy()
            meta["source"] = base_name
            meta["type"] = "doc_fragment"
            metadatas.append(meta)
            ids.append(f"{base_name}_part_{idx}")

        if documents:
            # normalize_embeddings=True 对余弦相似度检索非常重要
            embeddings = self.encoder.encode(documents, normalize_embeddings=True).tolist()
            
            self.collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            print(f"成功入库 {len(documents)} 个片段。")

    def add_qa_mistakes(self, json_path: str):
        """
        核心功能2 (升级版)：Key-Value RAG 模式
        读取 JSON 错题集 -> Embedding(Q) -> Store(A)
        目的：当 Query 匹配到报错信息(Q)时，直接返回修复策略(A)，而非无关文本。
        """
        if not os.path.exists(json_path):
            print(f"提示: 错题集文件 {json_path} 不存在，跳过加载。")
            return

        print(f"正在加载错题经验: {json_path}")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                print("错题集格式错误: 根节点应为 List")
                return

            ids = []
            documents = []  # 存 Answer (修复策略)
            embeddings = [] # 存 Question (报错信息) 的向量
            metadatas = []

            # 批量处理，减少编码次数
            questions = []
            
            for idx, item in enumerate(data):
                q = item.get("q", "")
                a = item.get("a", "")
                
                if not q or not a:
                    continue
                
                questions.append(q)
                documents.append(a)
                # 记录原始问题在 metadata 中，方便回溯
                metadatas.append({
                    "source": "mistakes_json", 
                    "type": "qa_experience",
                    "original_q": q
                })
                ids.append(f"mistake_{idx}_{str(uuid.uuid4())[:8]}")

            if questions:
                # 核心：向量化的是 Question (报错特征)
                embeddings = self.encoder.encode(questions, normalize_embeddings=True).tolist()
                
                self.collection.add(
                    ids=ids,
                    documents=documents, # 检索返回的内容是 Answer
                    embeddings=embeddings, # 检索匹配的依据是 Question
                    metadatas=metadatas
                )
                print(f"成功加载 {len(documents)} 条错题经验。")
                
        except Exception as e:
            print(f"加载错题集失败: {str(e)}")

    def add_single_qa(self, q: str, a: str, source: str = "runtime_learning"):
        """
        运行时动态添加单条经验 (Experience Replay)
        """
        try:
            embedding = self.encoder.encode([q], normalize_embeddings=True).tolist()
            
            unique_id = f"runtime_mistake_{str(uuid.uuid4())[:8]}"
            
            self.collection.add(
                ids=[unique_id],
                documents=[a],
                embeddings=embedding,
                metadatas=[{"source": source, "type": "qa_experience", "original_q": q}]
            )
            print(f"已动态记录经验: {q[:30]}...")
        except Exception as e:
            print(f"动态记录经验失败: {e}")

    def search(self, query: str, top_k: int = 3) -> List[str]:
        """
        [修正版] 智能去重检索
        修正点：针对 QA 数据，基于 Question (original_q) 去重，防止误删不同错误但修复方案相同的条目。
        """
        # 1. 向量化
        query_vec = self.encoder.encode([query], normalize_embeddings=True).tolist()
        
        # 2. 过采样检索
        results = self.collection.query(
            query_embeddings=query_vec,
            n_results=top_k * 3 
        )
        
        found_docs = results['documents'][0] if results['documents'] else []
        found_ids = results['ids'][0] if results['ids'] else []
        found_metadatas = results['metadatas'][0] if results['metadatas'] else []
        
        unique_docs = []
        seen_hashes = set()
        ids_to_delete = [] 

        # 3. 智能去重遍历
        for i in range(len(found_docs)):
            doc = found_docs[i]
            doc_id = found_ids[i]
            meta = found_metadatas[i] if found_metadatas else {}
            
            # --- 核心修改：判重指纹计算 ---
            if meta and "original_q" in meta:
                # 如果是 QA 错题/经验，必须基于“问题(Q)”来判重！
                # 只有当“问题”一模一样时，才视为冗余数据。
                unique_key = meta["original_q"].strip()
            else:
                # 如果是普通文档，则基于“内容”判重
                unique_key = doc.strip()
                
            # 计算指纹
            import hashlib
            item_hash = hashlib.md5(unique_key.encode('utf-8')).hexdigest()
            
            if item_hash not in seen_hashes:
                unique_docs.append(doc)
                seen_hashes.add(item_hash)
            else:
                # 指纹重复，说明库里有冗余的 Q (对于错题) 或冗余的文本 (对于文档)
                ids_to_delete.append(doc_id)
            
            if len(unique_docs) >= top_k and len(ids_to_delete) == 0:
                break

        # 4. 执行清理
        if ids_to_delete:
            # print(f"🧹 [RAG清理] 移除 {len(ids_to_delete)} 条冗余数据...") # 减少日志干扰
            try:
                self.collection.delete(ids=ids_to_delete)
            except: pass

        return unique_docs[:top_k]
    
    def search_score(self, query: str, top_k: int = 3, score_threshold: float = 0.4) -> List[str]:
        """
        [修正版] 智能去重 + 阈值截断检索
        :param score_threshold: 相似度阈值 (0-1)，低于此值的经验将被忽略。建议 0.35 ~ 0.5 之间。
        """
        # 1. 向量化
        query_vec = self.encoder.encode([query], normalize_embeddings=True).tolist()
        
        # 2. 过采样检索 (为了在过滤和去重后还能凑够 top_k，这里多取一些)
        results = self.collection.query(
            query_embeddings=query_vec,
            n_results=top_k * 5, 
            # 必须显式请求 distances
            include=["documents", "metadatas", "distances"] 
        )
        
        found_docs = results['documents'][0] if results['documents'] else []
        found_ids = results['ids'][0] if results['ids'] else []
        found_metadatas = results['metadatas'][0] if results['metadatas'] else []
        # 获取距离列表
        found_distances = results['distances'][0] if results['distances'] else []
        
        unique_docs = []
        seen_hashes = set()
        ids_to_delete = [] 

        # 3. 智能去重 + 阈值过滤遍历
        for i in range(len(found_docs)):
            doc = found_docs[i]
            doc_id = found_ids[i]
            meta = found_metadatas[i] if found_metadatas else {}
            dist = found_distances[i]
            
            # --- [核心修改] 相似度阈值判断 ---
            # Chroma 的 Cosine Distance 范围是 0~2 (0表示完全一样)
            # 相似度 = 1 - 距离
            similarity = 1.0 - dist
            
            if similarity < score_threshold:
                # 因为 Chroma 返回的结果是按相似度排序的 (距离由小到大)
                # 如果当前这条已经低于阈值，后面的肯定更低，直接结束循环
                # print(f"   [RAG过滤] 相似度 {similarity:.4f} 低于阈值 {score_threshold}，截断停止。")
                break

            # --- 下面是原本的去重逻辑 ---
            if meta and "original_q" in meta:
                unique_key = meta["original_q"].strip()
            else:
                unique_key = doc.strip()
                
            import hashlib
            item_hash = hashlib.md5(unique_key.encode('utf-8')).hexdigest()
            
            if item_hash not in seen_hashes:
                unique_docs.append(doc)
                seen_hashes.add(item_hash)
            else:
                ids_to_delete.append(doc_id)
            
            # 凑够了就停
            if len(unique_docs) >= top_k:
                break

        # 4. 执行清理 (保持不变)
        if ids_to_delete:
            try:
                self.collection.delete(ids=ids_to_delete)
            except: pass

        return unique_docs