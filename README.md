# pdf2epub

扫描版 PDF → 精排 EPUB：OCR + 校对 + 注释 + 排版一条龙。

专为中文扫描书籍设计，支持竖排/横排、繁简转换、Kindle 脚注弹窗。

## 工作流

```
PDF → 页面渲染 → Gemini OCR → 校对修正 → 注释/札记 → epub_generator 精排 → EPUB
         ↓              ↓           ↓              ↓
      pages/        ocr_cache/   fixes.json    annotations.json
      (JPEG)         (JSON)                    endnotes.json
```

每一步独立、可缓存、可断点续传。

## 安装

```bash
pip install -e .
```

## 使用

### 1. OCR

```bash
# Gemini OCR（ZenMux）
pdf2epub-ocr book.pdf --engine gemini --api zenmux --model gemini-2.5-flash

# 竖排繁体
pdf2epub-ocr book.pdf --layout vertical --skip-pages "1-5"

# 横排简体
pdf2epub-ocr book.pdf --layout horizontal

# GLM-OCR（本地，免费）
pdf2epub-ocr book.pdf --engine glm
```

### 2. 生成 EPUB

```bash
# 基础版
pdf2epub-build .pdf2epub/book/ocr_cache -o book.epub --title "书名" --author "作者" --t2s

# 带封面
pdf2epub-build .pdf2epub/book/ocr_cache -o book.epub --cover cover.jpg

# 带注释和章末札记
pdf2epub-build .pdf2epub/book/ocr_cache -o book.epub \
  --annotations annotations.json --endnotes endnotes.json --t2s
```

### 3. 校对

```bash
# 检查缓存完整性
pdf2epub-proof check .pdf2epub/book/ocr_cache .pdf2epub/book/pages

# 应用修正
pdf2epub-proof fix .pdf2epub/book/ocr_cache fixes.json
```

### 4. 注释

```bash
# 生成注释模板
python -m pdf2epub.annotate template .pdf2epub/book/ocr_cache -o annotations/

# 验证触发词
python -m pdf2epub.annotate validate annotations.json .pdf2epub/book/ocr_cache
```

## API 预设

| 名称 | 端点 | 格式 | 适合 |
|------|------|------|------|
| `zenmux` | ZenMux Pro | OpenAI | 稳定快速 |
| `52youxi` | 52youxi | Google | gemini-3-flash |

## 注释格式

**脚注**（Kindle 弹窗）：
```json
{
  "第一章": [
    {"trigger": "流亡中学", "note": "抗战期间沦陷区中学迁往后方继续办学..."}
  ]
}
```

**章末札记**：
```json
{
  "第一章": "王鼎钧写故乡，不是一般的乡愁抒情，而是把兰陵放在两千年历史纵深中审视..."
}
```

## 项目结构

```
pdf2epub/
├── pyproject.toml
├── README.md
├── pdf2epub/
│   ├── __init__.py
│   ├── ocr.py          # PDF渲染 + Gemini/GLM OCR + 缓存
│   ├── epub.py          # 章节检测 + epub_generator 排版
│   ├── proofread.py     # 校对修正 + 完整性检查
│   └── annotate.py      # 注释模板 + 验证
└── skill.md             # Claude Code skill 入口
```
