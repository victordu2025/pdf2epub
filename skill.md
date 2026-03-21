---
name: pdf2epub
description: 扫描版 PDF → 精排 EPUB（Gemini OCR + 校对 + 注释 + epub_generator 排版）
trigger: PDF转EPUB、扫描版转电子书、OCR转书
---

# /pdf2epub

扫描版 PDF → 精排 EPUB 一条龙。支持竖排/横排、繁简转换、脚注弹窗、章末札记。

## 项目路径

`~/Desktop/自媒体创作/pdf2epub/`

## 快速使用

```bash
cd ~/Desktop/自媒体创作/pdf2epub

# 1. OCR（Gemini + ZenMux）
python -m pdf2epub.ocr book.pdf --layout vertical --skip-pages "1-5"

# 2. 生成 EPUB
python -m pdf2epub.epub .pdf2epub/book/ocr_cache -o book.epub --title "书名" --author "作者" --t2s

# 3. 校对
python -m pdf2epub.proofread check .pdf2epub/book/ocr_cache .pdf2epub/book/pages
python -m pdf2epub.proofread fix .pdf2epub/book/ocr_cache fixes.json

# 4. 注释版
python -m pdf2epub.epub .pdf2epub/book/ocr_cache -o book_注释版.epub \
  --annotations annotations.json --endnotes endnotes.json --t2s
```

## API 切换

- `--api zenmux`：ZenMux Pro（默认，稳定）
- `--api 52youxi`：52youxi bak 端点（gemini-3-flash）

## 注意事项

- 竖排繁体用 `--layout vertical`，横排用 `--layout horizontal`
- OCR 缓存逐页存储，空响应不缓存，断点续传
- 生成 EPUB 前先 `proofread check` 确认缓存完整
- 封面：`--cover` 传入封面图片路径
- 繁→简：`--t2s`
