#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦免开口 —— 沟通卡快捷唤起。

不手动拼 URL，也不让用户自己去文件夹里找 html：把诉求改写成短句后，
一行命令生成带参链接并**直接打开**，需要时用户只需举起屏幕。

用法::

    python quiet_card.py "麻烦给我一根吸管"            # 生成并打开
    python quiet_card.py --preset 吸管                 # 用内置剧本
    python quiet_card.py "请不要放洋葱" -k taste --tag i人友好
    python quiet_card.py --list-presets                # 看全部内置剧本
    python quiet_card.py "麻烦给我一张纸巾" --print-only  # 只输出链接，不打开

``-k`` 场景取值：``item``（要东西）/ ``taste``（口味）/ ``ask``（询问）
/ ``thanks``（道谢）/ ``guide``（取餐指引）。
卡面短句建议不超过 15 字；朗读会由页面自动补成完整礼貌句。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

CARD = Path(__file__).resolve().parent.parent / "assets" / "quiet-card.html"

# 与 assets/quiet-card.html 中的 PRESETS 保持一致
PRESETS = [
    ("吸管",     "item",   "麻烦给我一根吸管"),
    ("纸巾",     "item",   "麻烦给我一张纸巾"),
    ("手套",     "item",   "麻烦给我一副手套"),
    ("打包袋",   "item",   "麻烦再给我一个打包袋"),
    ("番茄酱",   "item",   "麻烦多给我两包番茄酱"),
    ("去冰",     "taste",  "这杯请帮我做成去冰"),
    ("少放酱",   "taste",  "酱请少放一点，谢谢"),
    ("不要洋葱", "taste",  "请不要放洋葱"),
    ("催一下",   "ask",    "请问大概还要多久"),
    ("谢谢",     "thanks", "谢谢，辛苦了"),
]

KINDS = ("item", "taste", "ask", "thanks", "guide")

# 各平台常见浏览器可执行文件（直接拉起浏览器，避免系统对 file:// 带参链接
# 的处理差异——某些平台上经 ShellExecute 打开时会丢掉查询参数）
BROWSER_CANDIDATES = {
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Firefox.app/Contents/MacOS/firefox",
    ],
}


def build_url(text: str, kind: str, tag: str | None = None) -> str:
    """生成带参的 file:// 链接。中文按 UTF-8 百分号编码，页面用 URLSearchParams 解析。"""
    query = f"?t={quote(text)}&k={kind}"
    if tag:
        query += f"&tag={quote(tag)}"
    return CARD.as_uri() + query


def find_browser() -> str | None:
    for path in BROWSER_CANDIDATES.get(platform.system(), []):
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chromium", "microsoft-edge", "firefox"):
        found = shutil.which(name)
        if found:
            return found
    return None


def open_card(url: str, browser: str | None = None) -> str:
    """尝试打开卡片，返回实际使用的方式（用于如实告知用户）。"""
    if sys.platform.startswith("win"):
        exe = browser or find_browser()
        if exe:
            subprocess.Popen([exe, url])
            return "browser"
    elif platform.system() == "Darwin":
        exe = browser or find_browser()
        if exe:
            subprocess.Popen([exe, url])
            return "browser"
    else:
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, url])
            return "xdg-open"

    try:
        import webbrowser

        if webbrowser.open(url):
            return "webbrowser"
    except Exception:
        pass
    return "none"


def resolve_text(args: argparse.Namespace) -> str:
    if args.preset:
        for label, kind, text in PRESETS:
            if label == args.preset:
                args.kind = args.kind or kind
                return text
        raise SystemExit(
            f"没有名为「{args.preset}」的内置剧本。可用："
            + "、".join(p[0] for p in PRESETS)
        )
    return (args.text or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="麦麦免开口 · 沟通卡快捷唤起（生成带参链接并直接打开）"
    )
    parser.add_argument("text", nargs="?", help="卡面短句，建议不超过 15 字")
    parser.add_argument("--preset", help="使用内置剧本（用 --list-presets 查看）")
    parser.add_argument("-k", "--kind", choices=KINDS, help=f"场景，取值：{' / '.join(KINDS)}")
    parser.add_argument("--tag", help="角标文字；不传则跟随场景自动决定")
    parser.add_argument("--browser", help="指定浏览器可执行文件路径")
    parser.add_argument("--print-only", action="store_true", help="只输出链接，不打开")
    parser.add_argument("--list-presets", action="store_true", help="列出全部内置剧本")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    if args.list_presets:
        for label, kind, text in PRESETS:
            print(f"  {label:<6} [{kind:<6}] {text}")
        return 0

    text = resolve_text(args)
    if not text:
        parser.error("需要给出卡面短句，或用 --preset 指定内置剧本")
    kind = (args.kind or "item").lower()

    url = build_url(text, kind, args.tag)
    how = "not-opened" if args.print_only else open_card(url, args.browser)

    if args.json:
        print(json.dumps(
            {"text": text, "kind": kind, "tag": args.tag, "url": url, "opened": how},
            ensure_ascii=False, indent=2,
        ))
        return 0

    print(url)
    if args.print_only:
        print("（--print-only：未打开，链接可直接粘进浏览器）")
    elif how == "none":
        print("（没能自动打开浏览器，请把上面的链接粘进浏览器地址栏）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
