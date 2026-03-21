#!/usr/bin/env python3
"""校对模块：读取 OCR 缓存，应用修正"""

import argparse
import json
import os
from pathlib import Path


def apply_fixes(cache_dir: Path, fixes: list[dict]) -> int:
    """应用修正列表到 OCR 缓存。

    fixes: [{page, error, correction}] 或 [{page, old, new}]
    返回成功修正数。
    """
    applied = 0
    for fix in fixes:
        pg = fix.get("page")
        old = fix.get("error") or fix.get("old", "")
        new = fix.get("correction") or fix.get("new", "")
        if not (pg and old and new):
            continue

        f = cache_dir / f"page_{pg:04d}.json"
        if not f.exists():
            print(f"  - p{pg}: 文件不存在")
            continue

        with open(f, "r", encoding="utf-8") as fh:
            d = json.load(fh)

        md = d.get("markdown", "")
        if old in md:
            d["markdown"] = md.replace(old, new, 1)
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
            applied += 1
            print(f"  ✓ p{pg}: {old} → {new}")
        else:
            print(f"  - p{pg}: 未找到「{old}」")

    return applied


def check_empty_pages(cache_dir: Path, pages_dir: Path) -> list[int]:
    """检查缓存完整性，返回缺失/空白的页码列表"""
    page_files = sorted(pages_dir.glob("page_*.jpg"))
    missing = []

    for pf in page_files:
        pg = int(pf.stem.split("_")[1])
        cache_file = cache_dir / f"page_{pg:04d}.json"

        if not cache_file.exists():
            missing.append(pg)
            continue

        with open(cache_file, "r", encoding="utf-8") as f:
            d = json.load(f)
        if len(d.get("markdown", "").strip()) < 5:
            missing.append(pg)

    return missing


def main():
    p = argparse.ArgumentParser(description="校对工具")
    sub = p.add_subparsers(dest="cmd")

    # 应用修正
    fix_p = sub.add_parser("fix", help="应用修正 JSON")
    fix_p.add_argument("cache_dir", help="OCR 缓存目录")
    fix_p.add_argument("fixes_json", help="修正 JSON 文件")

    # 检查完整性
    chk_p = sub.add_parser("check", help="检查缓存完整性")
    chk_p.add_argument("cache_dir", help="OCR 缓存目录")
    chk_p.add_argument("pages_dir", help="页面图片目录")

    args = p.parse_args()

    if args.cmd == "fix":
        with open(args.fixes_json) as f:
            fixes = json.load(f)
        n = apply_fixes(Path(args.cache_dir), fixes)
        print(f"\n修正了 {n}/{len(fixes)} 处")

    elif args.cmd == "check":
        missing = check_empty_pages(Path(args.cache_dir), Path(args.pages_dir))
        if missing:
            print(f"缺失/空白: {len(missing)} 页")
            print(f"页码: {missing[:20]}{'...' if len(missing) > 20 else ''}")
        else:
            print("✓ 全部完整")

    else:
        p.print_help()


if __name__ == "__main__":
    main()
