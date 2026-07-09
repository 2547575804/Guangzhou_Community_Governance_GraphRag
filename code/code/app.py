"""Flask 问答系统主程序"""

from flask import Flask, jsonify, render_template, request

import config
from services.qa_service import QAService

app = Flask(__name__)
qa_service: QAService | None = None


def get_qa_service() -> QAService:
    global qa_service
    if qa_service is None:
        qa_service = QAService()
    return qa_service


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health():
    svc = get_qa_service()
    return jsonify({
        "status": "ok",
        "neo4j_connected": svc.neo4j.is_connected(),
        "llm_available": svc.llm.available,
        "kb_documents": len(svc.kb.documents),
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "问题不能为空"}), 400

    try:
        result = get_qa_service().answer(question)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"处理失败: {str(e)}"}), 500


@app.route("/api/kg/stats", methods=["GET"])
def kg_stats():
    try:
        svc = get_qa_service()
        node_stats = svc.neo4j._run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC"
        )
        rel_stats = svc.neo4j._run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC"
        )
        return jsonify({"nodes": node_stats, "relationships": rel_stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # 关闭 Flask 的 Werkzeug 开发服务器警告
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
