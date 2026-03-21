#!/usr/bin/env python3
"""注释模块：生成脚注 + 章末札记

用法：
  1. 准备注释 JSON（手写或 LLM 生成）
  2. 调用 epub.build_epub() 时传入 annotations 和 endnotes 参数

注释 JSON 格式：
{
    "第一章": [
        {"trigger": "流亡中学", "note": "抗战期间，沦陷区中学随师生迁往后方..."},
        {"trigger": "胶济铁路", "note": "青岛至济南铁路，1904年通车..."}
    ]
}

章末札记 JSON 格式：
{
    "第一章": "王鼎钧写故乡，不是一般的乡愁抒情...",
    "第二章": "吾家一章是中国传统家族的缩影..."
}
"""

import argparse
import json
from pathlib import Path

from .epub import load_ocr_cache, split_chapters


def generate_annotation_template(
    cache_dir: Path,
    output_path: Path,
    skip_pages: set[int] | None = None,
    chapter_pattern: str | None = None,
):
    """从 OCR 缓存生成注释模板 JSON（空壳，供填写）"""
    ocr = load_ocr_cache(cache_dir, skip_pages)
    chapters = split_chapters(ocr, chapter_pattern)

    annotations = {}
    endnotes = {}

    for ch in chapters:
        title = ch["title"]
        annotations[title] = [
            {"trigger": "【待填写触发词】", "note": "【待填写注释内容】"}
        ]
        endnotes[title] = "【待填写章末札记】"

    with open(output_path / "annotations.json", "w", encoding="utf-8") as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)

    with open(output_path / "endnotes.json", "w", encoding="utf-8") as f:
        json.dump(endnotes, f, ensure_ascii=False, indent=2)

    print(f"✓ 模板已生成:")
    print(f"  注释: {output_path / 'annotations.json'} ({len(chapters)} 章)")
    print(f"  札记: {output_path / 'endnotes.json'} ({len(chapters)} 章)")


def validate_annotations(annotations_path: Path, cache_dir: Path, skip_pages: set[int] | None = None):
    """验证注释中的 trigger 是否能在原文中找到"""
    with open(annotations_path) as f:
        annotations = json.load(f)

    ocr = load_ocr_cache(cache_dir, skip_pages)
    full_text = "\n".join(r.get("markdown", "") for r in ocr)

    total = 0
    found = 0
    missing = []

    for chapter_title, annos in annotations.items():
        for anno in annos:
            trigger = anno.get("trigger", "")
            if trigger.startswith("【"):
                continue
            total += 1
            if trigger in full_text:
                found += 1
            else:
                missing.append({"chapter": chapter_title, "trigger": trigger})

    print(f"验证: {found}/{total} 个触发词在原文中找到")
    if missing:
        print("未找到:")
        for m in missing:
            print(f"  [{m['chapter']}] {m['trigger']}")


def main():
    p = argparse.ArgumentParser(description="注释工具")
    sub = p.add_subparsers(dest="cmd")

    # 生成模板
    tmpl = sub.add_parser("template", help="生成注释模板")
    tmpl.add_argument("cache_dir", help="OCR 缓存目录")
    tmpl.add_argument("-o", "--output", required=True, help="输出目录")
    tmpl.add_argument("--skip-pages", default="")
    tmpl.add_argument("--chapter-pattern")

    # 验证注释
    val = sub.add_parser("validate", help="验证注释触发词")
    val.add_argument("annotations", help="注释 JSON")
    val.add_argument("cache_dir", help="OCR 缓存目录")
    val.add_argument("--skip-pages", default="")

    args = p.parse_args()

    def parse_skip(s):
        pages = set()
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                pages.update(range(int(a), int(b) + 1))
            else:
                pages.add(int(part))
        return pages

    if args.cmd == "template":
        skip = parse_skip(args.skip_pages) if args.skip_pages else None
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        generate_annotation_template(Path(args.cache_dir), out, skip, args.chapter_pattern)

    elif args.cmd == "validate":
        skip = parse_skip(args.skip_pages) if args.skip_pages else None
        validate_annotations(Path(args.annotations), Path(args.cache_dir), skip)

    else:
        p.print_help()


if __name__ == "__main__":
    main()
