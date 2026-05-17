# 会社PC セットアップ＆利用手順（QE-RAG）

社内文書QE-RAGシステムを **会社PC** で動かすための手順書。

## 0. 会社PCの前提・制約

| 項目 | 内容 | 影響 |
|---|---|---|
| OS | Windows | PowerShell前提 |
| 権限 | **管理者権限なし** | uvはユーザー領域インストール。ページングファイル変更不可（§7参照） |
| ネットワーク | **外部LLM・外部サイトブロック済み** | HuggingFaceからモデルDL不可 → §2でキャッシュを事前持ち込み必須 |
| LLM | 社内「aslead chatbot」APIサーバー（OpenAI互換プロキシ） | `BACKEND="aslead_chatbot"` を使用（§4） |
| ローカルモデル | Embedding / Reranker はCPUで動作（GPU不要） | 事前キャッシュさえあればオフラインで完結 |

> ⚠️ **最重要**：`pipeline.py` は完全オフライン強制（`HF_HUB_OFFLINE=1`）で動く。
> モデルキャッシュが無いと**起動すらできない**。§2を必ず先に実施すること。

---

## 1. 事前準備（ネット接続可能なPCで実施）

会社PCに持ち込む2点を、ネットが使える環境（例：自宅PC）で用意する。

### 1-1. リポジトリ一式

プロジェクトフォルダ `qe_rag` を丸ごとUSB等で持ち込む。
ただし以下は**持ち込み不要**（容量大・会社PCで再生成する）：

- `.venv/`（会社PCで `uv sync` で再構築）
- `db/`（会社PCで `--ingest` で再構築）
- `docs/`（会社PCに実際の社内文書を置く）

> Git管理している場合 `.venv/ db/ docs/` は `.gitignore` 済み。
> `git clone` で持ち込んでもよい（会社PCがGit/社内リポジトリにアクセスできる場合）。

### 1-2. HuggingFaceモデルキャッシュ（約940MB）

ネット可能PCで以下2フォルダを取得済みのはず（本プロジェクトを動かしたPCにある）。
無い場合はネット可能PCで一度 `uv run python cli.py --ingest` を実行すれば自動DLされる。

キャッシュ場所：`%USERPROFILE%\.cache\huggingface\hub\`

持ち込む2フォルダ：

```
models--intfloat--multilingual-e5-small                (約470MB) … Embedding
models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1    (約470MB) … Reranker
```

ZIP化して持ち込む例（ネット可能PC側）：

```powershell
$hub = "$env:USERPROFILE\.cache\huggingface\hub"
Compress-Archive -Path `
  "$hub\models--intfloat--multilingual-e5-small", `
  "$hub\models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1" `
  -DestinationPath "$env:USERPROFILE\Desktop\hf_cache_qe_rag.zip"
```

---

## 2. 会社PCでのセットアップ

### 2-1. uv の確認

uv は導入済みの前提。念のため確認：

```powershell
uv --version
```

未インストールの場合（外部ネット不可なら自宅PCで入手してUSB持ち込み）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2-2. 環境変数の設定（C ドライブ非使用）

会社PCはCドライブが読み取り専用のため、キャッシュ先をVドライブ（または書き込み可能なドライブ）へ向ける。
PowerShellプロファイル（`notepad $PROFILE`）に以下を追加して保存：

```powershell
$env:UV_CACHE_DIR = "V:\uv_cache"
$env:HF_HOME      = "V:\hf_models"
```

設定後、PowerShellを再起動して反映させること。

### 2-3. プロジェクト配置

持ち込んだ `qe_rag` フォルダを **Vドライブ**（または書き込み可能な場所）に展開：

```
V:\project\qe_rag\
```

### 2-4. HFモデルキャッシュの配置

§1-2 のZIPを `HF_HOME` で指定したフォルダの `hub` サブフォルダへ展開：

```powershell
$hub = "$env:HF_HOME\hub"
New-Item -ItemType Directory -Force $hub | Out-Null
Expand-Archive -Path "<持ち込んだ>\hf_cache_qe_rag.zip" -DestinationPath $hub
```

展開後、以下2フォルダが存在することを確認：

```powershell
Get-ChildItem "$env:HF_HOME\hub" -Directory |
  Where-Object Name -match 'multilingual-e5-small|mmarco-mMiniLMv2'
```

### 2-5. 依存パッケージのインストール

プロジェクトフォルダで：

```powershell
uv sync
```

> `transformers==4.57.6` 等のバージョンは `uv.lock` で固定済み。
> **`uv.lock` のバージョンを勝手に上げないこと**（新しいtransformersはモデルロードで
> ネイティブクラッシュする既知問題があり、4.57.6に固定している）。

---

## 3. config.py の記入（Fumio対応・必須）

`config.py` 冒頭の `BACKEND` を会社用に切り替える：

```python
# BACKEND = "llama_server"    # 自宅
BACKEND = "aslead_chatbot"    # ← 会社はこれ
```

次に「aslead chatbot APIサーバー」の値を記入（**TODO: Fumioが記入** の3箇所）：

```python
ASLEAD_BASE_URL    = "http://<社内APIサーバーのホスト:ポート>"
ASLEAD_LIGHT_MODEL = "<クエリ拡張用の軽量モデル名>"
ASLEAD_HEAVY_MODEL = "<回答生成用の高性能モデル名>"
```

> `ASLEAD_LIGHT_MODEL` と `ASLEAD_HEAVY_MODEL` は**必ず異なる文字列**にする
> （同一値だと振り分けが壊れる。詳細は §7 既知の罠）。

---

