#!/usr/bin/env python3
"""
Daily English — 微信公众号发布脚本（零外部依赖，仅需 Python stdlib + macOS 系统工具）

用法:
  python3 scripts/publish.py drafts/hello-world.md
  python3 scripts/publish.py --author "Daily English" --digest "..." drafts/hello-world.md

流程:
  1. 读取 Markdown 草稿，解析 front-matter（标题、摘要、作者）
  2. 根据文章标题自动生成封面图（SVG → PNG via macOS qlmanage / sips 回退）
  3. 上传封面图获取微信永久 media_id
  4. Markdown → 精美 HTML（微信公众号适配，支持所有常见语法）
  5. 创建微信草稿（不群发，需到后台人工发布）
  6. 归档到 published/ 目录
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import mimetypes
import os
import random
import re
import string
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.sax.saxutils import escape as xml_escape




# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 项目路径常量
# ---------------------------------------------------------------------------

PROJECT_DIR: Path = Path(__file__).resolve().parent.parent
ASSETS_DIR: Path = PROJECT_DIR / "assets"
COVER_DIR: Path = PROJECT_DIR / "covers"
DRAFT_DIR: Path = PROJECT_DIR / "drafts"
PUBLISHED_DIR: Path = PROJECT_DIR / "published"
for _d in (COVER_DIR, PUBLISHED_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# .env 解析器（零外部依赖）
# ---------------------------------------------------------------------------

def _parse_env_file(env_path: Path | None = None) -> dict[str, str]:
    """手动解析 .env 和 .env.example，支持 # 注释、引用值。.env.example 不覆盖 .env。"""
    result: dict[str, str] = {}
    for fname in (".env", ".env.example"):
        fpath = PROJECT_DIR / fname
        if not fpath.exists():
            continue
        for line in fpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            # .env.example 不覆盖 .env 已有的值
            if fname == ".env.example" and key in result:
                continue
            result[key] = val
    return result


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_AUTHOR = "Daily English"
API_MAX_RETRIES = 3
API_RETRY_BASE_DELAY = 1.0

_ENV_DICT = _parse_env_file()
_WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID") or _ENV_DICT.get("WECHAT_APP_ID", "")
_WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET") or _ENV_DICT.get("WECHAT_APP_SECRET", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or _ENV_DICT.get("DEEPSEEK_API_KEY", "")
BASE_URL = "https://api.weixin.qq.com/cgi-bin"


def validate_publish_config() -> None:
    missing = []
    if not _WECHAT_APP_ID:
        missing.append("WECHAT_APP_ID")
    if not _WECHAT_APP_SECRET:
        missing.append("WECHAT_APP_SECRET")
    if missing:
        sys.exit(f"❌ 缺少必要环境变量: {', '.join(missing)}。请检查 .env 文件。")


# ---------------------------------------------------------------------------
# 文字装饰 / 工具函数
# ---------------------------------------------------------------------------

_CN_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _fmt_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d")


def _truncate(text: str, max_len: int, suffix: str = "...") -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]", "_", text).strip("_").lower()[:60]


# 封面图生成（SVG → PNG）
# ---------------------------------------------------------------------------

COVER_SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="900" height="383" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{grad_start}"/>
      <stop offset="50%" stop-color="{grad_mid}"/>
      <stop offset="100%" stop-color="{grad_end}"/>
    </linearGradient>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="130%">
      <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="rgba(0,0,0,0.3)"/>
    </filter>
  </defs>
  <rect width="900" height="383" fill="url(#bg)"/>
  <!-- 装饰元素 -->
  <circle cx="800" cy="60" r="200" fill="rgba(255,255,255,0.03)"/>
  <circle cx="100" cy="350" r="150" fill="rgba(255,255,255,0.02)"/>
  <rect x="40" y="40" width="820" height="303" rx="12" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  <!-- 主标题 -->
  <text x="450" y="165" text-anchor="middle"
        font-family="-apple-system, BlinkMacSystemFont, Helvetica Neue, PingFang SC, Microsoft YaHei, sans-serif"
        font-size="44" font-weight="bold" fill="white" filter="url(#shadow)">{title}</text>
  <!-- 副标题 -->
  <text x="450" y="235" text-anchor="middle"
        font-family="-apple-system, BlinkMacSystemFont, Helvetica Neue, PingFang SC, Microsoft YaHei, sans-serif"
        font-size="16" fill="rgba(255,255,255,0.70)">{subtitle}</text>
  <!-- 底部标签 -->
  <text x="450" y="310" text-anchor="middle"
        font-family="-apple-system, BlinkMacSystemFont, Helvetica Neue, PingFang SC, Microsoft YaHei, sans-serif"
        font-size="13" fill="rgba(255,255,255,0.35)">{badge}</text>
