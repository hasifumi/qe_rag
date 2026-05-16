# 社内文書QE-RAGシステム 実装計画書
> Claude Codeへの指示用ドキュメント

---

## 背景・前提条件（事前調査サマリー）

### 参考にした仕組み
デジタル庁のガバメントAI「源内」（2026年4月OSSとして公開）に実装されている
「クエリ拡張RAG（QE-RAG）」をローカル環境向けに移植する。

源内のRAGパイプライン構成：
- クエリ拡張・関連性評価：軽量LLM（Nova 2 Lite）
- 回答生成：高性能LLM（Claude Haiku 4.5）
- 検索基盤：OpenSearch Serverless（AWSマネージド）

これを以下の制約に合わせて再設計する。

### 実行環境の制約
| 項目 | 内容 |
|---|---|
| 端末 | Panasonic Let's Note CF-SV1 |
| CPU | Intel Core i5-1145G7 |
| RAM | 8GB |
| GPU | Intel Iris Xe（内蔵のみ、VRAM非独立） |
| OS | Windows |
| 制約 | 管理者権限なし、外部LLMサービスブロック済み |

### LLMアクセス手段
「改良版なんちゃってAPIサーバー」を利用する。
- 社内チャットシステムをOpenAI互換APIとしてラップしたプロキシサーバー
- **モデル選択機能あり**（軽量モデルと高性能モデルの使い分けが可能）
- **中間ファイル渡し機能あり**（長いプロンプトをファイル経由で渡せる）
- 現状はPowerShellコマンドから呼び出している
- Tool Use（Function Calling）は**不要**（今回のパイプラインはchat completionのみ）

### LLMが不要な処理の整理
RAGのうち以下の処理はLLMを使わず、軽量な専用モデルで完結する：

| 処理 | 使用モデル/ツール | サイズ | CPU速度 |
|---|---|---|---|
| Embedding生成 | multilingual-e5-small | 約120MB | 数ms/文 |
| ベクトル検索 | ChromaDB | - | 数ms |
| リランキング | cross-encoder/ms-marco-MiniLM-L-6-v2 | 約90MB | 数十ms |

LLMを呼ぶのは「クエリ拡張」と「回答生成」の2箇所のみ。

---

## システム構成

```
[CF-SV1ローカル]
  社内文書フォルダ（pptx/pdf/docx等）
      ↓ 初回インデックス化（python ingest.py）
  ChromaDB（永続化DBファイル）
      ↑↓ Embedding: multilingual-e5-small（CPU）
      ↑↓ Rerank:    cross-encoder（CPU）

[パイプライン実行]
  ユーザー質問
      ↓
  ① クエリ拡張 → 改良版APIサーバー（軽量モデル）
      ↓
  ② Embedding + ベクトル検索 → ChromaDB（ローカル）
      ↓
  ③ リランキング → cross-encoder（ローカル）
      ↓
  ④ 回答生成 → 改良版APIサーバー（高性能モデル）+ 中間ファイル渡し
      ↓
  最終回答（コンソール or ファイル出力）
```

### 処理時間の目安
```
① クエリ拡張（API）     ～2秒
② Embedding+検索（ローカル） ～0.1秒
③ リランキング（ローカル）   ～0.1秒
④ 回答生成（API）       ～5秒
─────────────────────
合計                    ～7秒
```

ボトルネックはAPIコールのみ。ローカル処理はほぼ無視できる速度。

---

## ディレクトリ構成（目標）

```
qe_rag/
├── README.md
├── requirements.txt
├── config.py              # 設定（APIエンドポイント、モデル名、パス等）
├── ingest.py              # 文書取り込み・インデックス構築
├── pipeline.py            # QE-RAGパイプライン本体
├── cli.py                 # コマンドラインインターフェース
├── api_client.py          # 改良版なんちゃってAPIサーバーのクライアント
├── db/                    # ChromaDB永続化ディレクトリ
└── docs/                  # 社内文書フォルダ（pptx/pdf/docx等）
```

---

## 実装仕様

### config.py
```python
# APIサーバー設定
API_BASE_URL    = "http://localhost:XXXX"  # 改良版APIサーバーのURL
LIGHT_MODEL     = "model-light"            # クエリ拡張・評価用軽量モデル名
HEAVY_MODEL     = "model-heavy"            # 回答生成用高性能モデル名

# ローカルモデル設定
EMBED_MODEL     = "intfloat/multilingual-e5-small"
RERANK_MODEL    = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# パス設定
DOCS_DIR        = "./docs"
DB_DIR          = "./db"
TMP_PROMPT_FILE = "./tmp_prompt.txt"       # 中間ファイル渡し用

# RAGパラメーター
TOP_K_SEARCH    = 10   # ベクトル検索で取得する件数
TOP_K_RERANK    = 3    # リランキング後に使う件数
QUERY_EXPAND_N  = 3    # クエリ拡張で生成する言い換え数
```

