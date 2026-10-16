#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦免开口 —— 点餐偏好本地存储。

为什么需要这一层
----------------
「麦麦免开口」的多数动作，用户手动也能完成：自己写备注、自己在 App 里选餐具。
所以它的不可替代性不在"能不能做"，而在"**记不记得每次都做**"。

本模块把用户（及其家人）的点餐习惯沉淀为本地档案：一次设置，之后每次下单自动带入。
这是本 Skill 唯一无法被"自己动手"替代的能力。

隐私
----
偏好档案只存在本机，**不上传、不联网、不写入任何 MCP 请求之外的地方**。
默认路径 ``~/.mcd-quiet-order/preferences.json``，可用环境变量
``MCD_QUIET_ORDER_HOME`` 覆盖。

用法::

    python preference_store.py show                  # 查看当前档案（供复述给用户）
    python preference_store.py show --json           # 机器可读
    python preference_store.py list                  # 列出全部档案
    python preference_store.py new mom --label "我妈"
    python preference_store.py switch mom            # 切换当前档案
    python preference_store.py set --json '{"remark": "无接触配送，请放门口，不用敲门"}' --source asked
    python preference_store.py set --profile mom --json '{"taste": ["不要冰", "少放盐"]}' --source asked
    python preference_store.py set --json '{"remark": null}'         # 清除单项（传 null）
    python preference_store.py clear mom             # 删除档案

字段 ``source`` 记录的是**每一条偏好各自**是怎么来的：
``inferred``（从历史订单推断）、``asked``（下单前问到的）、``manual``（手动设置）。
它是一个「字段名 → 来源」的字典，``show`` 会在每条偏好后面标注来源，
便于在下单前向用户说明"这条是从你的历史订单里看出来的"，避免用户误解为系统擅自决定。
写入时用 ``--source`` 指定本次写入字段的来源，不写则记为 ``manual``。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = 1
DEFAULT_PROFILE = "self"

# 允许写入的字段及其类型，防止脏数据进入档案
# （source 不在此列：它由 --source 参数维护，按字段记录来源，不接受外部直接写入）
FIELD_TYPES: Dict[str, type] = {
    "label": str,           # 档案名，如「我自己」「我妈」
    "remark": str,          # 外送固定备注话术
    "need_tableware": bool, # 是否需要餐具
    "taste": list,          # 口味偏好，如 ["不要冰", "少放酱"]
    "avoid": list,          # 硬性排除，如 ["洋葱", "香菜"]
    "prefer_channel": str,  # 偏好就餐方式：delivery / pickup
    "card_presets": list,   # 常用沟通卡短句
    "note": str,            # 备忘
}

SOURCE_VALUES = ("inferred", "asked", "manual")

EMPTY_PROFILE: Dict[str, Any] = {
    "label": "",
    "remark": "",
    "need_tableware": None,
    "taste": [],
    "avoid": [],
    "prefer_channel": "",
    "card_presets": [],
    "note": "",
}

# 每条偏好的来源：{字段名: inferred / asked / manual}
EMPTY_SOURCE: Dict[str, str] = {}

SOURCE_LABELS = {
    "inferred": "从历史订单推断",
    "asked": "下单前问到的",
    "manual": "手动设置",
}


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------
def store_path() -> Path:
    home = os.environ.get("MCD_QUIET_ORDER_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".mcd-quiet-order"
    return base / "preferences.json"


def _empty_store() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "active_profile": DEFAULT_PROFILE,
        "profiles": {DEFAULT_PROFILE: {**EMPTY_PROFILE, "label": "我自己"}},
    }


def load() -> Dict[str, Any]:
    path = store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    data.setdefault("version", VERSION)
    data.setdefault("active_profile", DEFAULT_PROFILE)
    data.setdefault("profiles", {})
    for profile in data["profiles"].values():
        _migrate_profile(profile)
    return data


def _migrate_profile(profile: Dict[str, Any]) -> None:
    """把旧格式（source 为单个字符串）迁移为按字段记录的字典。"""
    src = profile.get("source")
    if isinstance(src, str):
        mapping: Dict[str, str] = {}
        if src:
            for key in EMPTY_PROFILE:
                if key == "label":
                    continue
                value = profile.get(key)
                if value not in ("", [], None):
                    mapping[key] = src
        profile["source"] = mapping
    elif not isinstance(src, dict):
        profile["source"] = {}


def save(data: Dict[str, Any]) -> Path:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 原子写入：先写临时文件再替换，避免中途失败把档案写坏
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".prefs-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


