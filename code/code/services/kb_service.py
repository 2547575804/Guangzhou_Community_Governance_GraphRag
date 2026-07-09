"""知识库检索服务 - 基于 TF-IDF 的文本检索"""

from dataclasses import dataclass

import jieba
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config


@dataclass
class KBDocument:
    doc_id: str
    source_type: str
    title: str
    content: str
    metadata: dict

    def to_text(self) -> str:
        parts = [self.title, self.content]
        for v in self.metadata.values():
            if v and str(v) != "nan":
                parts.append(str(v))
        return " ".join(parts)


class KnowledgeBaseService:
    def __init__(self):
        self.documents: list[KBDocument] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.tfidf_matrix = None
        self._load_documents()
        self._build_index()

    def _tokenize(self, text: str) -> str:
        words = jieba.cut(text)
        return " ".join(w for w in words if w.strip())

    def _load_documents(self):
        loaders = [
            (config.WORKORDER_CSV, "12345热线", "case_id", "title", "content",
             ["department", "process", "result", "conflict_type", "city"]),
            (config.COURTCASE_CSV, "法律文书", "document_id", "case_number", "key_facts",
             ["dispute_type", "court_opinion", "judgment_result", "applicable_law", "city"]),
            (config.NEWS_CSV, "新闻报道", "news_id", "title", "content",
             ["conflict_type", "solution", "departments", "media", "city"]),
        ]

        for csv_path, source_type, id_col, title_col, content_col, meta_cols in loaders:
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path, encoding="utf-8")
            for _, row in df.iterrows():
                meta = {col: str(row.get(col, "")) for col in meta_cols}
                self.documents.append(
                    KBDocument(
                        doc_id=str(row[id_col]),
                        source_type=source_type,
                        title=str(row.get(title_col, "")),
                        content=str(row.get(content_col, "")),
                        metadata=meta,
                    )
                )

    def _build_index(self):
        if not self.documents:
            return
        corpus = [self._tokenize(doc.to_text()) for doc in self.documents]
        self.vectorizer = TfidfVectorizer(max_features=8000)
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        top_k = top_k or config.KB_TOP_K
        if not self.documents or self.tfidf_matrix is None:
            return []

        query_vec = self.vectorizer.transform([self._tokenize(query)])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        ranked = scores.argsort()[::-1][:top_k]

        results = []
        for idx in ranked:
            if scores[idx] < 0.01:
                continue
            doc = self.documents[idx]
            results.append({
                "doc_id": doc.doc_id,
                "source_type": doc.source_type,
                "title": doc.title,
                "content": doc.content[:500],
                "metadata": doc.metadata,
                "score": float(scores[idx]),
            })
        return results

    def format_for_llm(self, results: list[dict]) -> str:
        if not results:
            return "未检索到相关知识库文档。"
        lines = ["【知识库检索结果】"]
        for i, r in enumerate(results, 1):
            lines.append(
                f"{i}. [{r['source_type']}] {r['title']}\n"
                f"   内容摘要: {r['content']}\n"
                f"   元数据: {r['metadata']}\n"
                f"   相关度: {r['score']:.3f}"
            )
        return "\n".join(lines)

    def extract_keywords(self, query: str) -> list[str]:
        words = jieba.cut(query)
        stop = {"的", "了", "是", "在", "有", "和", "与", "什么", "如何", "怎么", "哪些", "吗", "呢"}
        return [w for w in words if len(w) > 1 and w not in stop]
