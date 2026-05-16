# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

社内文書向けQE-RAG（Query Expansion RAG）システム。デジタル庁「源内」のRAGアーキテクチャをローカル環境向けに移植したもの。

**制約環境**：Windows、管理者権限なし、外部LLMサービスブロック済み。LLMは社内「改良版なんちゃってAPIサーバー」（OpenAI互換プロキシ）経由。

## セットアップ・実行コマンド

```powershell
# 初回セットアップ（仮想環境作成 + 依存パッケージインストール）
uv sync

# 文書の取り込み・インデックス構築（初回・更新時）
uv run python cli.py --ingest

# 質問実行
uv run python cli.py "有給休暇の申請方法は？"

# パッケージ追加
uv add <package-name>
```

## アーキテクチャ

### 4ステップQE-RAGパイプライン

```
ユーザー質問
  ↓ ① expand_query()   → 改良版APIサーバー（LIGHT_MODEL）
  ↓ ② search()         → ChromaDB + multilingual-e5-small（ローカルCPU）
  ↓ ③ rerank()         → cross-encoder（ローカルCPU）
  ↓ ④ generate_answer()→ 改良版APIサーバー（HEAVY_MODEL）+ 中間ファイル渡し
最終回答
```

### モジュール構成

| ファイル | 役割 |
|---|---|
| `config.py` | APIエンドポイント・モデル名・パス等の設定値 |
| `api_client.py` | 改良版APIサーバーのラッパー（`chat(model, prompt, use_file)`） |
| `ingest.py` | 文書テキスト抽出→チャンク分割→ChromaDB登録 |
| `pipeline.py` | QE-RAGパイプライン本体（4関数） |
| `cli.py` | CLIエントリポイント |
| `db/` | ChromaDB永続化ディレクトリ |
| `docs/` | 社内文書フォルダ（pptx/pdf/docx等） |

### ローカルモデル（CPUのみ動作）

- **Embedding**: `intfloat/multilingual-e5-small`（約120MB、日本語対応）
- **Reranker**: `cross-encoder/ms-marco-MiniLM-L-6-v2`（約90MB、英語訓練だが日本語で実用レベル動作）
- **ベクトルDB**: ChromaDB（永続化モード）

### 改良版APIサーバーの特徴

- OpenAI互換API（`/v1/chat/completions`）
- モデル選択可能：`LIGHT_MODEL`（クエリ拡張用）、`HEAVY_MODEL`（回答生成用）
- **中間ファイル渡し機能**：長いプロンプトはファイルに書き出してパスを渡す（`file:./tmp_prompt.txt`形式）
  - `len(prompt) > 2000` のとき自動的に`use_file=True`
  - 具体的プロトコルはFumioに要確認（`TODO: Fumioが確認`コメントで明示）
- Tool Use不使用

## 設定値（config.py）

未記入のプレースホルダーはFumioが記入：
- `API_BASE_URL`：改良版APIサーバーのURL
- `LIGHT_MODEL`・`HEAVY_MODEL`：使用するモデル名

RAGパラメーター：`TOP_K_SEARCH=10`、`TOP_K_RERANK=3`、`QUERY_EXPAND_N=3`

## 実装上の注意

- `expand_query()`のLLM出力（JSON配列）は必ずフォールバック処理を入れる（`json.JSONDecodeError`をキャッチして元の質問のみ返す）
- sentence-transformersの初回起動時にモデルダウンロード（約210MB）が必要。社内ネットワークブロックがある場合は事前にオフラインで取得
- ChromaDBのコレクション名は`"docs"`で固定

## 実装フェーズ

- **Phase 1**（優先）：`config.py`→`api_client.py`→`ingest.py`（pptxのみ）→`pipeline.py`→`cli.py`
- **Phase 2**：pdf/docx対応、増分インデックス更新、メタデータ表示、スコア閾値フィルタ
- **Phase 3**（オプション）：FastAPI WebUI、LoChaBot（Discord）連携
