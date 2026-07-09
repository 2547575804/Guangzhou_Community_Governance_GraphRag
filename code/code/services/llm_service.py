"""DeepSeek LLM 服务"""

import json
import re

import requests

import config

MARKDOWN_FORMAT_INSTRUCTION = (
    "\n\n输出格式要求（必须遵守）：\n"
    "- 使用标准 Markdown 格式输出\n"
    "- 用 ## / ### 组织标题层级\n"
    "- 用有序/无序列表呈现要点\n"
    "- 用 **加粗** 标注关键信息，用 `代码` 标注案例编号或法律条文\n"
    "- 案例引用使用引用块 > 格式\n"
    "- 多条案例对比可使用 Markdown 表格\n"
    "- 不要使用 HTML 标签，不要包裹 ```markdown 代码块"
)


class LLMService:
    def __init__(self):
        self.api_key = config.DEEPSEEK_API_KEY
        self.base_url = config.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = config.DEEPSEEK_MODEL

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        if not self.available:
            return self._fallback_response(messages)

        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[LLM 调用失败: {e}] {self._fallback_response(messages)}"

    def _fallback_response(self, messages: list[dict]) -> str:
        """无 API Key 时的本地降级回复"""
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        return (
            f"（DeepSeek API 未配置，以下为基于上下文的简要回复）\n"
            f"针对您的问题「{user_msg[:100]}」，请参考系统检索到的案例与图谱信息进行判断。"
        )

    def extract_json(self, text: str) -> dict:
        """从 LLM 输出中提取 JSON"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {}