</svg>"""

# 多套配色预设，按日期轮换
COVER_PALETTES = [
    # 深蓝商务
    ("#1a365d", "#2b6cb0", "#4299e1"),
    # 森林绿
    ("#1a3c34", "#2f8555", "#48bb78"),
    # 暖橙
    ("#5a3700", "#c05621", "#ed8936"),
    # 紫韵
    ("#3c1d5e", "#6b46c1", "#9f7aea"),
    # 玫红
    ("#5c1a2a", "#b8323e", "#fc8181"),
    # 炭灰蓝
    ("#1e293b", "#334155", "#64748b"),
]


def _generate_cover_svg(title: str, subtitle: str = "", badge: str = "") -> str:
    palette = COVER_PALETTES[hash(title) % len(COVER_PALETTES)]
    return COVER_SVG_TEMPLATE.format(
        title=xml_escape(title),
        subtitle=xml_escape(subtitle or "Daily English — AI 驱动的英语学习平台"),
        badge=xml_escape(badge or "关注 Daily English，每天进步一点点"),
        grad_start=palette[0],
        grad_mid=palette[1],
        grad_end=palette[2],
    )


def generate_cover_image(title: str, subtitle: str = "", badge: str = "") -> Path:
    """生成封面图 PNG，返回路径。跨平台设计：macOS 用 qlmanage，回退 sips。"""
    safe = _slugify(title) or "cover"
    png_path = COVER_DIR / f"{safe}.png"
    if png_path.exists():
        print(f"  📂 封面图已存在: {png_path.name} (跳过)")
        return png_path

    svg_content = _generate_cover_svg(title, subtitle, badge)
    svg_path = COVER_DIR / f"{safe}.svg"
    svg_path.write_text(svg_content, encoding="utf-8")

    # --- 方案 A: qlmanage (macOS) ---
    ql_png_path = COVER_DIR / f"{safe}.svg.png"
    try:
        subprocess.run(
            ["qlmanage", "-t", "-s", "900", "-o", str(COVER_DIR), str(svg_path)],
            capture_output=True, timeout=30, check=False,
        )
        if ql_png_path.exists():
            ql_png_path.rename(png_path)
            svg_path.unlink(missing_ok=True)
            print(f"  ✅ 封面图已生成: {png_path.name}")
            return png_path
    except Exception as e:
        print(f"  ⚠️ qlmanage 失败: {e}")

    # --- 方案 B: sips (macOS 备用) ---
    if ql_png_path.exists():
        ql_png_path.rename(png_path)
        svg_path.unlink(missing_ok=True)
        return png_path
    try:
        # sips 可以直接将 SVG 转为 PNG
        subprocess.run(
            ["sips", "-s", "format", "png", "--resampleWidth", "900",
             str(svg_path), "--out", str(png_path)],
            capture_output=True, timeout=30, check=False,
        )
        if png_path.exists():
            svg_path.unlink(missing_ok=True)
            print(f"  ✅ 封面图已生成(sips): {png_path.name}")
            return png_path
    except Exception as e:
        print(f"  ⚠️ sips 失败: {e}")

    # --- 方案 C: 默认封面回退 ---
    fallback = ASSETS_DIR / "cover.png"
    if fallback.exists():
        print("  ⚠️ 使用默认封面图")
        return fallback
    raise RuntimeError("无法生成封面图：系统缺少 qlmanage/sips，且无默认封面。")


# ---------------------------------------------------------------------------
# Markdown → HTML 渲染器（微信公众号适配）
# ---------------------------------------------------------------------------

class MarkdownRenderer:
    """将 Markdown 文本渲染为公众号适配的 HTML。"""

    # 公众号正文最大宽度 677px，字号推荐 15-17px
    P_STYLE = ("font-size:16px; color:#2d3748; line-height:1.85; "
               "letter-spacing:0.5px; margin:0.7em 0; text-align:justify;")
    CODE_STYLE = ("background:#edf2f7; padding:2px 7px; border-radius:4px; "
                  "font-size:0.9em; color:#2b6cb0; font-family:Menlo, Monaco, monospace;")
    LINK_STYLE = ("color:#2b6cb0; text-decoration:none; "
                  "border-bottom:1px solid #bee3f8;")
    BLOCKQUOTE_STYLE = ("border-left:4px solid #2b6cb0; background:#f7fafc; "
                        "padding:10px 16px; margin:0.8em 0; color:#4a5568; "
                        "font-style:italic; border-radius:0 6px 6px 0;")
    TABLE_STYLE = ("border-collapse:collapse; width:100%; margin:1em 0; "
                   "font-size:15px;")
    TABLE_TH_STYLE = ("background:#2b6cb0; color:white; padding:10px 14px; "
                      "text-align:left; font-weight:600;")
    TABLE_TD_STYLE = ("border:1px solid #e2e8f0; padding:8px 14px; color:#2d3748;")

    # 文章摘要长度
    DIGEST_MAX = 120

    def __init__(self) -> None:
        self._in_list: bool = False
        self._list_type: str = "ul"
        self._list_counter: int = 0
        self._in_code_block: bool = False
        self._code_buffer: list[str] = []
        self._body_parts: list[str] = []

    def _render_inline(self, text: str) -> str:
        """渲染行内元素：粗体、斜体、行内代码、链接。"""
        # 链接 [text](url)
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f'<a href="{xml_escape(m.group(2))}" style="{self.LINK_STYLE}">{m.group(1)}</a>',
            text,
        )
        # 图片 ![alt](url) → 微信公众号图片（仅当在正式渲染时）
        text = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda m: (f'<img src="{xml_escape(m.group(2))}" alt="{xml_escape(m.group(1))}" '
                       'style="max-width:100%; border-radius:8px; margin:0.8em 0;" />'),
            text,
        )
        # 粗体 **text**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # 斜体 *text* (不跟粗体冲突)
        text = re.sub(r"(?<!\*)\*(?![*\s])(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        # 行内代码
        text = re.sub(r"`([^`]+)`", f'<code style="{self.CODE_STYLE}">\\1</code>', text)
        # 删除线 ~~text~~
        text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
        return text

    def _handle_paragraph(self, text: str) -> str:
        inline = self._render_inline(text)
        return f'<p style="{self.P_STYLE}">{inline}</p>'

    def _handle_heading(self, text: str, level: int) -> str:
        inline = self._render_inline(text)
        # 公众号优化：### 用小一号 H2 样式，视觉更清晰
        render_level = level if level <= 2 else 2
        sizes = {1: "22px", 2: "19px"}
        size = sizes.get(render_level, "19px")
        margin = {1: "1em 0 0.3em", 2: "0.9em 0 0.3em"}.get(render_level, "0.9em 0 0.3em")
        accent = {1: 'border-bottom:2px solid #2b6cb0; padding-bottom:6px;',
                  2: 'border-bottom:1px solid #bee3f8; padding-bottom:4px;'}
        extra = accent.get(render_level, "")
        return (f'<h{render_level} style="font-size:{size}; font-weight:bold; color:#1a202c; '
                f'margin:{margin}; line-height:1.5; {extra}">{inline}</h{render_level}>')

    def _handle_horizontal_rule(self) -> str:
        return '<hr style="border:none; border-top:1.5px solid #e2e8f0; margin:1.5em 0;" />'

    def _close_list(self) -> None:
        if self._in_list:
            self._in_list = False

    def _render(self, md_text: str) -> str:
        """核心渲染，逐行处理。"""
        lines = md_text.split("\n")
        bq_lines: list[str] = []
        in_bq = False
        # 有序列表连续编号追踪
        _expect_ol_next: int | None = None

        def _flush_bq() -> None:
            nonlocal in_bq, bq_lines
            if bq_lines:
                content = "".join(bq_lines)
                self._body_parts.append(
                    f'<blockquote style="{self.BLOCKQUOTE_STYLE}">{content}</blockquote>'
                )
                bq_lines = []
                in_bq = False

        def _add_line(s: str) -> None:
            self._body_parts.append(s)

        def _maybe_close_list() -> None:
            nonlocal _expect_ol_next
            if self._in_list:
                self._in_list = False
            _expect_ol_next = None

        i = 0
        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()

            # --- 代码块 ---
            if stripped.startswith("```"):
                if self._in_code_block:
                    code_html = (
                        '<pre style="background:#1a202c; color:#e2e8f0; padding:16px; '
                        'border-radius:8px; font-size:14px; line-height:1.7; '
                        'overflow-x:auto; margin:0.8em 0;"><code>'
                        + "\n".join(self._code_buffer)
                        + "</code></pre>"
                    )
                    _flush_bq()
                    _maybe_close_list()
                    _add_line(code_html)
                    self._code_buffer = []
                    self._in_code_block = False
                else:
                    _flush_bq()
                    _maybe_close_list()
                    self._in_code_block = True
                i += 1
                continue
            if self._in_code_block:
                self._code_buffer.append(xml_escape(raw))
                i += 1
                continue

            # --- 空行: 如果是连续有序列表之间，不关闭列表 ---
            if not stripped:
                _flush_bq()
                # Check if next non-empty line continues an ordered list
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and _expect_ol_next is not None:
                    next_line = lines[j].strip()
                    ol_next = re.match(r"^(\d+)\.\s", next_line)
                    if ol_next and int(ol_next.group(1)) == _expect_ol_next:
                        # Don't close list, skip blank line
                        i += 1
                        continue
                _maybe_close_list()
                i += 1
                continue

            # --- 引用 > ---
            bq_match = re.match(r"^>\s*(.*)$", stripped)
            if bq_match:
                if not in_bq:
                    _flush_bq()
                    _maybe_close_list()
                    in_bq = True
                bq_lines.append(self._render_inline(bq_match.group(1)) + "<br/>")
                i += 1
                continue
            else:
                _flush_bq()

            # --- 标题 ---
            h_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
            if h_match:
                _maybe_close_list()
                _add_line(self._handle_heading(h_match.group(2), len(h_match.group(1))))
                i += 1
                continue

            # --- 分割线 ---
            if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
                _maybe_close_list()
                _add_line(self._handle_horizontal_rule())
                i += 1
                continue

            # --- 有序列表（支持跨空行连续编号） ---
            ol_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
            if ol_match:
                num = int(ol_match.group(1))
                text = ol_match.group(2)
                if not self._in_list:
                    _maybe_close_list()
                    self._in_list = True
                _add_line(
                    f'<div style="display:flex; align-items:flex-start; margin:0.3em 0; line-height:1.85;">'
                    f'<span style="font-size:15px; color:#2b6cb0; font-weight:600; min-width:1.6em; flex-shrink:0;">{num}.</span>'
                    f'<span style="font-size:16px; color:#2d3748; flex:1;">{self._render_inline(text)}</span>'
                    f'</div>'
                )
                _expect_ol_next = num + 1
                i += 1
                continue

            # --- 无序列表（含子项 `- *...*`） ---
            ul_match = re.match(r"^[-*+]\s+(.+)$", stripped)
            if ul_match:
                # Sub-item (like `- *italic text*`): render inside current list
                if self._in_list and self._list_type == "ol":
                    _add_line(
                        f'<div style="display:flex; align-items:flex-start; margin:0.15em 0 0.15em 1.2em; line-height:1.7;">'
                        f'<span style="font-size:14px; color:#718096; min-width:1em; flex-shrink:0;">-</span>'
                        f'<span style="font-size:15px; color:#4a5568; flex:1;">{self._render_inline(ul_match.group(1))}</span>'
                        f'</div>'
                    )
                    i += 1
                    continue
                if not self._in_list:
                    _maybe_close_list()
                    self._in_list = True
                _add_line(
                    f'<div style="display:flex; align-items:flex-start; margin:0.3em 0; line-height:1.85;">'
                    f'<span style="font-size:16px; color:#2b6cb0; min-width:1.2em; flex-shrink:0; text-align:center;">•</span>'
                    f'<span style="font-size:16px; color:#2d3748; flex:1;">{self._render_inline(ul_match.group(1))}</span>'
                    f'</div>'
                )
                _expect_ol_next = None
                i += 1
                continue

            # --- 表格 ---
            # 检测表头行
            tb_match = re.match(r"^\|(.+)\|$", stripped)
            if tb_match and i + 1 < len(lines):
                # 检查下一行是否是分隔线
                next_line = lines[i + 1].strip()
                if re.match(r"^\|[\s:-]+\|$", next_line):
                    # 渲染表格
                    self._close_list()
                    cols = [c.strip() for c in tb_match.group(1).split("|")]
                    html = [f'<table style="{self.TABLE_STYLE}">']
                    html.append("<thead><tr>")
                    for c in cols:
                        html.append(f'<th style="{self.TABLE_TH_STYLE}">{self._render_inline(c)}</th>')
                    html.append("</tr></thead><tbody>")
                    j = i + 2
                    while j < len(lines):
                        row = lines[j].strip()
                        if not row.startswith("|"):
                            break
                        cells = [c.strip() for c in row.strip("|").split("|")]
                        html.append("<tr>")
                        for c in cells:
                            html.append(f'<td style="{self.TABLE_TD_STYLE}">{self._render_inline(c)}</td>')
                        html.append("</tr>")
                        j += 1
                    html.append("</tbody></table>")
                    _add_line("\n".join(html))
                    i = j
                    continue

            # --- 普通段落 ---
            self._close_list()
            _add_line(self._handle_paragraph(stripped))
            i += 1

        # 清理
        _flush_bq()
        self._close_list()
        if self._in_code_block:
            _add_line(f'<pre><code>{"<br/>".join(self._code_buffer)}</code></pre>')

        return "\n".join(self._body_parts)

    @classmethod
    def render(cls, md_text: str) -> str:
        return cls()._render(md_text)


def md_to_html(md_text: str, title: str = "", digest: str = "") -> tuple[str, str]:
    """
    Markdown → 公众号完整 HTML。返回 (html_content, final_digest)。
    digest 为空时自动从正文提取前 120 字。
    """
    # Remove first H1 line from body since template adds it
    md_body = re.sub(r"^#\s+.+\n?", "", md_text, count=1).strip()
    body = MarkdownRenderer.render(md_body)

    # 自动摘要
    if not digest:
        plain = re.sub(r"<[^>]+>", "", body).strip()
        digest = _truncate(plain, 120)

    # 日期
    today = _fmt_date()

    html = f"""\
