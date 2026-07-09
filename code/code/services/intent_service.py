"""意图识别服务"""

from services.llm_service import LLMService


INTENT_KB = "knowledge_base"       # 知识库查询
INTENT_GRAPH = "graph_reasoning"    # 推理查询（图谱+知识库）
INTENT_DIRECT = "direct_llm"        # 直接 LLM 应答

INTENT_LABELS = {
    INTENT_KB: "知识库查询",
    INTENT_GRAPH: "推理查询",
    INTENT_DIRECT: "通用问答",
}


class IntentService:
    def __init__(self, llm: LLMService):
        self.llm = llm

    def recognize(self, question: str) -> dict:
        """
        识别用户意图，返回 intent、confidence、reason
        """
        rule_result = self._rule_based(question)
        if rule_result["confidence"] >= 0.85:
            return rule_result

        if self.llm.available:
            return self._llm_based(question, rule_result)

        return rule_result

    def _rule_based(self, question: str) -> dict:
        q = question.strip()

        graph_keywords = [
            "关系", "关联", "哪些部门", "哪些案例", "同一", "相同",
            "涉及", "处理过", "管辖", "适用法律", "法律条文",
            "图谱", "节点", "连线", "跨", "之间",
        ]
        kb_keywords = [
            "案例", "工单", "判决", "新闻", "报道", "怎么处理",
            "如何解决", "处理结果", "12345", "热线", "裁判",
            "纠纷", "投诉", "治理", "社区",
        ]
        direct_keywords = [
            "你好", "谢谢", "什么是", "介绍", "定义", "概念",
            "帮我写", "总结", "概括",
        ]

        graph_score = sum(1 for k in graph_keywords if k in q)
        kb_score = sum(1 for k in kb_keywords if k in q)
        direct_score = sum(1 for k in direct_keywords if k in q)

        if graph_score >= 2 or ("和" in q and ("案例" in q or "部门" in q)):
            return {
                "intent": INTENT_GRAPH,
                "confidence": min(0.95, 0.6 + graph_score * 0.1),
                "reason": f"检测到关系/推理类关键词 (score={graph_score})",
            }

        if kb_score >= 1:
            return {
                "intent": INTENT_KB,
                "confidence": min(0.9, 0.5 + kb_score * 0.15),
                "reason": f"检测到案例/知识检索关键词 (score={kb_score})",
            }

        if direct_score >= 1 and kb_score == 0 and graph_score == 0:
            return {
                "intent": INTENT_DIRECT,
                "confidence": 0.7,
                "reason": "检测到通用对话/概念解释类问题",
            }

        return {
            "intent": INTENT_KB,
            "confidence": 0.55,
            "reason": "默认归类为知识库查询",
        }

    def _llm_based(self, question: str, fallback: dict) -> dict:
        prompt = f"""你是意图分类器。将用户问题分为以下三类之一：
1. knowledge_base - 需要从案例库检索具体案例、工单、判决、新闻内容
2. graph_reasoning - 需要分析实体关系、部门关联、法律适用、跨案例推理
3. direct_llm - 通用概念解释、闲聊、无需检索数据

用户问题：{question}

只返回 JSON：{{"intent": "knowledge_base|graph_reasoning|direct_llm", "confidence": 0.0-1.0, "reason": "简短理由"}}
"""
        response = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=256,
        )
        data = self.llm.extract_json(response)
        intent = data.get("intent", fallback["intent"])
        if intent not in (INTENT_KB, INTENT_GRAPH, INTENT_DIRECT):
            intent = fallback["intent"]

        return {
            "intent": intent,
            "confidence": float(data.get("confidence", fallback["confidence"])),
            "reason": data.get("reason", fallback["reason"]),
        }
