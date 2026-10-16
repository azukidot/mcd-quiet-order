#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦免开口 · 全流程模拟演示（dry-run）

本脚本把「麦麦免开口」的主链路完整走一遍，方便在没有任何凭证的情况下
看清它到底做了什么。注意三点：

  · **不联网**：全程不调用任何 MCP 工具，不发出任何网络请求；
  · **不下单**：不会调用 create-order，不会产生真实订单与支付链接；
  · **不动真实档案**：偏好写入系统临时目录，跑完即弃。

真实运行时的差异只有一处：门店 / 菜单 / 券池 / 核价金额来自 MCP 实时返回，
而这里用的是 sample_data/ 里的示例数据。逻辑本身与真实运行完全一致。

用法::

    python demo.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "sample_data"
sys.path.insert(0, str(HERE))

import best_coupon_calc as bcc   # noqa: E402
import preference_store as ps    # noqa: E402

WIDTH = 64
PREFIX = "       │ "


# ---------------------------------------------------------------------------
# 排版工具
# ---------------------------------------------------------------------------
def line(char: str = "─") -> str:
    return char * WIDTH


def center(text: str, width: int = WIDTH) -> str:
    pad = max(width - bcc.disp_width(text), 0)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def banner() -> None:
    print("╭" + line() + "╮")
    print("│" + center("麦麦免开口 · 全流程模拟演示") + "│")
    print("│" + center("不联网 / 不下单 / 不动真实档案") + "│")
    print("╰" + line() + "╯")


def step(n: int, title: str) -> None:
    print()
    print(line("━"))
    print(f"  第 {n} 步 · {title}")
    print(line("━"))


def agent(text: str) -> None:
    for i, seg in enumerate(text.split("\n")):
        print(("  麦麦 │ " if i == 0 else PREFIX) + seg)


def user(text: str) -> None:
    print(f"  用户 │ {text}")


def note(text: str) -> None:
    print(f"  ☞ {text}")


def pause() -> None:
    try:
        input("\n  —— 回车继续 ——")
    except EOFError:
        print()


# ---------------------------------------------------------------------------
# 演示数据
# ---------------------------------------------------------------------------
def load_order_history() -> List[Dict[str, Any]]:
    raw = json.loads((SAMPLE / "order_history.json").read_text(encoding="utf-8"))
    return raw["data"]["list"]


def infer_from_history(orders: List[Dict[str, Any]], store_name: str) -> List[str]:
    """从指定门店的历史订单里归纳候选偏好（与真实运行的归纳规则一致）。

    只推断「有正面证据」的偏好，归纳依据见 SKILL.md 工作流 A-1 的对照表。
    历史订单里不含备注 / 特制 / 餐具字段，所以这里推不出「放门口」这类偏好。
    """
    picked = [o for o in orders if o.get("storeName") == store_name]
    combos: Counter = Counter()
    channels: Counter = Counter()
    hours: Counter = Counter()
    for o in picked:
        channels[{1: "到店自取", 2: "麦乐送", 5: "得来速"}.get(o.get("beType"), "到店自取")] += 1
        hours[o.get("createTime", " ")[11:13] + " 点前后"] += 1
        for p in o.get("orderProductList", []):
            side = "、".join(
                c.get("itemName", "") for c in p.get("comboItemList", []) if c.get("itemName")
            )
            combos[p["productName"] + (f"（{side}）" if side else "")] += 1
    top_combo, combo_count = combos.most_common(1)[0]
    top_channel, _ = channels.most_common(1)[0]
    top_hour, _ = hours.most_common(1)[0]
    return [
        f"常点是「{top_combo}」—— 最近 {len(picked)} 单全是它",
        f"习惯的取餐方式：{top_channel}",
        f"常在 {top_hour}下单",
    ]