### api_client.py（改良版APIサーバーのラッパー）
```python
import requests
import json
from pathlib import Path
from config import API_BASE_URL, TMP_PROMPT_FILE

def chat(model: str, prompt: str, use_file: bool = False) -> str:
    """
    改良版なんちゃってAPIサーバーへのchat completionリクエスト。
    use_file=Trueのときは中間ファイル渡し機能を使う。
    """
    if use_file:
        # 中間ファイルに書き出してAPIサーバーに参照させる
        Path(TMP_PROMPT_FILE).write_text(prompt, encoding="utf-8")
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"file:{TMP_PROMPT_FILE}"}
            ]
        }
    else:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }

    res = requests.post(
        f"{API_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=60
    )
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]
```

> **注意**: 中間ファイル渡しの具体的なプロトコルは改良版APIサーバーの実装に合わせること。
> 実装者（Fumio）に確認して調整する。

### ingest.py（文書取り込み）

対応フォーマット：
- `.pptx` → python-pptx でスライドテキスト抽出
- `.pdf`  → pdfminer.six でテキスト抽出
- `.docx` → python-docx でテキスト抽出
- `.txt` / `.md` → 直接読み込み

処理フロー：
1. `DOCS_DIR`を再帰的にスキャン
2. 各ファイルをテキスト抽出
3. チャンク分割（1000文字、200文字オーバーラップ）
4. Embeddingを生成してChromaDBに登録
5. メタデータ（ファイル名、ページ/スライド番号、更新日時）も保存

```python
# pptxの抽出イメージ
from pptx import Presentation

def extract_pptx(path: str) -> list[dict]:
    prs = Presentation(path)
    chunks = []
    for i, slide in enumerate(prs.slides):
        text = "\n".join(
            shape.text for shape in slide.shapes if shape.has_text_frame
        )
        if text.strip():
            chunks.append({
                "text": text,
                "metadata": {"file": path, "slide": i+1}
            })
    return chunks
```

### pipeline.py（QE-RAGパイプライン）

```python
from sentence_transformers import SentenceTransformer, CrossEncoder
import chromadb, json
from api_client import chat
from config import *

# 起動時ロード（合計約200MB、初回のみ時間がかかる）
embedder = SentenceTransformer(EMBED_MODEL)
reranker = CrossEncoder(RERANK_MODEL)
chroma   = chromadb.PersistentClient(path=DB_DIR)

def expand_query(question: str) -> list[str]:
    """① クエリ拡張（軽量モデル）"""
    prompt = f"""以下の質問を検索に使う{QUERY_EXPAND_N}つの異なる言い回しに展開してください。
JSON配列のみ返してください。例: ["言い換え1", "言い換え2", "言い換え3"]

質問: {question}"""
    result = chat(LIGHT_MODEL, prompt)
    try:
        queries = json.loads(result)
        return [question] + queries  # 元の質問も含める
    except json.JSONDecodeError:
        return [question]  # フォールバック：元の質問のみ

def search(queries: list[str], collection) -> list[str]:
    """② ベクトル検索（ローカル）"""
    results = []
    for q in queries:
        vec = embedder.encode(q).tolist()
        hits = collection.query(query_embeddings=[vec], n_results=TOP_K_SEARCH)
        results.extend(hits["documents"][0])
    return list(dict.fromkeys(results))  # 順序を保ちつつ重複除去

def rerank(question: str, chunks: list[str]) -> list[str]:
    """③ リランキング（ローカル）"""
    if not chunks:
        return []
    scores = reranker.predict([[question, c] for c in chunks])
    ranked = sorted(zip(scores, chunks), reverse=True)
    return [c for _, c in ranked[:TOP_K_RERANK]]

def generate_answer(question: str, chunks: list[str]) -> str:
    """④ 回答生成（高性能モデル）"""
    context = "\n\n---\n\n".join(chunks)
    prompt = f"""以下のコンテキストのみを根拠として質問に答えてください。
コンテキストに情報がない場合は「該当する情報が見つかりませんでした」と答えてください。

【コンテキスト】
{context}

【質問】
{question}"""
    # コンテキストが長い場合は中間ファイル渡しを使う
    use_file = len(prompt) > 2000
    return chat(HEAVY_MODEL, prompt, use_file=use_file)

def run(question: str) -> str:
    """パイプライン全体"""
    col = chroma.get_or_create_collection("docs")
    queries  = expand_query(question)
    chunks   = search(queries, col)
    reranked = rerank(question, chunks)
    answer   = generate_answer(question, reranked)
    return answer
```

