#!/usr/bin/env python3
"""OCR 模块：PDF 页面渲染 + 多引擎 OCR（Gemini / GLM）+ 断点续传缓存"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from pypdfium2 import PdfDocument

# 清除代理（52youxi / ZenMux 直连）
for _k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(_k, None)

# ─── OCR Prompt ──────────────────────────────────────────────

PROMPT_VERTICAL_CJK = """\
这是一页竖排繁体中文书籍的扫描图。请完整提取页面上的所有文字。
要求：
1. 按原文顺序输出（竖排从右到左阅读）
2. 保留原始段落分隔（用空行分段）
3. 保持繁体原文，不要转简体
4. 忽略页眉页脚的页码和章节标题
5. 如果页面包含插图/照片，用 [插图] 标记其位置
6. 只输出文字内容，不要任何解释或标注"""

PROMPT_HORIZONTAL_CJK = """\
这是一页横排中文书籍的扫描图。请完整提取页面上的所有文字。
要求：
1. 按原文顺序输出
2. 保留原始段落分隔（用空行分段）
3. 保持原文字体（繁体/简体），不要转换
4. 忽略页眉页脚的页码
5. 如果页面包含插图/照片，用 [插图] 标记其位置并描述图片内容
6. 只输出文字内容，不要任何解释或标注"""


# ─── PDF 渲染 ────────────────────────────────────────────────

def render_pages(
    pdf_path: str,
    output_dir: Path,
    scale: int = 2,
    skip_pages: set[int] | None = None,
) -> list[Path]:
    """将 PDF 逐页渲染为 JPEG"""
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = PdfDocument(pdf_path)
    total = len(doc)
    image_paths = []
    rendered = 0

    for i in range(total):
        page_num = i + 1
        if skip_pages and page_num in skip_pages:
            continue
        out_path = output_dir / f"page_{page_num:04d}.jpg"
        if out_path.exists():
            image_paths.append(out_path)
            continue
        page = doc[i]
        bitmap = page.render(scale=scale)
        img = bitmap.to_pil()
        img.save(str(out_path), "JPEG", quality=90)
        image_paths.append(out_path)
        rendered += 1
        print(f"\r  渲染页面: {page_num}/{total}", end="", flush=True)

    cached = len(image_paths) - rendered
    print(f"\r  渲染完成: {len(image_paths)} 页"
          + (f" (新渲染 {rendered}, 缓存 {cached})" if cached else "")
          + " " * 10)
    return image_paths


# ─── Gemini OCR ──────────────────────────────────────────────

def gemini_ocr_page(
    img_path: Path,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str = PROMPT_VERTICAL_CJK,
    api_format: str = "openai",
) -> str:
    """用 Gemini Vision API 识别单页"""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    proxies = {"http": None, "https": None}

    if api_format == "openai":
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ]}],
            "max_tokens": 4096,
            "temperature": 0.1,
        }
    else:  # google native
        url = f"{base_url}/v1/models/{model}:generateContent"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
            ]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
        }

    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, proxies=proxies, timeout=180)
            r.raise_for_status()
            break
        except Exception:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise

    resp = r.json()
    try:
        if api_format == "openai":
            return resp["choices"][0]["message"]["content"]
        else:
            return resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return ""


# ─── GLM OCR ────────────────────────────────────────────────

def glm_ocr_page(img_path: Path) -> tuple[str, list]:
    """用 GLM-OCR 识别单页"""
    from glmocr import GlmOcr
    ocr = GlmOcr()
    result = ocr.parse(str(img_path))
    md = result.markdown_result or ""
    jr = result.json_result if hasattr(result, "json_result") else []
    return md, jr


# ─── 批量 OCR（带缓存）────────────────────────────────────

def ocr_pages(
    image_paths: list[Path],
    cache_dir: Path,
    delay: float = 1.0,
    engine: str = "gemini",
    gemini_config: dict | None = None,
) -> list[dict]:
    """逐页 OCR，结果缓存到本地 JSON。空响应不缓存。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = []
    total = len(image_paths)
    cached_count = 0
    failed_count = 0

    for idx, img_path in enumerate(image_paths):
        page_num = int(img_path.stem.split("_")[1])
        cache_file = cache_dir / f"page_{page_num:04d}.json"

        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append(data)
            cached_count += 1
            continue

        try:
            if engine == "gemini" and gemini_config:
                md = gemini_ocr_page(
                    img_path,
                    api_key=gemini_config["api_key"],
                    base_url=gemini_config["base_url"],
                    model=gemini_config["model"],
                    prompt=gemini_config.get("prompt", PROMPT_VERTICAL_CJK),
                    api_format=gemini_config.get("api_format", "openai"),
                )
                data = {"page_num": page_num, "markdown": md, "json_result": []}
            else:
                md, jr = glm_ocr_page(img_path)
                data = {"page_num": page_num, "markdown": md, "json_result": jr}
        except Exception as e:
            print(f"\n  ⚠ 第 {page_num} 页 OCR 失败: {e}")
            data = {"page_num": page_num, "markdown": "", "json_result": []}
            failed_count += 1

        # 空响应不缓存
        if data.get("markdown", "").strip():
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        results.append(data)
        done = idx + 1 - cached_count
        print(
            f"\r  OCR: {idx + 1}/{total} (API {done}, 缓存 {cached_count})",
            end="", flush=True,
        )

        if delay > 0 and idx < total - 1:
            time.sleep(delay)

    status = f"  OCR 完成: {total} 页 (缓存 {cached_count}"
    if failed_count:
        status += f", 失败 {failed_count}"
    status += ")"
    print(f"\r{status}" + " " * 20)
    return results


