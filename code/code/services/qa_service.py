"""问答编排服务 - 三分支 + 上下文工程整合"""

from services.intent_service import (
    INTENT_DIRECT,
    INTENT_GRAPH,
    INTENT_KB,
    INTENT_LABELS,
    IntentService,
)
from services.kb_service import KnowledgeBaseService
from services.llm_service import LLMService, MARKDOWN_FORMAT_INSTRUCTION
from services.neo4j_service import Neo4jService


class QAService:
    def __init__(self):
        self.llm = LLMService()
        self.kb = KnowledgeBaseService()
        self.neo4j = Neo4jService(self.llm)
        self.intent_service = IntentService(self.llm)

    def answer(self, question: str) -> dict:
        """完整问答流程"""
        intent_info = self.intent_service.recognize(question)
        keywords = self.kb.extract_keywords(question)

        branch_kb = self._branch_knowledge_base(question)
        branch_graph, generated_cypher = self._branch_graph_reasoning(question, keywords)
        branch_direct = self._branch_direct_llm(question)

        final_answer = self._integrate_response(
            question=question,
            intent_info=intent_info,
            branch_kb=branch_kb,
            branch_graph=branch_graph,
            branch_direct=branch_direct,
        )

        return {
            "question": question,
            "answer": final_answer,
            "intent": intent_info,
            "intent_label": INTENT_LABELS.get(intent_info["intent"], ""),
            "generated_cypher": generated_cypher,
            "branches": {
                "knowledge_base": {
                    "label": "分支1-知识库查询",
                    "content": branch_kb,
                },
                "graph_reasoning": {
                    "label": "分支2-推理查询",
                    "content": branch_graph,
                    "cypher": generated_cypher,
                },
                "direct_llm": {
                    "label": "分支3-LLM应答",
                    "content": branch_direct,
                },
            },
        }

    def _branch_knowledge_base(self, question: str) -> str:
        """分支1: 知识库检索 + LLM 整合"""
        results = self.kb.search(question)
        kb_context = self.kb.format_for_llm(results)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是广州市社区治理案例专家。根据知识库检索结果，"
                    "提炼与用户问题最相关的案例信息，给出结构化摘要。"
                    "引用具体案例时注明来源类型（12345热线/法律文书/新闻报道）。"
                    + MARKDOWN_FORMAT_INSTRUCTION
                ),
            },
            {
                "role": "user",
                "content": f"用户问题：{question}\n\n{kb_context}\n\n请整合以上检索结果作答。",
            },
        ]
        return self.llm.chat(messages, temperature=0.3)

    def _branch_graph_reasoning(self, question: str, keywords: list[str]) -> tuple[str, str]:
        """分支2: Neo4j 推理 + 知识库 + LLM 整合"""
        graph_data = self.neo4j.reasoning_search(question, keywords)
        graph_context = self.neo4j.format_for_llm(graph_data)
        generated_cypher = graph_data.get("cypher", "")

        kb_results = self.kb.search(question, top_k=3)
        kb_context = self.kb.format_for_llm(kb_results)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是社区治理知识图谱分析专家。结合图谱关系推理结果和知识库内容，"
                    "分析实体之间的关联（部门、城市、冲突类型、法律等），"
                    "给出推理过程和结论。"
                    + MARKDOWN_FORMAT_INSTRUCTION
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{question}\n\n"
                    f"{graph_context}\n\n"
                    f"{kb_context}\n\n"
                    "请进行关系推理并整合知识库信息作答。"
                ),
            },
        ]
        return self.llm.chat(messages, temperature=0.3), generated_cypher

    def _branch_direct_llm(self, question: str) -> str:
        """分支3: 直接 LLM 应答"""
        messages = [
            {
                "role": "system",
                "content": (
                    "你是广州市社区治理领域的智能助手，熟悉基层治理、"
                    "12345热线、矛盾纠纷调解、社区公共服务等知识。"
                    "对于通用性问题，给出专业、简洁的回答。"
                    + MARKDOWN_FORMAT_INSTRUCTION
                ),
            },
            {"role": "user", "content": question},
        ]
        return self.llm.chat(messages, temperature=0.5)

    def _integrate_response(
        self,
        question: str,
        intent_info: dict,
        branch_kb: str,
        branch_graph: str,
        branch_direct: str,
    ) -> str:
        """上下文工程：整合三个分支生成最终回复"""
        primary = intent_info["intent"]
        weight_hint = {
            INTENT_KB: "重点参考【知识库分支】的案例检索结果",
            INTENT_GRAPH: "重点参考【推理分支】的图谱关系分析",
            INTENT_DIRECT: "重点参考【直接应答分支】的通用解释",
        }.get(primary, "")

        messages = [
            {
                "role": "system",
                "content": (
                    "你是广州市社区治理案例问答系统的最终整合模块。\n"
                    "你将收到三个并行分支的回答，需要进行上下文工程整合：\n"
                    "1. 知识库分支 - 基于案例文本检索\n"
                    "2. 推理分支 - 基于知识图谱关系推理\n"
                    "3. 直接应答分支 - 基于领域知识的通用回答\n\n"
                    "整合要求：\n"
                    "- 去重、消歧，避免重复罗列\n"
                    "- 优先采用与问题最相关的信息\n"
                    "- 案例引用注明来源\n"
                    "- 回答结构清晰：结论 → 依据 → 建议（如适用）\n"
                    "- 使用中文，专业但易懂"
                    + MARKDOWN_FORMAT_INSTRUCTION
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{question}\n"
                    f"识别意图：{INTENT_LABELS.get(primary, primary)} "
                    f"（置信度 {intent_info.get('confidence', 0):.2f}）\n"
                    f"整合策略：{weight_hint}\n\n"
                    f"=== 分支1 知识库查询 ===\n{branch_kb}\n\n"
                    f"=== 分支2 推理查询 ===\n{branch_graph}\n\n"
                    f"=== 分支3 LLM应答 ===\n{branch_direct}\n\n"
                    "请整合以上三个分支，生成最终回答。"
                ),
            },
        ]
        return self.llm.chat(messages, temperature=0.4, max_tokens=3000)
