#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦免开口 —— 本地优惠组合优化器（搜索）+ MCP 核价（验证）。

设计要点
--------
优惠方案的搜索**不调用 MCP**，全部在本地完成；只把排在最前面的少量方案交给
MCP 的 ``calculate-price`` 真实核价。这样做的原因有三条：

1. **绕开限流**。McDonald's MCP 每 Token 限 600 次/分钟，若逐个方案都调一次
   接口，几十个组合就会逼近上限，而本地穷举可以轻松试探上千种组合。
2. **搜索与计价解耦**。本地用归一化后的券规则做快速筛选，MCP 只负责"算准"。
3. **可复核**。相同输入永远得到相同输出，便于写测试与人工核对。

本地估算的价格**只能用于排序，不能直接展示给用户**——券的真实规则以麦当劳
系统为准，必须经过 ``calculate-price`` 核价后才能作为结论输出。

用法::

    python best_coupon_calc.py plan   --menu menu.json --coupons coupons.json \\
                                      --request request.json [--top 5]
    python best_coupon_calc.py verify --results results.json [--format text]

数据结构见文件末尾「数据契约」。
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from itertools import combinations, product
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 搜索规模上限（防止组合爆炸）
# ---------------------------------------------------------------------------
MAX_STACKED_COUPONS = 3        # 单个方案最多叠加几张券
MAX_CANDIDATES_PER_WANT = 4    # 每个"想吃的"保留几个候选商品
MAX_EXTRAS = 6                 # 凑单池大小
TOP_N_PLANS = 5                # 输出几个方案等待核价
DELIVERY_FEE_DEFAULT_FEN = 900


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _reconfigure_stdout() -> None:
    """Windows 控制台默认非 UTF-8，中文会乱码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def disp_width(text: str) -> int:
    """终端显示宽度，中日韩字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - disp_width(text))


def fen_to_yuan(fen: int) -> str:
    """分 -> 元。MCP 返回的金额单位一律是分。"""
    return f"¥{fen / 100:.2f}"


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def normalize_name(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "")


# ---------------------------------------------------------------------------
# 券模型
# ---------------------------------------------------------------------------
# 五种类型：item_price(单品改价) / percent(单品折扣) / threshold(满减)
#           / bundle_price(组合价，如 1+1) / free_gift(赠品)
#


