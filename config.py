# ===== バックエンド選択（1行だけ書き換えて切り替える） =====
# BACKEND = "aslead_chatbot"  # 会社（aslead chatbot API経由）
# BACKEND = "ollama"          # 自宅（Ollama）
BACKEND = "llama_server"    # 自宅（llama-server）

# ===== aslead chatbot APIサーバー（会社用） =====
ASLEAD_BASE_URL    = "http://localhost:XXXX"   # TODO: API担当者が記入
ASLEAD_LIGHT_MODEL = "model-light"              # TODO: API担当者が記入
ASLEAD_HEAVY_MODEL = "model-heavy"              # TODO: API担当者が記入
ASLEAD_TMP_FILE    = "./tmp_prompt.txt"

# ===== Ollama（自宅用） =====
OLLAMA_BASE_URL       = "http://localhost:11434"
OLLAMA_LIGHT_MODEL    = "qwen3.5:0.8b"
OLLAMA_HEAVY_MODEL    = "qwen3.5:9b"

# ===== llama-server（自宅用） =====
# 起動コマンド（PowerShellで2つ別ウィンドウ）:
#   ポート8080 LIGHT: C:\Users\hassy\llama.cpp\llama-server.exe -m "C:\Users\hassy\.lmstudio\models\lmstudio-community\Qwen3-0.6B-GGUF\Qwen3-0.6B-Q8_0.gguf" --port 8080 -ngl 99
#   ポート8081 HEAVY: C:\Users\hassy\llama.cpp\llama-server.exe -m "C:\Users\hassy\.lmstudio\models\lmstudio-community\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_M.gguf" --port 8081 -ngl 99
LLAMA_LIGHT_BASE_URL  = "http://localhost:8080"
LLAMA_HEAVY_BASE_URL  = "http://localhost:8081"
LLAMA_MODEL_NAME      = "local"  # llama-serverはモデル名を無視する

# ===== ローカルモデル（共通） =====
EMBED_MODEL  = "intfloat/multilingual-e5-small"
RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# ===== パス（共通） =====
DOCS_DIR = "./docs"
DB_DIR   = "./db"

# ===== RAGパラメーター（共通） =====
TOP_K_SEARCH   = 10
TOP_K_RERANK   = 3
QUERY_EXPAND_N = 3

# ===== pipeline.py が参照する統合エイリアス（BACKEND に応じて自動解決） =====
if BACKEND == "ollama":
    API_BASE_URL = OLLAMA_BASE_URL
    LIGHT_MODEL  = OLLAMA_LIGHT_MODEL
    HEAVY_MODEL  = OLLAMA_HEAVY_MODEL
    TMP_FILE     = None
elif BACKEND == "llama_server":
    API_BASE_URL = LLAMA_LIGHT_BASE_URL  # デフォルト（get_client()内で使い分け）
    # llama-serverはモデル名を無視するため、LIGHT/HEAVYのポート振り分け識別子に流用。
    # 同一値だと api_client がHEAVYを常にLIGHTポートへ誤送するため必ず別値にする。
    LIGHT_MODEL  = "light"
    HEAVY_MODEL  = "heavy"
    TMP_FILE     = None
else:  # "aslead_chatbot"
    API_BASE_URL = ASLEAD_BASE_URL
    LIGHT_MODEL  = ASLEAD_LIGHT_MODEL
    HEAVY_MODEL  = ASLEAD_HEAVY_MODEL
    TMP_FILE     = ASLEAD_TMP_FILE
