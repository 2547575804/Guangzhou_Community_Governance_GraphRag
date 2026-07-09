"""
广州市社区治理案例知识图谱构建脚本
从 process_data 导入节点与关系至 Neo4j
"""

import re
import sys
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

import config

GUANGZHOU_DISTRICTS = {
    "天河区", "海珠区", "白云区", "番禺区", "黄埔区",
    "花都区", "南沙区", "荔湾区", "越秀区", "增城区", "从化区"
}


def extract_laws(text: str) -> list[str]:
    if not text or pd.isna(text):
        return []
    return list(dict.fromkeys(re.findall(r"《[^》]+》", str(text))))


def split_departments(text: str) -> list[str]:
    if not text or pd.isna(text):
        return []
    parts = re.split(r"[、,，;；]", str(text))
    return [p.strip() for p in parts if p.strip()]


def extract_districts(text: str) -> list[str]:
    if not text or pd.isna(text):
        return []
    text = str(text)
    found = []
    for district in GUANGZHOU_DISTRICTS:
        if district in text:
            found.append(district)
    return list(dict.fromkeys(found))


class KnowledgeGraphBuilder:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def clear_database(self):
        print("清空现有图谱数据...")
        self.run_query("MATCH (n) DETACH DELETE n")

    def create_constraints(self):
        print("创建约束与索引...")
        constraints = [
            "CREATE CONSTRAINT workorder_id IF NOT EXISTS FOR (w:WorkOrder) REQUIRE w.id IS UNIQUE",
            "CREATE CONSTRAINT courtcase_id IF NOT EXISTS FOR (c:CourtCase) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT news_id IF NOT EXISTS FOR (n:News) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT city_name IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT district_name IF NOT EXISTS FOR (d:District) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT dept_name IF NOT EXISTS FOR (d:Department) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT media_name IF NOT EXISTS FOR (m:Media) REQUIRE m.name IS UNIQUE",
            "CREATE CONSTRAINT law_name IF NOT EXISTS FOR (l:Law) REQUIRE l.name IS UNIQUE",
            "CREATE CONSTRAINT conflict_name IF NOT EXISTS FOR (t:ConflictType) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT dispute_name IF NOT EXISTS FOR (t:DisputeType) REQUIRE t.name IS UNIQUE",
        ]
        for cypher in constraints:
            try:
                self.run_query(cypher)
            except Exception as e:
                print(f"  约束可能已存在: {e}")

    def import_workorders(self, csv_path: Path):
        print(f"导入 12345 热线案例: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8")
        for _, row in df.iterrows():
            case_id = str(row["case_id"])
            city = str(row.get("city", "")).strip()
            dept = str(row.get("department", "")).strip()
            conflict = str(row.get("conflict_type", "")).strip()

            content_text = str(row.get("content", ""))
            title_text = str(row.get("title", ""))
            districts = extract_districts(f"{title_text} {content_text} {dept}")

            self.run_query(
                """
                MERGE (w:WorkOrder {id: $id})
                SET w.title = $title,
                    w.content = $content,
                    w.process = $process,
                    w.result = $result,
                    w.conflict_type = $conflict_type,
                    w.publish_date = $publish_date,
                    w.source_url = $source_url,
                    w.data_source = '12345热线'
                """,
                {
                    "id": case_id,
                    "title": title_text,
                    "content": content_text,
                    "process": str(row.get("process", "")),
                    "result": str(row.get("result", "")),
                    "conflict_type": conflict,
                    "publish_date": str(row.get("publish_date", "")),
                    "source_url": str(row.get("source_url", "")),
                },
            )

            if city:
                self.run_query(
                    """
                    MERGE (c:City {name: $city})
                    WITH c
                    MATCH (w:WorkOrder {id: $id})
                    MERGE (w)-[:LOCATED_IN]->(c)
                    """,
                    {"id": case_id, "city": city},
                )

            for district in districts:
                self.run_query(
                    """
                    MERGE (d:District {name: $district})
                    WITH d
                    MATCH (w:WorkOrder {id: $id})
                    MERGE (w)-[:LOCATED_IN]->(d)
                    """,
                    {"id": case_id, "district": district},
                )

            if dept:
                self.run_query(
                    """
                    MERGE (d:Department {name: $dept})
                    WITH d
                    MATCH (w:WorkOrder {id: $id})
                    MERGE (w)-[:HANDLED_BY]->(d)
                    """,
                    {"id": case_id, "dept": dept},
                )

            if conflict:
                self.run_query(
                    """
                    MERGE (t:ConflictType {name: $conflict})
                    WITH t
                    MATCH (w:WorkOrder {id: $id})
                    MERGE (w)-[:HAS_CONFLICT_TYPE]->(t)
                    """,
                    {"id": case_id, "conflict": conflict},
                )

        print(f"  已导入 {len(df)} 条热线案例")

    def import_court_cases(self, csv_path: Path):
        print(f"导入法律文书: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8")
        for _, row in df.iterrows():
            case_id = str(row["document_id"])
            city = str(row.get("city", "")).strip()
            dispute = str(row.get("dispute_type", "")).strip()
            laws = extract_laws(str(row.get("applicable_law", "")))

            key_facts_text = str(row.get("key_facts", ""))
            court_opinion_text = str(row.get("court_opinion", ""))
            districts = extract_districts(f"{key_facts_text} {court_opinion_text}")

            self.run_query(
                """
                MERGE (c:CourtCase {id: $id})
                SET c.case_number = $case_number,
                    c.dispute_type = $dispute_type,
                    c.key_facts = $key_facts,
                    c.court_opinion = $court_opinion,
                    c.applicable_law = $applicable_law,
                    c.judgment_result = $judgment_result,
                    c.judgment_date = $judgment_date,
                    c.source = $source,
                    c.data_source = '法律文书'
                """,
                {
                    "id": case_id,
                    "case_number": str(row.get("case_number", "")),
                    "dispute_type": dispute,
                    "key_facts": key_facts_text,
                    "court_opinion": court_opinion_text,
                    "applicable_law": str(row.get("applicable_law", "")),
                    "judgment_result": str(row.get("judgment_result", "")),
                    "judgment_date": str(row.get("judgment_date", "")),
                    "source": str(row.get("source", "")),
                },
            )

            if city:
                self.run_query(
                    """
                    MERGE (city:City {name: $city})
                    WITH city
                    MATCH (c:CourtCase {id: $id})
                    MERGE (c)-[:LOCATED_IN]->(city)
                    """,
                    {"id": case_id, "city": city},
                )

            for district in districts:
                self.run_query(
                    """
                    MERGE (d:District {name: $district})
                    WITH d
                    MATCH (c:CourtCase {id: $id})
                    MERGE (c)-[:LOCATED_IN]->(d)
                    """,
                    {"id": case_id, "district": district},
                )

            if dispute:
                self.run_query(
                    """
                    MERGE (t:DisputeType {name: $dispute})
                    WITH t
                    MATCH (c:CourtCase {id: $id})
                    MERGE (c)-[:HAS_DISPUTE_TYPE]->(t)
                    """,
                    {"id": case_id, "dispute": dispute},
                )

            for law in laws:
                self.run_query(
                    """
                    MERGE (l:Law {name: $law})
                    WITH l
                    MATCH (c:CourtCase {id: $id})
                    MERGE (c)-[:APPLIES_LAW]->(l)
                    """,
                    {"id": case_id, "law": law},
                )

        print(f"  已导入 {len(df)} 条法律文书")

    def import_news(self, csv_path: Path):
        print(f"导入新闻报道: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8")
        for _, row in df.iterrows():
            news_id = str(row["news_id"])
            city = str(row.get("city", "")).strip()
            media = str(row.get("media", "")).strip()
            conflict = str(row.get("conflict_type", "")).strip()
            departments = split_departments(str(row.get("departments", "")))

            title_text = str(row.get("title", ""))
            content_text = str(row.get("content", ""))
            departments_text = str(row.get("departments", ""))
            districts = extract_districts(f"{title_text} {content_text} {departments_text}")

            self.run_query(
                """
                MERGE (n:News {id: $id})
                SET n.title = $title,
                    n.content = $content,
                    n.conflict_type = $conflict_type,
                    n.solution = $solution,
                    n.departments = $departments,
                    n.note = $note,
                    n.report_date = $report_date,
                    n.original_url = $original_url,
                    n.media = $media,
                    n.data_source = '新闻报道'
                """,
                {
                    "id": news_id,
                    "title": title_text,
                    "content": content_text,
                    "conflict_type": conflict,
                    "solution": str(row.get("solution", "")),
                    "departments": departments_text,
                    "note": str(row.get("note", "")),
                    "report_date": str(row.get("report_date", "")),
                    "original_url": str(row.get("original_url", "")),
                    "media": media,
                },
            )

            if city:
                self.run_query(
                    """
                    MERGE (c:City {name: $city})
                    WITH c
                    MATCH (n:News {id: $id})
                    MERGE (n)-[:LOCATED_IN]->(c)
                    """,
                    {"id": news_id, "city": city},
                )

            for district in districts:
                self.run_query(
                    """
                    MERGE (d:District {name: $district})
                    WITH d
                    MATCH (n:News {id: $id})
                    MERGE (n)-[:LOCATED_IN]->(d)
                    """,
                    {"id": news_id, "district": district},
                )

            if media:
                self.run_query(
                    """
                    MERGE (m:Media {name: $media})
                    WITH m
                    MATCH (n:News {id: $id})
                    MERGE (n)-[:REPORTED_BY]->(m)
                    """,
                    {"id": news_id, "media": media},
                )

            for dept in departments:
                self.run_query(
                    """
                    MERGE (d:Department {name: $dept})
                    WITH d
                    MATCH (n:News {id: $id})
                    MERGE (n)-[:INVOLVES]->(d)
                    """,
                    {"id": news_id, "dept": dept},
                )

            if conflict:
                self.run_query(
                    """
                    MERGE (t:ConflictType {name: $conflict})
                    WITH t
                    MATCH (n:News {id: $id})
                    MERGE (n)-[:HAS_CONFLICT_TYPE]->(t)
                    """,
                    {"id": news_id, "conflict": conflict},
                )

        print(f"  已导入 {len(df)} 条新闻报道")

    def create_cross_domain_relations(self):
        """创建跨数据源关联：同部门、同冲突类型、纠纷类型关联"""
        print("创建跨域关联关系...")

        self.run_query(
            """
            MATCH (w:WorkOrder)-[:HANDLED_BY]->(d:Department)<-[:INVOLVES]-(n:News)
            MERGE (w)-[:RELATED_NEWS {relation: '同处置部门'}]->(n)
            """
        )

        self.run_query(
            """
            MATCH (w:WorkOrder)-[:HAS_CONFLICT_TYPE]->(t:ConflictType)<-[:HAS_CONFLICT_TYPE]-(n:News)
            MERGE (w)-[:RELATED_NEWS {relation: '同冲突类型'}]->(n)
            """
        )

        self.run_query(
            """
            MATCH (w:WorkOrder)-[:HAS_CONFLICT_TYPE]->(ct:ConflictType)
            MATCH (cc:CourtCase)-[:HAS_DISPUTE_TYPE]->(dt:DisputeType)
            WHERE ct.name CONTAINS dt.name OR dt.name CONTAINS ct.name
            MERGE (w)-[:RELATED_COURTCASE {relation: '冲突/纠纷类型相关'}]->(cc)
            """
        )

        self.run_query(
            """
            MATCH (n:News)-[:HAS_CONFLICT_TYPE]->(ct:ConflictType)
            MATCH (cc:CourtCase)-[:HAS_DISPUTE_TYPE]->(dt:DisputeType)
            WHERE ct.name CONTAINS dt.name OR dt.name CONTAINS ct.name
            MERGE (n)-[:RELATED_COURTCASE {relation: '冲突/纠纷类型相关'}]->(cc)
            """
        )

        print("  创建区-城市关联...")
        self.run_query(
            """
            MATCH (d:District)
            MERGE (c:City {name: '广州'})
            MERGE (d)-[:BELONGS_TO]->(c)
            """
        )

        print("  创建同区跨数据源关联...")
        self.run_query(
            """
            MATCH (w:WorkOrder)-[:LOCATED_IN]->(d:District)<-[:LOCATED_IN]-(n:News)
            MERGE (w)-[:RELATED_NEWS {relation: '同区案例'}]->(n)
            """
        )

        self.run_query(
            """
            MATCH (w:WorkOrder)-[:LOCATED_IN]->(d:District)<-[:LOCATED_IN]-(cc:CourtCase)
            MERGE (w)-[:RELATED_COURTCASE {relation: '同区案例'}]->(cc)
            """
        )

        self.run_query(
            """
            MATCH (n:News)-[:LOCATED_IN]->(d:District)<-[:LOCATED_IN]-(cc:CourtCase)
            MERGE (n)-[:RELATED_COURTCASE {relation: '同区案例'}]->(cc)
            """
        )

        print("  跨域关联完成")

    def print_statistics(self):
        print("\n===== 知识图谱统计 =====")
        stats = self.run_query(
            """
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY count DESC
            """
        )
        for record in stats:
            print(f"  节点 {record['label']}: {record['count']}")

        rel_stats = self.run_query(
            """
            MATCH ()-[r]->()
            RETURN type(r) AS rel_type, count(r) AS count
            ORDER BY count DESC
            """
        )
        print("\n  关系统计:")
        for record in rel_stats:
            print(f"    {record['rel_type']}: {record['count']}")

    def build(self, clear: bool = True):
        if clear:
            self.clear_database()
        self.create_constraints()
        self.import_workorders(config.WORKORDER_CSV)
        self.import_court_cases(config.COURTCASE_CSV)
        self.import_news(config.NEWS_CSV)
        self.create_cross_domain_relations()
        self.print_statistics()


def main():
    clear = "--no-clear" not in sys.argv
    builder = KnowledgeGraphBuilder(
        config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD
    )
    try:
        builder.build(clear=clear)
        print("\n知识图谱构建完成!")
    finally:
        builder.close()


if __name__ == "__main__":
    main()