### cli.py（コマンドラインインターフェース）

```python
# 使用例
# python cli.py "有給休暇の申請方法は？"
# python cli.py --ingest   # 文書の取り込み・再インデックス
```

---

## 依存パッケージ（requirements.txt）

```
sentence-transformers>=2.7.0   # Embedding + Cross-Encoder
chromadb>=0.5.0                # ベクトルDB
python-pptx>=1.0.0             # pptx抽出
pdfminer.six>=20221105         # pdf抽出
python-docx>=1.1.0             # docx抽出
requests>=2.31.0               # APIクライアント
```

> **管理者権限なしでのインストール**:
> `pip install --user -r requirements.txt`
> または uv/venvをユーザーディレクトリに作成する

---

## 実装フェーズ

### Phase 1（優先）：動くものを作る
- [ ] `config.py` の作成（APIサーバーURLとモデル名はFumioが記入）
- [ ] `api_client.py` の作成（中間ファイル渡しプロトコルはFumioが確認）
- [ ] `ingest.py` の作成（まずpptx対応のみでよい）
- [ ] `pipeline.py` の作成
- [ ] `cli.py` の作成
- [ ] 動作確認：数ファイルで試す

### Phase 2：精度・使いやすさ改善
- [ ] pdf/docx対応を追加
- [ ] 増分インデックス更新（変更ファイルのみ再インデックス）
- [ ] メタデータ表示（回答の根拠ファイル名・スライド番号を表示）
- [ ] スコア閾値フィルタ（関連度が低すぎるチャンクを除外）

### Phase 3（オプション）：UI
- [ ] 簡易WebUI（FastAPI + 最小限HTML）
- [ ] LoChaBot連携（Discordから質問できるようにする）

---

## Claude Codeへの指示文（コピペ用）

```
以下の仕様書に基づいて、社内文書へのQE-RAG問い合わせシステムを実装してください。

## 環境
- OS: Windows（管理者権限なし）
- Python: ユーザーディレクトリにインストール済み
- LLM: 改良版なんちゃってAPIサーバー（OpenAI互換、localhost）
  - モデル選択機能あり
  - 中間ファイル渡し機能あり（長いプロンプトをファイルパスで渡す）
  - Tool Useは不使用
- ローカル処理: sentence-transformers（CPU動作）、ChromaDB

## 実装対象（Phase 1）
1. config.py        - 設定値（APIのURLとモデル名はプレースホルダーでよい）
2. api_client.py    - chat()関数（中間ファイル渡し対応）
3. ingest.py        - pptxからテキスト抽出してChromaDBに登録
4. pipeline.py      - QE-RAGパイプライン（expand_query/search/rerank/generate_answer）
5. cli.py           - python cli.py "質問文" で動くCLI
6. requirements.txt - 依存パッケージ一覧

## 制約・注意事項
- pip install は --user フラグを使うこと（管理者権限なし）
- Embeddingは intfloat/multilingual-e5-small を使う（日本語対応、約120MB）
- リランキングは cross-encoder/ms-marco-MiniLM-L-6-v2 を使う（約90MB）
- LLMへのJSON出力指示は必ずフォールバック処理を入れること
- 中間ファイル渡しの具体的プロトコルはコメントで「TODO: Fumioが確認」と記載

## 参考にしたアーキテクチャ
デジタル庁「源内」のクエリ拡張RAG（genai-ai-api）をローカル向けに移植したもの。
クラウドのOpenSearch ServerlessをChromaDB、BedRockモデルを改良版APIサーバーに置き換えた構成。
```

---

## 備考・決定事項メモ

- 中間ファイル渡しのプロトコル詳細は改良版APIサーバーの実装を要確認
- 改良版APIサーバーで使えるモデル名（LIGHT_MODEL/HEAVY_MODEL）はFumioが記入
- Cross-Encoderは英語訓練モデルだが日本語でも実用レベルで動作する実績あり
- sentence-transformersの初回ダウンロードはインターネット接続が必要（社内ブロック注意）
  → 事前にモデルファイルをダウンロードしてオフラインで使う方法も検討
