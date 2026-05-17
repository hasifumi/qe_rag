import requests
from pathlib import Path
import config


class AsleadChatbotClient:
    """aslead chatbot APIサーバー向けクライアント（中間ファイル渡し対応）"""

    def chat(self, model: str, prompt: str) -> str:
        use_file = config.TMP_FILE and len(prompt) > 2000
        if use_file:
            # TODO: 中間ファイル渡しの具体的プロトコルはFumioが確認
            # 現状の想定: ファイルに書き出してパスをcontentに渡す
            Path(config.TMP_FILE).write_text(prompt, encoding="utf-8")
            messages = [{"role": "user", "content": f"file:{config.TMP_FILE}"}]
        else:
            messages = [{"role": "user", "content": prompt}]

        res = requests.post(
            f"{config.API_BASE_URL}/v1/chat/completions",
            json={"model": model, "messages": messages},
            timeout=60,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


class OllamaClient:
    """Ollama向けクライアント（ネイティブAPI使用）"""

    def chat(self, model: str, prompt: str) -> str:
        res = requests.post(
            f"{config.API_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=300,
        )
        res.raise_for_status()
        return res.json()["message"]["content"]


class LlamaServerClient:
    """llama-server向けクライアント（OpenAI互換API、LIGHT/HEAVYで別ポート）"""

    def chat(self, model: str, prompt: str) -> str:
        # LIGHT_MODEL → ポート8080、HEAVY_MODEL → ポート8081
        base_url = (
            config.LLAMA_LIGHT_BASE_URL
            if model == config.LIGHT_MODEL
            else config.LLAMA_HEAVY_BASE_URL
        )
        res = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                # Qwen3系はデフォルトで長大な英語thinkを生成し、max_tokens超過時に
                # content が空になる。RAGの事実抽出に思考は不要なので完全無効化。
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=300,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


def get_client():
    if config.BACKEND == "ollama":
        return OllamaClient()
    if config.BACKEND == "llama_server":
        return LlamaServerClient()
    return AsleadChatbotClient()  # "aslead_chatbot"


def chat(model: str, prompt: str) -> str:
    """pipeline.py から呼ぶショートカット関数"""
    return get_client().chat(model, prompt)