# ---------------------------------------------------------------------------
# 档案操作
# ---------------------------------------------------------------------------
def get_profile(data: Dict[str, Any], name: Optional[str]) -> str:
    key = name or data.get("active_profile") or DEFAULT_PROFILE
    return key


def ensure_profile(data: Dict[str, Any], name: str, label: str = "") -> Dict[str, Any]:
    profiles = data.setdefault("profiles", {})
    if name not in profiles:
        profiles[name] = {**EMPTY_PROFILE, "label": label or name, "source": {}}
        return profiles[name]
    _migrate_profile(profiles[name])
    return profiles[name]


def merge_fields(
    data: Dict[str, Any],
    name: str,
    patch: Dict[str, Any],
    source: Optional[str] = None,
) -> List[str]:
    """把 patch 合并进档案，返回被拒绝的字段列表。

    字段值传 ``null`` 表示清除该项（恢复为默认空值），便于用户删掉一条不再适用的偏好。
    ``source`` 标注本次写入的偏好是怎么来的（inferred / asked / manual），
    按字段分别记录，``show`` 时逐条展示。清除字段时同步移除其来源。
    """
    profile = ensure_profile(data, name)
    origin = source if source in SOURCE_VALUES else "manual"
    sources: Dict[str, str] = profile.setdefault("source", {})
    rejected: List[str] = []
    for key, value in patch.items():
        expected = FIELD_TYPES.get(key)
        if expected is None:
            rejected.append(key)
            continue
        if value is None:
            profile[key] = EMPTY_PROFILE.get(key)
            sources.pop(key, None)
            continue
        if expected is bool:
            if not isinstance(value, bool):
                rejected.append(key)
                continue
        elif expected is list:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                rejected.append(key)
                continue
        elif not isinstance(value, expected):
            rejected.append(key)
            continue
        profile[key] = value
        sources[key] = origin
    return rejected


def is_empty(profile: Dict[str, Any]) -> bool:
    """判断档案是否尚未记录任何习惯。label 只是显示名，不计入。"""
    for key, blank in EMPTY_PROFILE.items():
        if key == "label":
            continue
        if profile.get(key) not in (blank, None):
            return False
    return True


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def _origin_tag(profile: Dict[str, Any], key: str) -> str:
    origin = (profile.get("source") or {}).get(key)
    if not origin:
        return ""
    return f"（{SOURCE_LABELS.get(origin, origin)}）"