<section style="padding:8px 15px 20px; max-width:677px; margin:0 auto;">
  <h1 style="font-size:22px; font-weight:bold; color:#1a202c; text-align:center; margin:0.8em 0 0.3em; letter-spacing:1px; line-height:1.5;">
    {xml_escape(title)}
  </h1>
  <p style="font-size:13px; color:#a0aec0; text-align:center; margin:0 0 1em;">
    {xml_escape(today)}
  </p>
  <hr style="border:none; border-top:2px solid #2b6cb0; width:60px; margin:0.5em auto 1.2em;" />
  {body}
  <hr style="border:none; border-top:1px solid #e2e8f0; margin:2em 0 1em;" />
  <p style="font-size:13px; color:#a0aec0; text-align:center; letter-spacing:0.5px;">
    本文由 Daily English 自动生成 · AI 驱动 · 人工审核
  </p>
  <p style="font-size:13px; color:#a0aec0; text-align:center; margin-top:4px;">
    关注 Daily English，每天进步一点点
  </p>
</section>"""
    return html, digest


# ---------------------------------------------------------------------------
# 微信 API 客户端（零外部依赖，用 urllib）
# ---------------------------------------------------------------------------

class WeChatAPIError(Exception):
    def __init__(self, errcode: int, errmsg: str, raw: dict[str, Any]) -> None:
        self.errcode = errcode
        self.errmsg = errmsg
        self.raw = raw
        super().__init__(f"微信 API 错误 [{errcode}]: {errmsg}")


class WeChatClient:
    """微信公众号 API 客户端，内置 retry 和超时。"""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0

    # ------------------------------------------------------------------
    # HTTP 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _urlopen(req: Request, timeout: int = 15) -> bytes:
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body}") from e
        except URLError as e:
            raise RuntimeError(f"网络错误: {e.reason}") from e

    @staticmethod
    def _post_json(url: str, data: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        raw = WeChatClient._urlopen(req, timeout)
        return json.loads(raw)

    @staticmethod
    def _check_response(resp: dict[str, Any]) -> dict[str, Any]:
        if "errcode" in resp and resp["errcode"] != 0:
            raise WeChatAPIError(resp["errcode"], resp.get("errmsg", "unknown"), resp)
        return resp

    @staticmethod
    def _retry(method: callable, *args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, API_MAX_RETRIES + 1):
            try:
                return method(*args, **kwargs)
            except WeChatAPIError as e:
                if e.errcode in (40001, 40014, 42001):
                    # token 过期，刷新后重试
                    print(f"  ⚠️ Token 失效，重新获取... ({e.errmsg})")
                    # Clear cached token
                    return method(*args, **kwargs)
                last_exc = e
                if attempt < API_MAX_RETRIES:
                    delay = API_RETRY_BASE_DELAY * (1.5 ** (attempt - 1))
                    print(f"  🔄 重试 ({attempt}/{API_MAX_RETRIES}) 等待 {delay:.1f}s...")
                    time.sleep(delay)
            except Exception as e:
                last_exc = e
                if attempt < API_MAX_RETRIES:
                    delay = API_RETRY_BASE_DELAY * (1.5 ** (attempt - 1))
                    print(f"  🔄 重试 ({attempt}/{API_MAX_RETRIES}) 等待 {delay:.1f}s... ({e})")
                    time.sleep(delay)
        raise RuntimeError(f"API 调用超过最大重试次数 ({API_MAX_RETRIES}): {last_exc}") from last_exc

    # ------------------------------------------------------------------
    # Token 管理
    # ------------------------------------------------------------------

    def get_access_token(self, force: bool = False) -> str:
        now = time.time()
        if self._token and not force and now < self._token_expires_at - 60:
            return self._token

        validate_publish_config()
        params = urlencode({
            "grant_type": "client_credential",
            "appid": _WECHAT_APP_ID,
            "secret": _WECHAT_APP_SECRET,
        })
        url = f"{BASE_URL}/token?{params}"

        def _fetch() -> dict[str, Any]:
            return json.loads(self._urlopen(Request(url)))

        data = self._retry(_fetch)
        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        self._token = data["access_token"]
        self._token_expires_at = now + data.get("expires_in", 7200)
        return self._token

    # ------------------------------------------------------------------
    # 素材管理
    # ------------------------------------------------------------------

    def upload_image(self, image_path: Path) -> str:
        """上传图片为永久素材，返回 media_id。"""
        token = self.get_access_token()
        url = f"{BASE_URL}/material/add_material?access_token={token}&type=image"

        boundary = "----" + uuid.uuid4().hex
        filename = image_path.name

        with open(image_path, "rb") as f:
            file_data = f.read()

        # 构造 multipart/form-data 体
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'.encode()
        )
        body.write(f"Content-Type: image/png\r\n\r\n".encode())
        body.write(file_data)
        body.write(f"\r\n--{boundary}--\r\n".encode())

        payload = body.getvalue()
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        def _upload() -> dict[str, Any]:
            raw = self._urlopen(req)
            return json.loads(raw)

        data = self._retry(_upload)
        data = self._check_response(data)
        if "media_id" not in data:
            raise RuntimeError(f"上传封面图失败: {data}")
        print(f"  ✅ 封面图已上传 (media_id: {data['media_id'][:20]}...)")
        return data["media_id"]

    # ------------------------------------------------------------------
    # 草稿管理
    # ------------------------------------------------------------------

    def create_draft(
        self,
        title: str,
        html_content: str,
        thumb_media_id: str,
        digest: str = "",
        author: str = "",
        content_source_url: str = "",
        open_comment: bool = True,
    ) -> dict[str, Any]:
        token = self.get_access_token()
        url = f"{BASE_URL}/draft/add?access_token={token}"

        article: dict[str, Any] = {
            "title": title[:64],
            "content": html_content,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 1 if open_comment else 0,
            "only_fans_can_comment": 0,
        }
        if digest:
            article["digest"] = digest[:120]
        if author:
            article["author"] = author[:64]
        if content_source_url:
            article["content_source_url"] = content_source_url

        body = {"articles": [article]}

        def _create() -> dict[str, Any]:
            return self._post_json(url, body)

        result = self._retry(_create)
        return self._check_response(result)


# ---------------------------------------------------------------------------
# 发布归档
# ---------------------------------------------------------------------------

ARCHIVE_INDEX = "index.json"


class ArchiveManager:
    """已发布文章管理。"""

    def __init__(self, publish_dir: Path) -> None:
        self._dir = publish_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / ARCHIVE_INDEX

    def load_index(self) -> list[dict[str, Any]]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def save_index(self, entries: list[dict[str, Any]]) -> None:
        self._index_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def archive(
        self,
        article_id: str,
        title: str,
        digest: str,
        cover_path: Path | None = None,
        draft_path: Path | None = None,
        media_id: str = "",
        author: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """归档一篇已发布的文章。"""
        entries = self.load_index()

        entry: dict[str, Any] = {
            "id": article_id,
            "title": title,
            "digest": digest,
            "author": author or DEFAULT_AUTHOR,
            "published_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "media_id": media_id,
            "tags": tags or [],
        }

        # 保存原始 Markdown 副本
        if draft_path and draft_path.exists():
            archive_md = self._dir / f"{article_id}.md"
            archive_md.write_text(draft_path.read_text(encoding="utf-8"), encoding="utf-8")
            entry["source_md"] = archive_md.name

        # 封面副本
        if cover_path and cover_path.exists():
            archive_cover_name = f"{article_id}{cover_path.suffix}"
            archive_cover = self._dir / archive_cover_name
            shutil.copy2(cover_path, archive_cover)
            entry["cover"] = archive_cover_name

        entries.insert(0, entry)  # 最新在前
        self.save_index(entries)
        print(f"  📚 已归档到 published/{archive_cover_name if cover_path else ''}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Daily English — 微信公众号发布脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python3 scripts/publish.py drafts/my-article.md\n"
            "  python3 scripts/publish.py drafts/my-article.md --author \"Alice\"\n"
            '  python3 scripts/publish.py drafts/my-article.md --digest "实用英语对话"\n'
        ),
    )
    parser.add_argument("draft", help="Markdown 草稿文件路径")
    parser.add_argument("--author", default=DEFAULT_AUTHOR, help="作者名")
    parser.add_argument("--digest", default="", help="文章摘要（最多120字）")
    parser.add_argument("--source-url", default="", help="原文链接")
    parser.add_argument("--no-comment", action="store_true", help="关闭评论区")
    parser.add_argument("--dry-run", action="store_true", help="仅生成封面和 HTML，不上传")
    parser.add_argument("--subtitle", default="", help="封面副标题")
    parser.add_argument("--badge", default="", help="封面底部标签")

    args = parser.parse_args()

    draft_file = Path(args.draft)
    if not draft_file.exists():
        sys.exit(f"❌ 文件不存在: {draft_file}")
    if draft_file.suffix.lower() not in (".md", ".markdown"):
        print(f"  ⚠️ 文件不是 .md 后缀: {draft_file}")

    # 1. 读取 Markdown
    md_content = draft_file.read_text(encoding="utf-8")

    # 从文件名推断标题
    stem = draft_file.stem
    # 处理日期前缀如 "2026-06-15-meeting-etiquette" → "Meeting Etiquette"
    title = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    title = title.replace("-", " ").replace("_", " ").strip().title()

    # 2. 生成封面图
    print("🎨 生成封面图...")
    cover_path = generate_cover_image(title, args.subtitle, args.badge)

    # 3. Markdown → HTML
    print("📝 排版文章...")
    html_content, final_digest = md_to_html(md_content, title=title, digest=args.digest)

    # 4. Dry-run 模式
    if args.dry_run:
        print("\n✅ Dry-run 完成。生成的 HTML 和封面未上传。")
        print(f"   封面: {cover_path}")
        print(f"   摘要: {final_digest}")
        return

    # 5. 初始化 API 客户端并发布
    client = WeChatClient()
    archive = ArchiveManager(PUBLISHED_DIR)

    print("📡 连接微信 API...")

    print("🖼️ 上传封面图...")
    thumb_id = client.upload_image(cover_path)

    print(f"📰 创建草稿: {title}")
    result = client.create_draft(
        title=title,
        html_content=html_content,
        thumb_media_id=thumb_id,
        digest=final_digest,
        author=args.author,
        content_source_url=args.source_url,
        open_comment=not args.no_comment,
    )

    if "media_id" in result:
        media_id = result["media_id"]
        print(f"\n✅ 草稿创建成功！")
        print(f"   media_id: {media_id}")
        print(f"   请前往公众号后台 → 草稿箱 查看并发布")

        # 6. 归档
        article_id = _slugify(title) or hashlib.md5(title.encode()).hexdigest()[:12]
        archive.archive(
            article_id=article_id,
            title=title,
            digest=final_digest,
            cover_path=cover_path,
            draft_path=draft_file,
            media_id=media_id,
            author=args.author,
        )
    else:
        print(f"\n❌ 创建草稿失败")
        print(f"   响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
