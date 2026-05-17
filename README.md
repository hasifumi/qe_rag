# QE-RAG — 社内文書 Query Expansion RAG システム

社内文書（PowerPoint・PDF・Word・テキスト）に対して自然言語で質問できる RAG システムです。
デジタル庁「源内」のアーキテクチャをローカル環境向けに移植しました。

## 特徴

- **クエリ拡張（QE）**：質問を複数の言い回しに展開してから検索することで、キーワードのゆらぎに強い
- **ローカルモデルのみ**：Embedding・Reranker は CPU 動作、外部サービス不要
- **LLM は選択式**：社内 API サーバー・Ollama・llama-server の 3 バックエンドに対応
- **増分インデックス**：更新ファイルのみ再登録、削除ファイルは自動除外
- **Web UI & CLI**：ブラウザから使える UI と、スクリプト連携しやすい CLI の両方を提供

## アーキテクチャ

```
ユーザー質問
  ① expand_query()    → LLM（LIGHT_MODEL）でクエリを 3 つに拡張
  ② search()          → ChromaDB + multilingual-e5-small でベクトル検索
  ③ rerank()          → cross-encoder でリランキング（上位 3 件に絞る）
  ④ generate_answer() → LLM（HEAVY_MODEL）で回答生成
最終回答＋参照文書（ファイル名・スライド番号・ページ番号）
```

## 動作環境

| 項目 | 内容 |
|---|---|
| OS | Windows（PowerShell） |
| Python | 3.10 以上（uv で管理） |
| GPU | 不要（Embedding・Reranker は CPU 動作） |
| LLM | 社内 API サーバー / Ollama / llama-server（いずれか） |

## セットアップ（自宅 PC・llama-server 使用例）

### 1. 依存パッケージのインストール

```powershell
uv sync
```

初回は HuggingFace からモデルが自動ダウンロードされます（計 約 940MB）。

### 2. LLM サーバーの起動（llama-server の場合）

2 つの PowerShell ウィンドウで起動します（パスは環境に合わせて変更）：

```powershell
# ウィンドウ1 — LIGHT モデル（ポート 8080）
llama-server.exe -m "Qwen3-0.6B-Q8_0.gguf" --port 8080 -ngl 99

# ウィンドウ2 — HEAVY モデル（ポート 8081）
llama-server.exe -m "Qwen3.5-9B-Q4_K_M.gguf" --port 8081 -ngl 99
```

### 3. config.py の確認

`config.py` の `BACKEND` が目的の値になっていることを確認します：

```python
BACKEND = "llama_server"    # 自宅（llama-server）
# BACKEND = "ollama"        # 自宅（Ollama）
# BACKEND = "aslead_chatbot"  # 会社（aslead chatbot API 経由）
```

### 4. 文書の取り込み

`docs/` フォルダに社内文書を置いてインデックスを構築します：

```powershell
# サンプル文書で試す場合
uv run python create_test_docs.py

# インデックス構築
uv run python cli.py --ingest
```

## 使い方

### CLI

```powershell
# 質問する
uv run python cli.py "有給休暇の申請方法は？"
uv run python cli.py "育児休業は子供が何歳まで取れますか？"

# 文書を更新したときは再インデックス
uv run python cli.py --ingest
```

### Web UI

```powershell
uv run uvicorn webapp:app --port 8000
```

ブラウザで `http://localhost:8000` を開きます。
質問・進捗表示・ファイルアップロード・インデックス済みファイル一覧に対応しています。

## 対応ファイル形式

| 形式 | 拡張子 |
|---|---|
| PowerPoint | `.pptx` |
| PDF | `.pdf` |
| Word | `.docx` |
| テキスト | `.txt` / `.md` |

## 会社 PC でのセットアップ

制約環境（外部ネットワークブロック・Cドライブ読み取り専用・管理者権限なし）での
セットアップ手順は [COMPANY_SETUP.md](COMPANY_SETUP.md) を参照してください。

## モジュール構成

| ファイル | 役割 |
|---|---|
| `config.py` | バックエンド選択・API エンドポイント・モデル名・パス等の設定 |
| `api_client.py` | LLM API クライアント（aslead chatbot / Ollama / llama-server） |
| `ingest.py` | 文書テキスト抽出 → チャンク分割 → ChromaDB 登録（増分・削除同期） |
| `pipeline.py` | QE-RAG パイプライン本体（4 関数） |
| `cli.py` | CLI エントリポイント |
| `webapp.py` | FastAPI Web UI |
| `static/index.html` | シングルページ UI（SSE 進捗・回答・ハイライト表示） |
| `create_test_docs.py` | 動作確認用サンプル文書生成スクリプト |

## ローカルモデル

- **Embedding**: `intfloat/multilingual-e5-small`（約 470MB、日本語対応）
- **Reranker**: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`（約 470MB）
- 初回 `uv sync` 後、`--ingest` 実行時に自動ダウンロードされます

## RAG パラメーター

`config.py` で調整できます：

| パラメーター | デフォルト | 説明 |
|---|---|---|
| `TOP_K_SEARCH` | 10 | ベクトル検索の取得件数 |
| `TOP_K_RERANK` | 3 | リランキング後の上位件数 |
| `QUERY_EXPAND_N` | 3 | クエリ拡張数 |

## ライセンス

MIT