def coupon_conflict(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """两张券是否互斥。

    规则：任一不可叠加即互斥；满减与赠品之间允许共存；其余情况看适用商品是否重叠。
    """
    if not a.get("stackable", False) or not b.get("stackable", False):
        return True
    ta, tb = a.get("type"), b.get("type")
    if ta in ("threshold", "free_gift") and tb in ("threshold", "free_gift"):
        return False
    codes_a = set(a.get("item_codes", [])) | {c for g in a.get("groups", []) for c in g}
    codes_b = set(b.get("item_codes", [])) | {c for g in b.get("groups", []) for c in g}
    return bool(codes_a & codes_b)


def coupon_touchable(coupon: Dict[str, Any], basket_codes: set) -> bool:
    """该券是否**有可能**作用在这个菜篮上（用于缩小搜索空间）。"""
    ctype = coupon.get("type")
    if ctype in ("threshold", "free_gift"):
        return True
    if ctype == "bundle_price":
        return all(set(g) & basket_codes for g in coupon.get("groups", []))
    return bool(set(coupon.get("item_codes", [])) & basket_codes)


def price_basket(
    basket: Sequence[Dict[str, Any]],
    coupon_ids: Sequence[str],
    coupons_by_id: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """在给定菜篮上套用一组券，返回明细；若券不合法则返回 None。"""
    code2item = {it["code"]: it for it in basket}

    override_price: Dict[str, int] = {}
    override_pct: Dict[str, float] = {}
    bundle_lines: List[Dict[str, Any]] = []
    consumed: set = set()

    for cid in coupon_ids:
        cp = coupons_by_id[cid]
        ctype = cp["type"]

        if ctype == "item_price":
            usable = [c for c in cp.get("item_codes", []) if c in code2item]
            if not usable:
                return None
            for code in usable:
                override_price[code] = min(
                    override_price.get(code, 1 << 30), int(cp["override_price_fen"])
                )

        elif ctype == "percent":
            usable = [c for c in cp.get("item_codes", []) if c in code2item]
            if not usable:
                return None
            for code in usable:
                override_pct[code] = min(override_pct.get(code, 1.0), float(cp["discount_pct"]))

        elif ctype == "bundle_price":
            picked: List[str] = []
            for group in cp.get("groups", []):
                cand = [c for c in group if c in code2item and c not in consumed]
                if not cand:
                    return None
                # 每组取原价最高的那个，最大化组合价的优惠幅度
                cand.sort(key=lambda c: code2item[c]["price_fen"], reverse=True)
                picked.append(cand[0])
                consumed.add(cand[0])
            bundle_lines.append(
                {"coupon_id": cid, "title": cp.get("title", cid),
                 "codes": picked, "price_fen": int(cp["price_fen"])}
            )

        elif ctype in ("threshold", "free_gift"):
            continue  # 小计算完后统一处理

        else:
            return None  # 未知券型，保守放弃

    # 逐项计价
    lines: List[Dict[str, Any]] = []
    subtotal_fen = 0
    for it in basket:
        code = it["code"]
        if code in consumed:
            continue
        base = int(it["price_fen"])
        eff = base
        tag = ""
        if code in override_price:
            eff = min(eff, override_price[code])
            tag = "单品券价"
        if code in override_pct:
            eff = min(eff, int(round(base * override_pct[code])))
            tag = "折扣"
        subtotal_fen += eff
        lines.append({"code": code, "name": it["name"], "price_fen": eff, "tag": tag})

    for bl in bundle_lines:
        subtotal_fen += bl["price_fen"]
        lines.append(
            {"code": "+".join(bl["codes"]), "name": bl["title"],
             "price_fen": bl["price_fen"], "tag": "组合价"}
        )

    # 满减：取当前小计下可用的最大抵扣
    best_threshold = None
    best_discount = 0
    for cid in coupon_ids:
        cp = coupons_by_id[cid]
        if cp["type"] == "threshold" and subtotal_fen >= int(cp.get("min_spend_fen", 0)):
            if int(cp["discount_fen"]) > best_discount:
                best_discount = int(cp["discount_fen"])
                best_threshold = cid

    # 赠品：门槛校验
    gifts: List[str] = []
    for cid in coupon_ids:
        cp = coupons_by_id[cid]
        if cp["type"] == "free_gift" and subtotal_fen >= int(cp.get("min_spend_fen", 0)):
            gifts.extend(cp.get("gift_codes", []))

    total_fen = max(subtotal_fen - best_discount, 0)
    return {
        "lines": lines,
        "subtotal_fen": subtotal_fen,
        "threshold_coupon": best_threshold,
        "discount_fen": best_discount,
        "total_fen": total_fen,
        "gifts": sorted(set(gifts)),
    }


def best_coupon_combo(
    basket: Sequence[Dict[str, Any]],
    coupons: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """在给定菜篮上搜索最省钱的券组合（本地穷举）。"""
    coupons_by_id = {c["id"]: c for c in coupons}
    basket_codes = {it["code"] for it in basket}

    pool = [cid for cid, cp in coupons_by_id.items() if coupon_touchable(cp, basket_codes)]

    best: Optional[Dict[str, Any]] = None
    best_total = 1 << 30
    combos_tried = 0

    for r in range(0, min(MAX_STACKED_COUPONS, len(pool)) + 1):
        for combo in combinations(pool, r):
            conflict = any(
                coupon_conflict(coupons_by_id[a], coupons_by_id[b])
                for a, b in combinations(combo, 2)
            )
            if conflict:
                continue
            combos_tried += 1
            res = price_basket(basket, combo, coupons_by_id)
            if res is None:
                continue
            if res["total_fen"] < best_total:
                best_total = res["total_fen"]
                best = res
                best["coupon_ids"] = list(combo)

    if best is None:
        best = price_basket(basket, [], coupons_by_id) or {}
        best.setdefault("coupon_ids", [])
    best["combos_tried"] = combos_tried
    return best


# ---------------------------------------------------------------------------
# 菜篮生成
# ---------------------------------------------------------------------------
def match_want(want: str, items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按名称/标签模糊匹配用户想吃的商品，返回按匹配度与价格排序的候选。"""
    key = normalize_name(want)
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for it in items:
        name = normalize_name(it.get("name", ""))
        code = normalize_name(it.get("code", ""))
        tags = [normalize_name(t) for t in it.get("tags", [])]
        score = -1
        if key and key in (name, code):
            score = 100
        elif key and (key in name or name in key):
            score = 80
        elif any(key in t or t in key for t in tags):
            score = 60
        if score >= 0:
            scored.append((score, it))
    scored.sort(key=lambda x: (-x[0], x[1]["price_fen"]))
    return [it for _, it in scored]


def build_baskets(request: Dict[str, Any], items: Sequence[Dict[str, Any]]) -> Iterable[List[Dict[str, Any]]]:
    """生成候选菜篮：用户想要的组合，以及为了凑满减而加购 1~2 件的变体。"""
    wants: List[str] = request.get("wants") or []
    max_items = int(request.get("max_items", 5))
    allow_extras = bool(request.get("allow_extras", True))

    want_candidates: List[List[Dict[str, Any]]] = []
    locked: set = set()
    for want in wants:
        cands = match_want(want, items)[:MAX_CANDIDATES_PER_WANT]
        if not cands:
            continue
        want_candidates.append(cands)
        locked.update(it["code"] for it in cands)

    if not want_candidates:
        # 没有明确想吃的东西，用最便宜的几件兜底
        cheapest = sorted(items, key=lambda x: x["price_fen"])[:MAX_CANDIDATES_PER_WANT]
        for it in cheapest:
            yield [it]
        return

    extras_pool = (
        [it for it in sorted(items, key=lambda x: x["price_fen"]) if it["code"] not in locked][:MAX_EXTRAS]
        if allow_extras
        else []
    )

    for combo in product(*want_candidates):
        codes = [it["code"] for it in combo]
        if len(set(codes)) != len(codes) or len(combo) > max_items:
            continue
        yield list(combo)
        if not allow_extras or len(combo) >= max_items:
            continue
        for extra in extras_pool:
            yield list(combo) + [extra]
        if len(combo) + 1 < max_items:
            for e1, e2 in combinations(extras_pool, 2):
                yield list(combo) + [e1, e2]


# ---------------------------------------------------------------------------
# plan：本地搜索
# ---------------------------------------------------------------------------
def plan(
    menu: Dict[str, Any],
    coupons_payload: Dict[str, Any],
    request: Dict[str, Any],
    top_n: int = TOP_N_PLANS,
) -> Dict[str, Any]:
    items = menu["items"]
    mode = str(request.get("dining_mode") or "pickup").strip().lower()
    all_coupons = coupons_payload.get("coupons", [])

    # 按就餐场景过滤券：channel 为 any 或与当前场景一致者可用
    coupons = [
        c for c in all_coupons
        if str(c.get("channel", "any")).strip().lower() in ("any", mode, "")
    ]

    delivery_fee_fen = (
        int(request.get("delivery_fee_fen") or DELIVERY_FEE_DEFAULT_FEN) if mode == "delivery" else 0
    )
    index = {it["code"]: it for it in items}

    # 无券基线
    baseline_items: List[Dict[str, Any]] = []
    for want in request.get("wants") or []:
        cands = match_want(want, items)
        if cands:
            baseline_items.append(cands[0])
    baseline_total_fen = sum(int(it["price_fen"]) for it in baseline_items)

    plans: List[Dict[str, Any]] = []
    seen: set = set()
    combos_tried = 0
    baskets_tried = 0

    for basket in build_baskets(request, items):
        baskets_tried += 1
        res = best_coupon_combo(basket, coupons)
        combos_tried += int(res.get("combos_tried", 0))
        if not res:
            continue

        calories = sum(int(it.get("calories", 0)) for it in basket)
        for gift in res.get("gifts", []):
            if gift in index:
                calories += int(index[gift].get("calories", 0))

        total_fen = int(res["total_fen"]) + delivery_fee_fen

        budget = request.get("budget_fen")
        if budget is not None and total_fen > int(budget):
            continue
        max_calories = request.get("max_calories")
        if max_calories is not None and calories > int(max_calories):
            continue

        key = (tuple(sorted(it["code"] for it in basket)), total_fen)
        if key in seen:
            continue
        seen.add(key)

        raw_total_fen = sum(int(it["price_fen"]) for it in basket)
        plans.append(
            {
                "items": [{"code": it["code"], "quantity": 1, "name": it["name"]} for it in basket],
                "coupon_ids": res.get("coupon_ids", []),
                "coupon_titles": [
                    coupons_by_id_title(coupons, cid) for cid in res.get("coupon_ids", [])
                ],
                "lines": res["lines"],
                "gifts": [g for g in res.get("gifts", []) if g in index],
                "estimated": {
                    "raw_total_fen": raw_total_fen,
                    "subtotal_fen": int(res["subtotal_fen"]),
                    "discount_fen": int(res["discount_fen"]),
                    "delivery_fee_fen": delivery_fee_fen,
                    "total_fen": total_fen,
                    "total": fen_to_yuan(total_fen),
                },
                "calories": calories,
                "item_count": len(basket),
                "saving_fen": raw_total_fen - total_fen,
            }
        )

    plans.sort(key=lambda p: (p["estimated"]["total_fen"], p["calories"]))

    for rank, p in enumerate(plans[:top_n], start=1):
        p["plan_id"] = f"plan-{rank}"
        p["notes"] = _make_notes(p, baseline_total_fen, request)

    warnings: List[str] = []
    if not coupons:
        warnings.append(
            "券池为空或当前就餐方式下无可用券。建议先调用 auto-bind-coupons 领取麦麦省券，"
            "或确认 storeCode / beType 是否正确。"
        )
    warnings.append(
        "本地估算价格仅用于排序，必须逐方案调用 calculate-price 核价后才能作为结论输出。"
    )

    return {
        "dining_mode": mode,
        "delivery_fee_fen": delivery_fee_fen,
        "baseline": {
            "items": [it["name"] for it in baseline_items],
            "total_fen": baseline_total_fen,
            "total": fen_to_yuan(baseline_total_fen),
        },
        "plan_pool_size": len(plans),
        "baskets_tried": baskets_tried,
        "combos_tried": combos_tried,
        "plans": plans[:top_n],
        "warnings": warnings,
        "verify_hint": "把 plans[].items 与 plans[].coupon_ids 对应的券交给 calculate-price 核价。",
    }


def coupons_by_id_title(coupons: Sequence[Dict[str, Any]], cid: str) -> str:
    for c in coupons:
        if c["id"] == cid:
            return str(c.get("title") or cid)
    return cid


def _make_notes(plan: Dict[str, Any], baseline_total_fen: int, request: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    diff = baseline_total_fen - plan["estimated"]["total_fen"]
    if diff > 0:
        notes.append(f"相比直选同类商品省 {fen_to_yuan(diff)}")
    if plan.get("gifts"):
        notes.append("含赠品：" + "、".join(plan["gifts"]))
    if plan["item_count"] > len(request.get("wants") or []):
        notes.append("含为凑满减而加购的商品，请确认是否接受")
    return notes


# ---------------------------------------------------------------------------
# verify：用 MCP 核价结果择优
# ---------------------------------------------------------------------------
def verify(results: Dict[str, Any]) -> Dict[str, Any]:
    """results.plans[].verified_total_fen 来自 calculate-price 的真实返回。"""
    raw = [p for p in results.get("plans", []) if p.get("verified_total_fen") is not None]
    if not raw:
        raise SystemExit("results.json 中没有含 verified_total_fen 的方案，无法择优。")

    baseline_fen = results.get("baseline_total_fen")
    if baseline_fen is None:
        baseline_fen = max(int(p["verified_total_fen"]) for p in raw)
    baseline_fen = int(baseline_fen)

    ranked = sorted(
        raw,
        key=lambda p: (
            int(p["verified_total_fen"]),
            -(baseline_fen - int(p["verified_total_fen"])),
            0 if not p.get("coupon_ids") else 1,  # 同价优先不用券，把券留到下次
        ),
    )

    comparisons = []
    for rank, p in enumerate(ranked, start=1):
        total = int(p["verified_total_fen"])
        comparisons.append(
            {
                "rank": rank,
                "plan_id": p.get("plan_id"),
                "label": p.get("label")
                or ("不使用优惠券" if not p.get("coupon_ids") else " + ".join(p.get("coupon_titles") or [])),
                "verified_total_fen": total,
                "verified_total": fen_to_yuan(total),
                "saved_fen": baseline_fen - total,
                "saved": fen_to_yuan(baseline_fen - total),
                "is_best": rank == 1,
            }
        )

    best = comparisons[0]
    return {
        "store": results.get("store"),
        "channel": results.get("channel"),
        "items_summary": results.get("items_summary"),
        "baseline_total_fen": baseline_fen,
        "baseline_total": fen_to_yuan(baseline_fen),
        "best": best,
        "saved_fen": best["saved_fen"],
        "saved": best["saved"],
        "discount_percent": round(best["saved_fen"] / baseline_fen * 100, 1) if baseline_fen else 0.0,
        "comparisons": comparisons,
    }


def render_text(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    if result.get("items_summary"):
        lines.append(f"商品：{result['items_summary']}")
    if result.get("store"):
        channel = f"（{result['channel']}）" if result.get("channel") else ""
        lines.append(f"门店：{result['store']}{channel}")
    lines.append(f"原价：{result['baseline_total']}")
    lines.append("")
    lines.append("方案对照：")

    width = min(max((disp_width(c["label"]) for c in result["comparisons"]), default=10), 40)
    for idx, comp in enumerate(result["comparisons"]):
        letter = chr(ord("A") + idx) if idx < 26 else str(idx + 1)
        mark = "   ← 推荐" if comp["is_best"] else ""
        lines.append(f"  {letter}  {pad(comp['label'], width)}  实付 {comp['verified_total']}{mark}")

    lines.append("")
    if result["saved_fen"] > 0:
        lines.append(
            f"推荐方案 {result['best']['label']}，可省 {result['saved']}"
            f"（约 {result['discount_percent']:.0f}%）。"
        )
    else:
        lines.append("当前没有能降低实付金额的券，按原价下单即可。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_plan(args: argparse.Namespace) -> None:
    menu = load_json(args.menu)
    coupons = load_json(args.coupons)
    request = load_json(args.request) if args.request else {}
    dump_json(plan(menu, coupons, request, top_n=args.top))


def cmd_verify(args: argparse.Namespace) -> None:
    results = load_json(args.results)
    out = verify(results)
    if args.format == "text":
        print(render_text(out))
    else:
        dump_json(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="麦当劳优惠组合优化器（麦麦免开口）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="本地穷举，产出待核价的候选方案")
    p_plan.add_argument("--menu", required=True, help="菜单 JSON")
    p_plan.add_argument("--coupons", required=True, help="归一化后的券列表 JSON")
    p_plan.add_argument("--request", help="需求 JSON（wants / 预算 / 热量上限等）")
    p_plan.add_argument("--top", type=int, default=TOP_N_PLANS, help="输出前几名，默认 5")
    p_plan.set_defaults(func=cmd_plan)

    p_verify = sub.add_parser("verify", help="用 MCP 核价结果择优")
    p_verify.add_argument("--results", required=True, help="含 verified_total_fen 的结果 JSON")
    p_verify.add_argument("--format", choices=["json", "text"], default="json")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _reconfigure_stdout()
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------
#
# menu.json —— 由 MCP 的 query-meals 归一化而来（金额单位：分）
# {
#   "store_code": "1990622",
#   "items": [
#     {"code": "BIGMAC", "name": "巨无霸", "category": "burger",
#      "price_fen": 2500, "calories": 550, "tags": ["beef", "classic"]}
#   ]
# }
#
# coupons.json —— 由 query-my-coupons / query-store-coupons / available-coupons
#                 的结果合并、去重并按下列五种类型归一化（金额单位：分）
# {
#   "coupons": [
#     {"id": "C1", "type": "item_price",   "title": "巨无霸立减",
#      "item_codes": ["BIGMAC"], "override_price_fen": 1800, "stackable": false},
#     {"id": "C2", "type": "percent",      "title": "小食 8 折",
#      "item_codes": ["FRIES_M"], "discount_pct": 0.8, "stackable": false},
#     {"id": "C3", "type": "threshold",    "title": "满 40 减 10",
#      "min_spend_fen": 4000, "discount_fen": 1000, "stackable": true},
#     {"id": "C4", "type": "bundle_price", "title": "组合价",
#      "groups": [["BIGMAC", "MCFLOWER"], ["FRIES_M", "COKE_M"]],
#      "price_fen": 1290, "stackable": false},
#     {"id": "C5", "type": "free_gift",    "title": "满 20 送派",
#      "min_spend_fen": 2000, "gift_codes": ["PIE"], "stackable": true}
#   ]
# }
# 可选字段 channel，取值 "any"（默认）/ "pickup" / "delivery"，控制券的适用场景。
#
# request.json
# {
#   "wants": ["巨无霸套餐", "麦乐鸡5块"],
#   "budget_fen": 6000,
#   "max_items": 3,
#   "allow_extras": false,
#   "dining_mode": "pickup",
#   "delivery_fee_fen": 900
# }
#
# results.json —— 把 calculate-price 的真实返回填入 verified_total_fen
# {
#   "store": "麦当劳XX餐厅",
#   "channel": "到店自取 · 取餐柜",
#   "items_summary": "巨无霸套餐 ×1 + 麦乐鸡5块 ×1",
#   "baseline_total_fen": 5500,
#   "plans": [
#     {"plan_id": "plan-1", "coupon_ids": ["C1"], "coupon_titles": ["巨无霸立减"],
#      "verified_total_fen": 4000}
#   ]
# }
