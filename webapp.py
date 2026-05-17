"""FastAPI Web UI（QE-RAG 照会 / 文書再インデックス）

CLI（cli.py）と同じ pipeline / ingest をそのまま利用する。
重いブロッキング処理は別スレッドで実行し、進捗を SSE でブラウザへ流す。

起動:
    uv run uvicorn webapp:app --port 8000
ブラウザ:
    http://localhost:8000
"""
import json
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時にローカルモデル（embedder/reranker/ChromaDB）を事前ロードし、
    # 初回照会のレイテンシを削減する。pipeline 側でグローバルキャッシュされる。
    import pipeline

    pipeline._get_resources()
    yield


app = FastAPI(title="QE-RAG Web UI", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str
    department: str = "all"


def _sse(payload: dict) -> str:
    """1 イベント = `data: {json}\\n\\n`。type フィールドで種別を区別する。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_stream(target):
    """target(report) を別スレッドで実行し、進捗・結果・エラーを SSE で yield する。

    target: report(msg:str) を受け取り、最終結果(dict)を返す callable。
    """
    q: "queue.Queue[tuple[str, object]]" = queue.Queue()

    def report(msg: str) -> None:
        q.put(("progress", msg))

    def worker() -> None:
        try:
            result = target(report)
            q.put(("done", result))
        except Exception as e:  # noqa: BLE001 - エラー内容を UI へ返すため握る
            q.put(("error", f"{type(e).__name__}: {e}"))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        kind, payload = q.get()
        if kind == "progress":
            yield _sse({"type": "progress", "message": payload})
        elif kind == "error":
            yield _sse({"type": "error", "message": payload})
            return
        else:  # done
            result = payload if isinstance(payload, dict) else {}
            yield _sse({"type": "done", **result})
            return


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/ask")
def api_ask(req: AskRequest):
    import pipeline

    question = req.question.strip()
    if not question:
        def empty():
            yield _sse({"type": "error", "message": "質問が空です"})

        return StreamingResponse(empty(), media_type="text/event-stream")

    def target(report):
        return pipeline.run(question, department=req.department, on_progress=report)

    return StreamingResponse(_event_stream(target), media_type="text/event-stream")


@app.get("/api/files")
def api_files():
    import pipeline

    _, _, chroma = pipeline._get_resources()
    col = chroma.get_or_create_collection("docs")
    metas = col.get(include=["metadatas"])["metadatas"]
    seen: dict[str, dict] = {}
    for m in metas:
        f = m.get("file", "")
        if f and f not in seen:
            seen[f] = {"name": Path(f).name, "department": m.get("department", "common")}
    files = [{"file": k, "name": v["name"], "department": v["department"]} for k, v in seen.items()]
    return {"files": files}


@app.post("/api/ingest")
def api_ingest():
    import ingest

    def target(report):
        ingest.ingest(on_progress=report)
        return {"message": "インデックス構築完了"}

    return StreamingResponse(_event_stream(target), media_type="text/event-stream")


ALLOWED_EXTS = {".pptx", ".pdf", ".docx", ".txt", ".md"}


@app.post("/api/upload")
async def api_upload(files: list[UploadFile] = File(...), department: str = Form("common")):
    import ingest as ingest_mod
    import config

    target_dir = Path(config.DOCS_DIR) / department
    target_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    skipped: list[str] = []
    file_contents: list[tuple[str, bytes]] = []

    for f in files:
        name = Path(f.filename).name  # パストラバーサル除去
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTS:
            skipped.append(name)
        else:
            data = await f.read()
            file_contents.append((name, data))
            saved.append(name)

    def target(report):
        for name, data in file_contents:
            dest = target_dir / name
            dest.write_bytes(data)
            report(f"  保存: {name} → {department}/")
        for name in skipped:
            report(f"  スキップ（非対応形式）: {name}")
        if saved:
            ingest_mod.ingest(on_progress=report)
            return {"message": f"{len(saved)} ファイル保存・インデックス更新完了"}
        return {"message": "保存対象ファイルなし（対応形式: pptx/pdf/docx/txt/md）"}

    return StreamingResponse(_event_stream(target), media_type="text/event-stream")
