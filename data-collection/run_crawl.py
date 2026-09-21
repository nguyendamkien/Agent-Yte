"""CLI để chạy crawler thu thập dữ liệu y tế tiếng Việt.

Ví dụ:
    python run_crawl.py --source vinmec --limit 30
    python run_crawl.py --source medlatec --limit 50
    python run_crawl.py --source all --limit 20
"""

import argparse
import json
import sys
from pathlib import Path

# Đảm bảo in được tiếng Việt trên console Windows (mặc định dùng cp1252).
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

from config import DATA_DIR
from crawlers import medlatec, suckhoedoisong, vinmec
from utils import save_jsonl


def main():
    parser = argparse.ArgumentParser(description="Thu thập dữ liệu y tế tiếng Việt")
    parser.add_argument(
        "--source",
        choices=["vinmec", "medlatec", "suckhoedoisong", "all"],
        default="all",
        help="Nguồn dữ liệu cần crawl (mặc định: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Số bài tối đa mỗi nguồn (mặc định: 20; dùng để test trước khi crawl lớn)",
    )
    parser.add_argument(
        "--letters",
        default="abcdefghijklmnopqrstuvwxyz",
        help="Chỉ dùng cho Vinmec: các chữ cái muốn crawl, vd. 'abc' (mặc định: toàn bộ a-z)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DATA_DIR),
        help="Thư mục lưu file kết quả (mặc định: data-collection/data)",
    )
    args = parser.parse_args()
    if args.limit == 0:
        args.limit = None  # 0 = không giới hạn

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_records = []

    if args.source in ("vinmec", "all"):
        records = vinmec.run(limit=args.limit, letters=args.letters)
        save_jsonl(records, output_dir / "vinmec.jsonl")
        all_records.extend(records)

    if args.source in ("medlatec", "all"):
        records = medlatec.run(limit=args.limit)
        save_jsonl(records, output_dir / "medlatec.jsonl")
        all_records.extend(records)

    if args.source in ("suckhoedoisong", "all"):
        records = suckhoedoisong.run(limit=args.limit)
        save_jsonl(records, output_dir / "suckhoedoisong.jsonl")
        all_records.extend(records)

    if args.source == "all":
        save_jsonl(all_records, output_dir / "combined.jsonl")

    print(f"\nHoàn tất. Tổng số tài liệu thu thập: {len(all_records) if args.source == 'all' else len(records)}")


if __name__ == "__main__":
    main()
