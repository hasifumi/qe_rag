"""QE-RAGパイプライン（4ステップ）"""
import os

# 外部サービスブロック環境かつ全モデルキャッシュ済み。
# Hub通信（hf-xetネイティブ拡張）でのACCESS_VIOLATIONを避けるため完全オフライン強制。
# transformers/sentence_transformers の import より前に設定する必要がある。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import json

import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder

import config
from api_client import chat

# 起動時ロード（初回のみ時間がかかる）
_embedder = None
_reranker = None
_chroma   = None


def _get_resources():
    global _embedder, _reranker, _chroma
    if _embedder is None:
        _embedder = SentenceTransformer(config.EMBED_MODEL, device="cpu")
        _reranker = CrossEncoder(config.RERANK_MODEL, device="cpu")
        _chroma   = chromadb.PersistentClient(path=config.DB_DIR)
    return _embedder, _reranker, _chroma


def expand_query(question: str) -> list[str]:
    """① クエリ拡張（軽量モデル）"""
    prompt = (
        "/no_think\n"
        f"以下の質問を検索に使う{config.QUERY_EXPAND_N}つの異なる言い回しに展開してください。\n"
        f"JSON配列のみ返してください。例: [\"言い換え1\", \"言い換え2\", \"言い換え3\"]\n\n"
        f"質問: {question}"
    )
    result = chat(config.LIGHT_MODEL, prompt)
    try:
        queries = json.loads(result)
        if isinstance(queries, list):
            return [question] + [str(q) for q in queries]
    except (json.JSONDecodeError, ValueError):
        pass
    return [question]


def search(queries: list[str], col, department: str | None = None) -> list[str]:
    """② ベクトル検索（ローカル）"""
    embedder, _, _ = _get_resources()
    results = []
    where = {"department": department} if department and department != "all" else None
    for q in queries:
        vec = embedder.encode(q).tolist()
        kwargs: dict = {"query_embeddings": [vec], "n_results": config.TOP_K_SEARCH}
        if where:
            kwargs["where"] = where
        hits = col.query(**kwargs)
        results.extend(hits["documents"][0])
    return list(dict.fromkeys(results))


def rerank(question: str, chunks: list[str]) -> list[str]:
    """③ リランキング（ローカル）"""
    if not chunks:
        return []
    _, reranker, _ = _get_resources()
    scores = reranker.predict([[question, c] for c in chunks])
    ranked = sorted(zip(scores, chunks), reverse=True)
    return [c for _, c in ranked[: config.TOP_K_RERANK]]


def generate_answer(question: str, chunks: list[str]) -> str:
    """④ 回答生成（高性能モデル）"""
    if not chunks:
        return "該当する情報が見つかりませんでした。"
    context = "\n\n---\n\n".join(chunks)
    prompt = (
        "/no_think\n"
        "以下のコンテキストのみを根拠として質問に答えてください。\n"
        "コンテキストに情報がない場合は「該当する情報が見つかりませんでした」と答えてください。\n\n"
        f"【コンテキスト】\n{context}\n\n"
        f"【質問】\n{question}"
    )
    return chat(config.HEAVY_MODEL, prompt)


def run(question: str, department: str | None = None, on_progress=None) -> dict:
    """パイプライン全体を実行して回答と参照情報を返す

    on_progress: 進捗メッセージを受け取る callable（引数1: str）。
                 None のとき print（CLI 後方互換）。Web UI は SSE 送出用に渡す。
    """
    report = on_progress if on_progress is not None else print

    _, _, chroma = _get_resources()
    col = chroma.get_or_create_collection("docs")

    report("[1/4] クエリ拡張中...")
    queries = expand_query(question)

    report(f"[2/4] 検索中... ({len(queries)} クエリ)")
    chunks = search(queries, col, department)
    report(f"      {len(chunks)} 件取得")

    report("[3/4] リランキング中...")
    reranked = rerank(question, chunks)
    report(f"      {len(reranked)} 件に絞り込み")

    report("[4/4] 回答生成中...")
    answer = generate_answer(question, reranked)

    # 参照文書のメタデータを取得
    sources = []
    if reranked:
        results = col.get(include=["documents", "metadatas"])
        doc_to_meta = dict(zip(results["documents"], results["metadatas"]))
        for chunk in reranked:
            meta = doc_to_meta.get(chunk)
            if meta:
                entry = {"file": meta.get("file", "")}
                if "slide" in meta:
                    entry["slide"] = meta["slide"]
                elif "page" in meta:
                    entry["page"] = meta["page"]
                if entry not in sources:
                    sources.append(entry)

    return {"answer": answer, "sources": sources}
