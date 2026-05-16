"""コマンドラインインターフェース

使い方:
    python cli.py "有給休暇の申請方法は？"
    python cli.py --ingest
    python cli.py --ingest --docs ./my_docs
"""
import argparse
import sys
from pathlib import Path

import config


def cmd_ingest(docs_dir: str) -> None:
    from ingest import ingest
    if not Path(docs_dir).exists():
        print(f"エラー: docs フォルダが見つかりません: {docs_dir}")
        sys.exit(1)
    ingest(docs_dir=docs_dir)


def cmd_query(question: str) -> None:
    from pipeline import run
    result = run(question)

    print()
    print("【回答】")
    print(result["answer"])

    if result["sources"]:
        print()
        print("【参照文書】")
        for src in result["sources"]:
            name = Path(src["file"]).name
            if "slide" in src:
                print(f"  - {name}（スライド {src['slide']}）")
            elif "page" in src:
                print(f"  - {name}（{src['page']} ページ）")
            else:
                print(f"  - {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="社内文書QE-RAG検索システム")
    parser.add_argument("question", nargs="?", help="質問文")
    parser.add_argument("--ingest", action="store_true", help="文書をインデックス化する")
    parser.add_argument(
        "--docs",
        default=config.DOCS_DIR,
        help=f"文書フォルダのパス（デフォルト: {config.DOCS_DIR}）",
    )
    args = parser.parse_args()

    if args.ingest:
        cmd_ingest(args.docs)
    elif args.question:
        cmd_query(args.question)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
