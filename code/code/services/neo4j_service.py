"""Neo4j 图谱查询服务"""

from neo4j import GraphDatabase

import config
from services.llm_service import LLMService


class Neo4jService:
    def __init__(self, llm: LLMService | None = None):
        self.driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        )
        self.llm = llm or LLMService()

    def close(self):
        self.driver.close()

    def _run(self, query: str, params: dict | None = None) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def is_connected(self) -> bool:
        try:
            self._run("RETURN 1 AS ok")
            return True
        except Exception:
            return False

    def search_by_keyword(self, keywords: list[str], limit: int = 10) -> list[dict]:
        """关键词模糊检索图谱节点"""
        if not keywords:
            return []

        results = []
        seen = set()
        queries = [
            (
                """
                MATCH (w:WorkOrder)
                WHERE w.title CONTAINS $kw OR w.content CONTAINS $kw
                   OR w.conflict_type CONTAINS $kw
                RETURN w.id AS id, 'WorkOrder' AS type, w.title AS title,
                       w.content AS content, w.conflict_type AS category
                LIMIT $limit
                """,
            ),
            (
                """
                MATCH (c:CourtCase)
                WHERE c.case_number CONTAINS $kw OR c.key_facts CONTAINS $kw
                   OR c.dispute_type CONTAINS $kw
                RETURN c.id AS id, 'CourtCase' AS type, c.case_number AS title,
                       c.key_facts AS content, c.dispute_type AS category
                LIMIT $limit
                """,
            ),
            (
                """
                MATCH (n:News)
                WHERE n.title CONTAINS $kw OR n.content CONTAINS $kw
                   OR n.conflict_type CONTAINS $kw
                RETURN n.id AS id, 'News' AS type, n.title AS title,
                       n.content AS content, n.conflict_type AS category
                LIMIT $limit
                """,
            ),
        ]

        for kw in keywords[:5]:
            for query in queries:
                try:
                    rows = self._run(query, {"kw": kw, "limit": limit})
                    for row in rows:
                        key = (row.get("id"), row.get("type"))
                        if key not in seen:
                            seen.add(key)
                            results.append(row)
                except Exception:
                    continue

        return results[:limit]

    def query_relations(self, keywords: list[str], limit: int = 10) -> list[dict]:
        """关系推理查询：部门-案例、冲突类型-案例、法律-案例等"""
        results = []
        for kw in keywords[:3]:
            queries = [
                (
                    "部门关联",
                    """
                    MATCH (d:Department)
                    WHERE d.name CONTAINS $kw
                    OPTIONAL MATCH (d)<-[:HANDLED_BY]-(w:WorkOrder)
                    OPTIONAL MATCH (d)<-[:INVOLVES]-(n:News)
                    RETURN d.name AS entity, collect(DISTINCT w.title)[..3] AS workorders,
                           collect(DISTINCT n.title)[..3] AS news
                    LIMIT $limit
                    """,
                ),
                (
                    "冲突类型关联",
                    """
                    MATCH (t:ConflictType)
                    WHERE t.name CONTAINS $kw
                    OPTIONAL MATCH (t)<-[:HAS_CONFLICT_TYPE]-(w:WorkOrder)
                    OPTIONAL MATCH (t)<-[:HAS_CONFLICT_TYPE]-(n:News)
                    RETURN t.name AS entity, collect(DISTINCT w.title)[..3] AS workorders,
                           collect(DISTINCT n.title)[..3] AS news
                    LIMIT $limit
                    """,
                ),
                (
                    "法律关联",
                    """
                    MATCH (l:Law)
                    WHERE l.name CONTAINS $kw
                    OPTIONAL MATCH (l)<-[:APPLIES_LAW]-(c:CourtCase)
                    RETURN l.name AS entity, collect(DISTINCT c.case_number)[..3] AS court_cases
                    LIMIT $limit
                    """,
                ),
                (
                    "区关联",
                    """
                    MATCH (d:District)
                    WHERE d.name CONTAINS $kw
                    OPTIONAL MATCH (d)<-[:LOCATED_IN]-(w:WorkOrder)
                    OPTIONAL MATCH (d)<-[:LOCATED_IN]-(n:News)
                    OPTIONAL MATCH (d)<-[:LOCATED_IN]-(cc:CourtCase)
                    RETURN d.name AS entity, collect(DISTINCT w.title)[..3] AS workorders,
                           collect(DISTINCT n.title)[..3] AS news,
                           collect(DISTINCT cc.case_number)[..3] AS court_cases
                    LIMIT $limit
                    """,
                ),
                (
                    "跨域关联",
                    """
                    MATCH (w:WorkOrder)-[r:RELATED_NEWS|RELATED_COURTCASE]->(target)
                    WHERE w.title CONTAINS $kw OR w.content CONTAINS $kw
                    RETURN w.title AS workorder, type(r) AS relation,
                           labels(target)[0] AS target_type,
                           coalesce(target.title, target.case_number) AS target_title
                    LIMIT $limit
                    """,
                ),
            ]
            for rel_type, cypher in queries:
                try:
                    rows = self._run(cypher, {"kw": kw, "limit": limit})
                    for row in rows:
                        row["relation_type"] = rel_type
                        results.append(row)
                except Exception:
                    continue
        return results[:limit * 2]

    def generate_cypher_and_query(self, question: str) -> tuple[str, list[dict]]:
        """使用 LLM 生成 Cypher 并执行（安全白名单）"""
        prompt = f"""你是 Neo4j Cypher 专家。根据用户问题生成只读 Cypher 查询。
数据库模式：
- WorkOrder(id,title,content,conflict_type) -[:LOCATED_IN]-> City
- WorkOrder -[:LOCATED_IN]-> District
- WorkOrder -[:HANDLED_BY]-> Department
- WorkOrder -[:HAS_CONFLICT_TYPE]-> ConflictType
- CourtCase(id,case_number,dispute_type,key_facts) -[:LOCATED_IN]-> City
- CourtCase -[:LOCATED_IN]-> District
- CourtCase -[:APPLIES_LAW]-> Law
- News(id,title,content,conflict_type) -[:LOCATED_IN]-> City
- News -[:LOCATED_IN]-> District
- News -[:REPORTED_BY]-> Media
- News -[:INVOLVES]-> Department
- District -[:BELONGS_TO]-> City
- WorkOrder -[:RELATED_NEWS]-> News
- WorkOrder -[:RELATED_COURTCASE]-> CourtCase

用户问题：{question}

只返回 JSON：{{"cypher": "MATCH ... RETURN ... LIMIT 10"}}。
禁止 DELETE/CREATE/MERGE/SET/DETACH，只允许 MATCH/RETURN/WHERE/OPTIONAL MATCH。
"""
        response = self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1)
        data = self.llm.extract_json(response)
        cypher = data.get("cypher", "")

        if not cypher or not self._is_safe_cypher(cypher):
            return "", []

        try:
            return cypher, self._run(cypher)
        except Exception:
            return cypher, []

    def _is_safe_cypher(self, cypher: str) -> bool:
        upper = cypher.upper()
        forbidden = ["DELETE", "CREATE", "MERGE", "SET ", "DETACH", "DROP", "REMOVE"]
        return not any(f in upper for f in forbidden)

    def reasoning_search(self, question: str, keywords: list[str]) -> dict:
        """综合图谱推理检索"""
        node_results = self.search_by_keyword(keywords)
        relation_results = self.query_relations(keywords)
        cypher, cypher_results = self.generate_cypher_and_query(question)

        return {
            "node_results": node_results,
            "relation_results": relation_results,
            "cypher": cypher,
            "cypher_results": cypher_results,
        }

    def format_for_llm(self, graph_data: dict) -> str:
        lines = ["【图谱推理检索结果】"]

        if graph_data.get("node_results"):
            lines.append("\n▶ 节点匹配:")
            for i, r in enumerate(graph_data["node_results"][:5], 1):
                lines.append(
                    f"  {i}. [{r.get('type')}] {r.get('title', '')} "
                    f"({r.get('category', '')})\n     {str(r.get('content', ''))[:200]}"
                )

        if graph_data.get("relation_results"):
            lines.append("\n▶ 关系推理:")
            for i, r in enumerate(graph_data["relation_results"][:5], 1):
                lines.append(f"  {i}. [{r.get('relation_type')}] {r}")

        if graph_data.get("cypher"):
            lines.append(f"\n▶ 生成 Cypher: {graph_data['cypher']}")
            if graph_data.get("cypher_results"):
                lines.append(f"▶ Cypher 结果: {graph_data['cypher_results'][:5]}")

        if len(lines) == 1:
            lines.append("未检索到相关图谱信息。")

        return "\n".join(lines)