def render_profile(name: str, profile: Dict[str, Any], active: bool) -> str:
    lines: List[str] = []
    marker = "（当前）" if active else ""
    label = profile.get("label") or name
    lines.append(f"档案：{label} [{name}] {marker}".rstrip())

    if is_empty(profile):
        lines.append("  （空档案，尚未记录任何习惯）")
        return "\n".join(lines)

    if profile.get("remark"):
        lines.append(f"  外送备注      {profile['remark']}{_origin_tag(profile, 'remark')}")
    if profile.get("need_tableware") is not None:
        tag = _origin_tag(profile, "need_tableware")
        lines.append(f"  需要餐具      {'是' if profile['need_tableware'] else '否'}{tag}")
    if profile.get("prefer_channel"):
        channel = {"delivery": "麦乐送", "pickup": "到店取餐"}.get(
            profile["prefer_channel"], profile["prefer_channel"]
        )
        lines.append(f"  偏好方式      {channel}{_origin_tag(profile, 'prefer_channel')}")
    if profile.get("taste"):
        lines.append(f"  口味偏好      {'、'.join(profile['taste'])}{_origin_tag(profile, 'taste')}")
    if profile.get("avoid"):
        lines.append(f"  不吃 / 忌口   {'、'.join(profile['avoid'])}{_origin_tag(profile, 'avoid')}")
    if profile.get("card_presets"):
        lines.append(
            f"  常用卡片      {'、'.join(profile['card_presets'])}{_origin_tag(profile, 'card_presets')}"
        )
    if profile.get("note"):
        lines.append(f"  备忘          {profile['note']}{_origin_tag(profile, 'note')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_show(args: argparse.Namespace) -> None:
    data = load()
    name = get_profile(data, args.profile)
    profile = data.get("profiles", {}).get(name)
    if profile is None:
        if args.json:
            print(json.dumps({"profile": name, "found": False}, ensure_ascii=False, indent=2))
        else:
            print(f"未找到档案「{name}」。可用 `new {name}` 新建。")
        return
    if args.json:
        print(json.dumps({"profile": name, "data": profile}, ensure_ascii=False, indent=2))
    else:
        print(render_profile(name, profile, name == data.get("active_profile")))
        print(f"\n存储位置：{store_path()}")


def cmd_list(args: argparse.Namespace) -> None:
    data = load()
    active = data.get("active_profile")
    for name, profile in data.get("profiles", {}).items():
        print(render_profile(name, profile, name == active))
        print()


def cmd_new(args: argparse.Namespace) -> None:
    data = load()
    if args.name in data.get("profiles", {}):
        print(f"档案「{args.name}」已存在，未改动。")
        return
    ensure_profile(data, args.name, args.label)
    save(data)
    print(f"已新建档案：{args.label or args.name} [{args.name}]")


def cmd_switch(args: argparse.Namespace) -> None:
    data = load()
    if args.name not in data.get("profiles", {}):
        print(f"档案「{args.name}」不存在。可先执行 `new {args.name}`。")
        raise SystemExit(1)
    data["active_profile"] = args.name
    save(data)
    print(f"当前档案已切换为：{data['profiles'][args.name].get('label') or args.name}")


def cmd_set(args: argparse.Namespace) -> None:
    try:
        patch = json.loads(args.json)
    except json.JSONDecodeError as exc:
        print(f"--json 不是合法 JSON：{exc}")
        raise SystemExit(1)
    if not isinstance(patch, dict):
        print("--json 必须是一个对象，例如 '{\"remark\": \"放门口\"}'")
        raise SystemExit(1)

    data = load()
    name = get_profile(data, args.profile)
    rejected = merge_fields(data, name, patch, source=args.source)
    save(data)

    print(render_profile(name, data["profiles"][name], name == data.get("active_profile")))
    if rejected:
        print(f"\n以下字段未写入（未知字段或类型不符）：{'、'.join(rejected)}")
        print(f"可用字段：{'、'.join(FIELD_TYPES)}")


def cmd_clear(args: argparse.Namespace) -> None:
    data = load()
    if args.name not in data.get("profiles", {}):
        print(f"档案「{args.name}」不存在。")
        return
    del data["profiles"][args.name]
    if data.get("active_profile") == args.name:
        data["active_profile"] = next(iter(data["profiles"]), DEFAULT_PROFILE)
    if not data["profiles"]:
        data = _empty_store()
    save(data)
    print(f"已删除档案「{args.name}」。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="麦麦免开口 · 点餐偏好本地存储")
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="查看档案")
    p_show.add_argument("--profile", help="档案名，默认当前档案")
    p_show.add_argument("--json", action="store_true", help="输出 JSON")
    p_show.set_defaults(func=cmd_show)

    p_list = sub.add_parser("list", help="列出全部档案")
    p_list.set_defaults(func=cmd_list)

    p_new = sub.add_parser("new", help="新建档案")
    p_new.add_argument("name")
    p_new.add_argument("--label", default="", help="显示名，如「我妈」")
    p_new.set_defaults(func=cmd_new)

    p_switch = sub.add_parser("switch", help="切换当前档案")
    p_switch.add_argument("name")
    p_switch.set_defaults(func=cmd_switch)

    p_set = sub.add_parser("set", help="写入或更新字段（局部合并）")
    p_set.add_argument("--profile", help="档案名，默认当前档案")
    p_set.add_argument("--json", required=True, help="要合并的字段，JSON 对象")
    p_set.add_argument(
        "--source",
        choices=list(SOURCE_VALUES),
        default="manual",
        help="本次写入字段的来源，默认 manual",
    )
    p_set.set_defaults(func=cmd_set)

    p_clear = sub.add_parser("clear", help="删除档案")
    p_clear.add_argument("name")
    p_clear.set_defaults(func=cmd_clear)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# 档案结构
# ---------------------------------------------------------------------------
#
# {
#   "version": 1,
#   "active_profile": "self",
#   "profiles": {
#     "self": {
#       "label": "我自己",
#       "remark": "无接触配送，请放门口，不用敲门",
#       "need_tableware": true,
#       "prefer_channel": "delivery",
#       "taste": ["不要冰", "少放酱"],
#       "avoid": ["洋葱"],
#       "card_presets": ["麻烦给我一根吸管", "麻烦给我一张纸巾"],
#       "note": "",
#       "source": {
#         "remark": "asked",       // 下单前问到的
#         "taste": "inferred",     // 从历史订单推断
#         "need_tableware": "manual"
#       }
#     },
#     "mom": {
#       "label": "我妈",
#       "remark": "请放门口，不用敲门也不用按门铃，谢谢",
#       "taste": ["可乐去冰", "不要辣"],
#       "source": { "taste": "asked", "remark": "asked" }
#     }
#   }
# }
