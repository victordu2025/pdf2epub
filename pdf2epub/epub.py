#!/usr/bin/env python3
"""EPUB 排版模块：OCR 缓存 → epub_generator 精排 EPUB"""

import argparse
import json
import re
from pathlib import Path

import epub_generator as eg


# ─── 加载 OCR 缓存 ──────────────────────────────────────────

def load_ocr_cache(cache_dir: Path, skip_pages: set[int] | None = None) -> list[dict]:
    """加载 OCR 缓存，按页码排序"""
    results = []
    for f in sorted(cache_dir.glob("page_*.json")):
        with open(f, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        if skip_pages and d["page_num"] in skip_pages:
            continue
        results.append(d)
    return results


# ─── 章节检测 ────────────────────────────────────────────────

def split_chapters(ocr_results: list[dict], pattern: str | None = None) -> list[dict]:
    """检测章节边界"""
    if not pattern:
        pattern = r"^第[一二三四五六七八九十百]+[章部篇卷]"

    chapters = []
    current = {"title": "前言", "parts": [], "pages": []}

    for r in ocr_results:
        text = r["markdown"].strip()
        pg = r["page_num"]
        if not text:
            continue

        lines = text.split("\n")
        found = False
        for li, line in enumerate(lines):
            stripped = line.strip()
            if re.match(pattern, stripped) and len(stripped) < 40:
                before = "\n".join(lines[:li]).strip()
                if before:
                    current["parts"].append(before)
                if current["parts"]:
                    current["content"] = "\n\n".join(current["parts"])
                    chapters.append(current)
                after = "\n".join(lines[li + 1:]).strip()
                current = {
                    "title": stripped,
                    "parts": [after] if after else [],
                    "pages": [pg],
                }
                found = True
                break

        if not found:
            current["pages"].append(pg)
            if text:
                current["parts"].append(text)

    if current["parts"]:
        current["content"] = "\n\n".join(current["parts"])
        chapters.append(current)

    chapters = [c for c in chapters if c.get("content", "").strip()]
    return chapters


# ─── 文本后处理 ──────────────────────────────────────────────

def merge_cross_page_breaks(text: str) -> str:
    """合并跨页断句"""
    end_puncts = set("。！？」』）；…—\n")
    paragraphs = text.split("\n\n")
    merged = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if merged:
            prev = merged[-1]
            if (prev[-1] not in end_puncts
                and len(para) > 5
                and not re.match(r"^第[一二三四五六七八九十]+[章部篇卷]", para)
                and not re.match(r"^[一二三四五六七八九十]+、", para)):
                merged[-1] = prev + para
                continue
        merged.append(para)

    return "\n\n".join(merged)


# ─── 文本 → Chapter ─────────────────────────────────────────

def text_to_chapter(
    text: str,
    annotations: list[dict] | None = None,
    endnote: str | None = None,
) -> eg.Chapter:
    """纯文本 → epub_generator.Chapter，支持脚注和章末札记"""
    text = merge_cross_page_breaks(text)

    # 注释索引
    anno_map = {}
    if annotations:
        for i, a in enumerate(annotations):
            anno_map[a["trigger"]] = (i + 1, a["note"])

    elements = []
    footnotes = []
    used_ids = set()
    fid_counter = [0]

    def annotate(para: str) -> list:
        if not anno_map:
            return [para]
        parts = []
        remaining = para
        for trigger, (aid, note) in anno_map.items():
            if trigger in remaining and aid not in used_ids:
                idx = remaining.index(trigger)
                fid_counter[0] += 1
                fid = fid_counter[0]
                used_ids.add(aid)
                parts.append(remaining[:idx + len(trigger)])
                parts.append(eg.Mark(id=fid))
                remaining = remaining[idx + len(trigger):]
                footnotes.append(eg.Footnote(
                    id=fid,
                    contents=[eg.TextBlock(kind=eg.TextKind.BODY, level=0, content=[note])],
                ))
                break
        parts.append(remaining)
        return [p for p in parts if p]

    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        if (len(para) < 20
            and para[-1] not in "。，、；：！？」』）…—"
            and not re.match(r"^「", para)):
            elements.append(eg.TextBlock(kind=eg.TextKind.HEADLINE, level=2, content=[para]))
        else:
            elements.append(eg.TextBlock(kind=eg.TextKind.BODY, level=0, content=annotate(para)))

    # 章末札记
    if endnote:
        elements.append(eg.TextBlock(kind=eg.TextKind.HEADLINE, level=3, content=["读后札记"]))
        for para in endnote.strip().split("\n\n"):
            para = para.strip()
            if para:
                elements.append(eg.TextBlock(kind=eg.TextKind.QUOTE, level=0, content=[para]))

    return eg.Chapter(elements=elements, footnotes=footnotes)


# ─── 构建 EPUB ───────────────────────────────────────────────

def build_epub(
    chapters: list[dict],
    output_path: str,
    title: str = "",
    author: str = "",
    publisher: str = "",
    t2s: bool = False,
    cover_image: str | None = None,
    annotations: dict[str, list[dict]] | None = None,
    endnotes: dict[str, str] | None = None,
):
    """构建精排 EPUB。

    annotations: {章节标题: [{trigger, note}]}
    endnotes: {章节标题: "章末札记文本"}
    """
    cc = None
    if t2s:
        from opencc import OpenCC
        cc = OpenCC("t2s")

    def convert(s: str) -> str:
        return cc.convert(s) if cc else s

    meta = eg.BookMeta(
        title=convert(title),
        authors=[convert(author)] if author else [],
        publisher=convert(publisher) if publisher else None,
    )

    cover_path = None
    if cover_image and Path(cover_image).exists():
        cover_path = Path(cover_image)

    toc_items = []
    for ch in chapters:
        ch_title = convert(ch["title"])
        ch_content = convert(ch.get("content", ""))
        ch_annos = annotations.get(ch["title"], []) if annotations else None
        ch_endnote = endnotes.get(ch["title"]) if endnotes else None
        if ch_endnote:
            ch_endnote = convert(ch_endnote)
        chapter_obj = text_to_chapter(ch_content, ch_annos, ch_endnote)
        toc_items.append(eg.TocItem(
            title=ch_title,
            get_chapter=lambda c=chapter_obj: c,
        ))

    epub_data = eg.EpubData(
        meta=meta,
        chapters=toc_items,
        cover_image_path=cover_path,
    )

    eg.generate_epub(epub_data, Path(output_path), lan="zh")
    size = Path(output_path).stat().st_size / 1024
    print(f"✓ EPUB: {output_path} ({size:.0f} KB, {len(chapters)} 章)")


# ─── CLI ─────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="OCR 缓存 → 精排 EPUB")
    p.add_argument("cache_dir", help="OCR 缓存目录")
    p.add_argument("-o", "--output", required=True, help="输出 EPUB")
    p.add_argument("--title", default="")
    p.add_argument("--author", default="")
    p.add_argument("--publisher", default="")
    p.add_argument("--skip-pages", default="")
    p.add_argument("--chapter-pattern", help="章节正则")
    p.add_argument("--t2s", action="store_true", help="繁→简")
    p.add_argument("--cover", help="封面图片路径")
    p.add_argument("--annotations", help="注释 JSON 文件: {章节标题: [{trigger, note}]}")
    p.add_argument("--endnotes", help="章末札记 JSON 文件: {章节标题: '札记文本'}")
    args = p.parse_args()

    cache_dir = Path(args.cache_dir)
    skip = set()
    if args.skip_pages:
        for part in args.skip_pages.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                skip.update(range(int(a), int(b) + 1))
            else:
                skip.add(int(part))

    ocr = load_ocr_cache(cache_dir, skip)
    print(f"加载: {len(ocr)} 页")

    chapters = split_chapters(ocr, args.chapter_pattern)
    for ch in chapters:
        print(f"  · {ch['title']}  ({len(ch.get('content', ''))} 字)")

    annos = None
    if args.annotations:
        with open(args.annotations) as f:
            annos = json.load(f)

    endnotes = None
    if args.endnotes:
        with open(args.endnotes) as f:
            endnotes = json.load(f)

    build_epub(
        chapters, args.output,
        title=args.title, author=args.author, publisher=args.publisher,
        t2s=args.t2s, cover_image=args.cover,
        annotations=annos, endnotes=endnotes,
    )


if __name__ == "__main__":
    main()