# ─── CLI ─────────────────────────────────────────────────────

API_PRESETS = {
    "zenmux": {
        "api_key": "sk-ss-v1-2faa325ac5e9958fb95ba6ddc080a9f9bf66c5d9d41e62b7da2c83959dca5851",
        "base_url": "https://zenmux.ai/api/v1",
        "api_format": "openai",
    },
    "52youxi": {
        "api_key": "sk-qKPwfej8yOGxVDQ4lHkAdXGuQUEQwmKL4b3kK881CFirLF67",
        "base_url": "http://bak.52youxi.cc:3000",
        "api_format": "google",
    },
}


def parse_page_range(s: str) -> set[int]:
    pages: set[int] = set()
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


def main():
    p = argparse.ArgumentParser(description="PDF → OCR 缓存（逐页图片 + Gemini/GLM）")
    p.add_argument("pdf", help="输入 PDF")
    p.add_argument("-o", "--work-dir", help="工作目录（默认 PDF 旁 .pdf2epub/）")
    p.add_argument("--skip-pages", default="", help="跳过页码: '1-3,200'")
    p.add_argument("--scale", type=int, default=2, help="渲染缩放")
    p.add_argument("--engine", choices=["gemini", "glm"], default="gemini")
    p.add_argument("--api", choices=list(API_PRESETS.keys()), default="zenmux", help="API 预设")
    p.add_argument("--model", default="gemini-2.5-flash", help="模型名")
    p.add_argument("--layout", choices=["vertical", "horizontal"], default="vertical", help="版面方向")
    p.add_argument("--delay", type=float, default=1.0, help="API 间隔秒数")

    args = p.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"错误: {pdf_path}")
        sys.exit(1)

    work = Path(args.work_dir) if args.work_dir else pdf_path.parent / ".pdf2epub" / pdf_path.stem
    skip = parse_page_range(args.skip_pages) if args.skip_pages else set()

    print(f"PDF: {pdf_path}")
    print(f"引擎: {args.engine} ({args.api}/{args.model})")

    images = render_pages(str(pdf_path), work / "pages", args.scale, skip)

    gemini_config = None
    if args.engine == "gemini":
        preset = API_PRESETS[args.api]
        prompt = PROMPT_VERTICAL_CJK if args.layout == "vertical" else PROMPT_HORIZONTAL_CJK
        gemini_config = {**preset, "model": args.model, "prompt": prompt}

    ocr_pages(images, work / "ocr_cache", args.delay, args.engine, gemini_config)


if __name__ == "__main__":
    main()