## 4. 動作確認（サンプル文書で疎通テスト）

実文書を入れる前に、付属のサンプルで一連の流れを確認する。

```powershell
# サンプル文書（架空の就業規則・福利厚生）を生成
uv run python create_test_docs.py

# インデックス構築（初回はEmbeddingモデルのロードで数十秒）
uv run python cli.py --ingest

# 質問してみる
uv run python cli.py "給与の支払い日はいつですか？"
```

期待結果：「毎月25日（土日祝の場合は前営業日）」といった回答＋参照文書名が表示される。
ここまで通れば、ローカルモデル・ChromaDB・社内APIの3系統すべて疎通OK。

---

## 5. 実運用

### 5-1. 社内文書の取り込み

`docs/` フォルダに実際の社内文書を置く（サブフォルダ可）。対応形式：

| 形式 | 拡張子 |
|---|---|
| PowerPoint | `.pptx` |
| PDF | `.pdf` |
| Word | `.docx` |
| テキスト | `.txt` / `.md` |

```powershell
uv run python cli.py --ingest
```

- 増分対応：更新の無いファイルは自動スキップ、更新ファイルのみ再登録される。
- 文書を入れ替えた／更新したら、その都度 `--ingest` を実行する。

### 5-2. 質問する

```powershell
uv run python cli.py "有給休暇は何日もらえますか？"
uv run python cli.py "育児休業は子供が何歳まで取れますか？"
```

回答に続けて、根拠とした文書名（スライド／ページ番号付き）が表示される。

---

## 6. 日常運用クイックリファレンス

| やりたいこと | コマンド |
|---|---|
| 初回セットアップ | `uv sync` |
| 文書を取り込む／更新する | `uv run python cli.py --ingest` |
| 質問する | `uv run python cli.py "質問文"` |
| パッケージ追加（通常不要） | `uv add <pkg>`（事前に `uv pip index versions <pkg>` で存在確認） |

---

## 7. トラブルシューティング

### A. 起動直後にクラッシュ／モデルがロードできない

- **症状**：`OSError ... os error 1455`、終了コード `-1073741819`(0xC0000005) など。
- **原因候補1（キャッシュ欠落）**：§2-3 のHFキャッシュが正しく配置されていない。
  `%USERPROFILE%\.cache\huggingface\hub\` に2フォルダがあるか再確認。
- **原因候補2（ページングファイル枯渇）**：Windowsのコミット上限枯渇。
  会社PCは通常「システム管理」のため発生しにくいが、発生した場合は
  **管理者権限が必要なため社内IT部門に連絡**し、
  「仮想メモリ＝システム管理サイズ」への変更を依頼する。
  確認コマンド（読み取りは権限不要）：
  ```powershell
  Get-CimInstance Win32_ComputerSystem | Select-Object AutomaticManagedPagefile
  ```
  `True` が正常。`False` の場合はIT部門へ。

### B. 回答が空、または文脈に答えがあるのに「該当する情報が見つかりませんでした」

- 検索・リランクは正しいのに回答だけ崩れる場合の典型。
- **原因1**：`config.py` の `ASLEAD_LIGHT_MODEL` と `ASLEAD_HEAVY_MODEL` が
  同じ値になっている → 必ず別の値にする。
- **原因2（要Fumio確認）**：社内APIの裏のモデルが「思考(thinking)」を長文生成し
  出力上限を食い潰している可能性。自宅llama-server構成では
  `chat_template_kwargs.enable_thinking=false` で解決したが、**aslead chatbot API側で
  同等の無効化が必要かは社内APIサーバー仕様の確認が必要**（§8）。

### C. 社内APIに繋がらない

- `ASLEAD_BASE_URL` のホスト・ポートを確認。
- 疎通確認：
  ```powershell
  Invoke-WebRequest "$($url)/v1/models" -UseBasicParsing   # url は ASLEAD_BASE_URL
  ```
- VPN／社内ネットワーク内からのアクセスが必要な場合がある。

### D. ネットワークエラーでモデルをダウンロードしようとする

- `pipeline.py` は完全オフライン強制済みなので通常発生しない。
- 発生する場合はHFキャッシュのフォルダ名が違う／配置場所が
  `%USERPROFILE%\.cache\huggingface\hub\` でない。§2-3を再確認。

---

## 8. 既知の未確認事項（Fumio確認待ち）

1. **中間ファイル渡しプロトコル**：`api_client.py` の `AsleadChatbotClient` は
   プロンプトが2000文字超のとき `file:./tmp_prompt.txt` 形式でパスを渡す想定。
   **実際の社内APIサーバーの受け取り仕様（キー名・パス形式）は要確認**
   （コード内 `TODO: Fumioが確認` コメント箇所）。
2. **thinking挙動**：社内API裏のモデルが思考トークンを返すか、返す場合の
   無効化方法（リクエストパラメータ）は社内APIサーバー仕様の確認が必要。
   問題が出たら §7-B を参照しサーバー担当へ確認。

---

## 付録：構成の要点

```
ユーザー質問
  ① expand_query()   → 社内API（LIGHT_MODEL）       クエリ拡張
  ② search()         → ChromaDB + e5-small（CPU）   ベクトル検索
  ③ rerank()         → mmarco cross-encoder（CPU）  リランク
  ④ generate_answer()→ 社内API（HEAVY_MODEL）       回答生成
最終回答（＋参照文書）
```

- ローカルモデルはCPU動作・オフライン完結。社内APIは①④のみで使用。
- `db/`（ChromaDB）と `docs/` はGit管理外。各PCで `--ingest` 再構築。