def confirm_sheet(order: Dict[str, Any], habit_lines: List[str]) -> None:
    """打印订单确认单（真实运行时，用户确认后才会调 create-order）。"""
    w = 58
    print("  ┌" + "─" * w + "┐")
    print("  │" + center("订 单 确 认 单", w) + "│")
    print("  ├" + "─" * w + "┤")

    def row(k: str, v: str) -> None:
        pad = w - 2 - bcc.disp_width(k) - bcc.disp_width(v)
        print("  │ " + k + "  " + " " * max(pad, 1) + v + " │")

    for k, v in order["rows"]:
        row(k, v)

    print("  ├" + "─" * w + "┤")
    habit = "按你的习惯带入（可当场改）"
    print("  │ " + habit + " " * (w - 2 - bcc.disp_width(habit)) + " │")
    for h in habit_lines:
        text = "· " + h
        print("  │ " + text + " " * (w - 2 - bcc.disp_width(text)) + " │")
    print("  └" + "─" * w + "┘")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    banner()

    # 偏好档案写到临时目录，避免污染真实数据
    tmp_home = tempfile.mkdtemp(prefix="mcd-quiet-order-demo-")
    os.environ["MCD_QUIET_ORDER_HOME"] = tmp_home
    note(f"偏好档案写入临时目录（演示结束即弃）：{tmp_home}")
    note("真实运行的每一步在这里都有一一对应的动作；凡属「演示数据」处均已标注。")

    # =====================================================================
    step(1, "偏好层 · 给自己点（从历史订单推断）")
    # =====================================================================
    print()
    user("帮我点个麦当劳")
    agent("先看看你的档案——还是空的。读一遍历史订单：")
    orders = load_order_history()
    by_store: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for o in orders:
        by_store[f"{o['storeName']}（{o['storeCode']}）"].append(o)
    for name, items in by_store.items():
        print(PREFIX + f" · {name}：{len(items)} 单")

    target_store = "麦当劳（软件园店）"
    agent("\n你说「看软件园这家」——历史自带门店信息，本地筛一下就行：")
    for c in infer_from_history(orders, target_store):
        print(PREFIX + f" · {c}")
    agent("\n要不要记成你的「老样子」？")
    user("记吧")
    agent(
        "还有件事必须说实话：历史订单里没有备注和特制字段，\n"
        "所以放门口、去冰这些，历史里看不出来。这次怎么点？"
    )
    user("这次外卖，放门口别敲门，餐具要一副")
    agent("好，记下了。")
    note("「无糖可乐」来自历史推断；麦乐送、备注、餐具是刚问到的——档案里会分别标注来源。")

    data = ps.load()
    ps.merge_fields(
        data, "self",
        {"taste": ["无糖可乐"], "prefer_channel": "pickup"},
        source="inferred",
    )
    ps.merge_fields(
        data, "self",
        {
            "prefer_channel": "delivery",
            "remark": "无接触配送，请放门口，不用敲门",
            "need_tableware": True,
        },
        source="asked",
    )
    ps.save(data)
    print()
    print("  （档案写入后：）")
    print("  " + ps.render_profile("self", data["profiles"]["self"], True).replace("\n", "\n  "))

    pause()

    # =====================================================================
    step(2, "偏好层 · 给别人点（问三个问题）")
    # =====================================================================
    print()
    user("帮我妈点一份")
    agent("我妈有档案吗？——没有。那就问，一次只问一个：")
    for q, a in [
        ("阿姨有什么不吃的吗？", "辣的不行"),
        ("送到家还是到店取？", "到店取，她爱遛弯"),
        ("要不要餐具？", "要"),
    ]:
        agent(q)
        user(a)
    agent("好，存成「我妈」的档案，下次直接用。")
    ps.merge_fields(
        data, "mom",
        {"label": "我妈", "taste": ["不要辣"], "prefer_channel": "pickup", "need_tableware": True},
        source="asked",
    )
    ps.save(data)
    print()
    print("  " + ps.render_profile("mom", data["profiles"]["mom"], False).replace("\n", "\n  "))

    pause()

    # =====================================================================
    step(3, "优惠试算（本地穷举 + MCP 核价，此处为演示数据）")
    # =====================================================================
    print()
    agent(
        "想吃巨无霸套餐，再加一份麦乐鸡。先把券池和菜单在本地穷举一轮，\n"
        "只把最前面的几个方案交给 calculate-price 核价。"
    )
    menu = json.loads((SAMPLE / "menu.json").read_text(encoding="utf-8"))
    coupons = json.loads((SAMPLE / "coupons.json").read_text(encoding="utf-8"))
    request = json.loads((SAMPLE / "request.json").read_text(encoding="utf-8"))
    plan = bcc.plan(menu, coupons, request, top_n=4)
    print(PREFIX + f" 本地试了 {plan['combos_tried']} 种「菜品 × 券」组合"
          f"（{plan['baskets_tried']} 个菜篮，原价 {plan['baseline']['total']}）")
    print(PREFIX + " ↓ 真实运行中，金额来自 calculate-price 的核价返回；")
    print(PREFIX + "   此处使用预置的演示核价结果（sample_data/results.json）")
    results = json.loads((SAMPLE / "results.json").read_text(encoding="utf-8"))
    print()
    print("  " + bcc.render_text(bcc.verify(results)).replace("\n", "\n  "))
    print()
    agent(
        "顺手也算了一下外卖：同一单外卖到手 ¥54.00（含配送费 ¥9.00），\n"
        "比自取贵 ¥9.00，正好是一单配送费。"
    )
    user("那就自取。反正取餐柜扫码就行，也一样不用说话")

    pause()

    # =====================================================================
    step(4, "订单确认单（确认之后才会真正下单）")
    # =====================================================================
    print()
    agent(
        "按最省方案整理成确认单。注意中间那段——本次自动带入\n"
        "了哪些习惯，一条条列出来，你可以当场改："
    )
    confirm_sheet(
        {
            "rows": [
                ("商品", "巨无霸套餐 ×1 + 麦乐鸡5块 ×1"),
                ("门店", "麦当劳（软件园店）"),
                ("方式", "到店自取 · 取餐柜"),
                ("备注", "本次不适用（到店无备注通道）"),
                ("餐具", "需要"),
                ("实付", "¥45.00（原价 ¥55.00，省 ¥10.00）"),
            ],
        },
        [
            "套餐配中薯条、无糖可乐 ← 历史订单推断",
            "需要餐具 ← 你上次说的",
            "外送备注已存着，这次到店用不上 ← 你上次说的",
        ],
    )
    print()
    user("没问题，下单")
    note("真实运行到这里才会调用 create-order。本演示到此为止，不会下单。")

    pause()

    # =====================================================================
    step(5, "下单之后 · 取餐与兜底")
    # =====================================================================
    print()
    agent("支付链接已生成（演示占位，非真实链接）：")
    print(PREFIX + " https://pay.example.invalid/demo-qr  ← 用户自己扫码付款")
    agent(
        "\n支付完成后返回取餐柜二维码，扫码开柜，全程不见店员。\n"
        "临时想加一句「麻烦给我一根吸管」？——出卡："
    )
    print(PREFIX + " python scripts/quiet_card.py --preset 吸管   ← 卡片直接弹出，举给店员看即可")
    print(PREFIX + " （全屏展示 / 点朗读 / 存成图片转发）")
    print()
    print(line("─"))
    print("  演示结束。真实运行时唯一的区别：门店、菜单、券池与金额")
    print("  全部来自麦当劳 MCP 的实时返回，且第 4 步确认后才真正下单。")
    print(line("─"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
