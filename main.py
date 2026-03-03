#!/usr/bin/env python3
"""
Pokemon PPT Helper Tool
从 wiki.52poke.com 抓取 Pokemon 信息并生成本地网页
"""

import argparse
import colorsys
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin

import requests
from bs4 import BeautifulSoup
from jinja2 import Template
from pypinyin import Style, lazy_pinyin

def get_app_dir() -> Path:
    """返回应用目录（源码模式为脚本目录，EXE 模式为 exe 所在目录）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_bundle_dir() -> Path:
    """返回打包资源目录（EXE 模式为 _MEIPASS，源码模式为脚本目录）"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


# 常量定义
BASE_URL = "https://wiki.52poke.com"
LIST_URL = f"{BASE_URL}/wiki/宝可梦列表（按全国图鉴编号）"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
}
APP_DIR = get_app_dir()
BUNDLE_DIR = get_bundle_dir()
CACHE_DIR = Path(".cache/pages")
CACHE_ENABLED = True
REFRESH_CACHE = False
NAME_MAPPING_FILE = APP_DIR / "name_mapping.txt"
IGNORE_SKILLS_FILE = APP_DIR / "ignore_skills.txt"
TEMPLATE_FILE = BUNDLE_DIR / "template.html"
SITE_STYLES_FILE = BUNDLE_DIR / "wiki_site_styles.css"
ICONS_DIR = BUNDLE_DIR / "icons"
POKEMON_INDEX_CACHE: list[dict] | None = None
TYPE_BG_COLOR_CACHE: dict[str, str] | None = None

TYPE_ICON_ALIASES = {
    "斗": "格斗",
    "飞": "飞行",
    "鬼": "幽灵",
    "超": "超能力",
}

TYPE_ORDER = [
    "一般", "格斗", "飞行", "毒", "地面", "岩石", "虫", "幽灵", "钢",
    "火", "水", "草", "电", "超能力", "冰", "龙", "恶", "妖精"
]

STAT_ROW_CLASS_MAP = {
    "hp": {"row": "bgl-HP", "bar_bg": "bg-HP", "bar_bd": "bd-HP"},
    "attack": {"row": "bgl-攻击", "bar_bg": "bg-攻击", "bar_bd": "bd-攻击"},
    "defense": {"row": "bgl-防御", "bar_bg": "bg-防御", "bar_bd": "bd-防御"},
    "sp_attack": {"row": "bgl-特攻", "bar_bg": "bg-特攻", "bar_bd": "bd-特攻"},
    "sp_defense": {"row": "bgl-特防", "bar_bg": "bg-特防", "bar_bd": "bd-特防"},
    "speed": {"row": "bgl-速度", "bar_bg": "bg-速度", "bar_bd": "bd-速度"},
}

# 最新世代可用的属性相克关系（第六世代起规则一致）
ATTACK_TYPE_CHART = {
    "一般": {"岩石": 0.5, "幽灵": 0, "钢": 0.5},
    "格斗": {"一般": 2, "飞行": 0.5, "毒": 0.5, "岩石": 2, "虫": 0.5, "幽灵": 0, "钢": 2, "超能力": 0.5, "冰": 2, "恶": 2, "妖精": 0.5},
    "飞行": {"格斗": 2, "岩石": 0.5, "虫": 2, "钢": 0.5, "草": 2, "电": 0.5},
    "毒": {"毒": 0.5, "地面": 0.5, "岩石": 0.5, "幽灵": 0.5, "钢": 0, "草": 2, "妖精": 2},
    "地面": {"飞行": 0, "毒": 2, "岩石": 2, "虫": 0.5, "钢": 2, "火": 2, "草": 0.5, "电": 2},
    "岩石": {"格斗": 0.5, "飞行": 2, "地面": 0.5, "虫": 2, "钢": 0.5, "火": 2, "冰": 2},
    "虫": {"格斗": 0.5, "飞行": 0.5, "毒": 0.5, "幽灵": 0.5, "钢": 0.5, "火": 0.5, "草": 2, "超能力": 2, "恶": 2, "妖精": 0.5},
    "幽灵": {"一般": 0, "幽灵": 2, "超能力": 2, "恶": 0.5},
    "钢": {"岩石": 2, "钢": 0.5, "火": 0.5, "水": 0.5, "电": 0.5, "冰": 2, "妖精": 2},
    "火": {"岩石": 0.5, "钢": 2, "火": 0.5, "水": 0.5, "草": 2, "冰": 2, "龙": 0.5, "虫": 2},
    "水": {"地面": 2, "岩石": 2, "火": 2, "水": 0.5, "草": 0.5, "龙": 0.5},
    "草": {"飞行": 0.5, "毒": 0.5, "地面": 2, "岩石": 2, "虫": 0.5, "钢": 0.5, "火": 0.5, "水": 2, "草": 0.5, "龙": 0.5},
    "电": {"飞行": 2, "地面": 0, "水": 2, "草": 0.5, "电": 0.5, "龙": 0.5},
    "超能力": {"格斗": 2, "毒": 2, "钢": 0.5, "超能力": 0.5, "恶": 0},
    "冰": {"飞行": 2, "地面": 2, "钢": 0.5, "火": 0.5, "水": 0.5, "草": 2, "冰": 0.5, "龙": 2},
    "龙": {"钢": 0.5, "龙": 2, "妖精": 0},
    "恶": {"格斗": 0.5, "幽灵": 2, "超能力": 2, "恶": 0.5, "妖精": 0.5},
    "妖精": {"格斗": 2, "毒": 0.5, "钢": 0.5, "火": 0.5, "龙": 2, "恶": 2}
}


def compute_attack_effectiveness(
    form_types: list[str],
    name_mapping: dict[str, str] | None = None
) -> tuple[list[str], list[str]]:
    """计算进攻端属性克制（效果拔群/效果不好）"""
    valid_types = [t for t in form_types if t in ATTACK_TYPE_CHART]
    if not valid_types:
        return [], []

    strong_list: list[str] = []
    weak_list: list[str] = []

    for defend_type in TYPE_ORDER:
        multipliers = [ATTACK_TYPE_CHART[atk].get(defend_type, 1) for atk in valid_types]

        # 任意一个属性克制即可算效果拔群（并集）
        if any(m > 1 for m in multipliers):
            mapped_name = name_mapping.get(defend_type, defend_type) if name_mapping else defend_type
            strong_list.append(mapped_name)

        # 仅当所有属性都效果不好（<1）才算效果不好（交集）
        if all(m < 1 for m in multipliers):
            mapped_name = name_mapping.get(defend_type, defend_type) if name_mapping else defend_type
            # 所有属性都无效（=0）时标注
            if all(m == 0 for m in multipliers):
                mapped_name = f"{mapped_name}(无效)"
            weak_list.append(mapped_name)

    return strong_list, weak_list


def fetch_page(url: str) -> BeautifulSoup:
    """获取页面并解析为 BeautifulSoup 对象（支持本地缓存）"""
    cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.html"

    if CACHE_ENABLED and not REFRESH_CACHE and cache_file.exists():
        print(f"使用缓存页面: {url}")
        html = cache_file.read_text(encoding="utf-8")
        return BeautifulSoup(html, "lxml")

    print(f"请求页面: {url}")
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    html = response.text

    if CACHE_ENABLED:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(html, encoding="utf-8")

    return BeautifulSoup(html, "lxml")


def load_name_mapping(mapping_file: Path = NAME_MAPPING_FILE) -> dict[str, str]:
    """加载名称映射表（如属性全名 -> 简称）"""
    mapping: dict[str, str] = {}

    if not mapping_file.exists():
        print(f"未找到映射文件，跳过映射: {mapping_file}")
        return mapping

    try:
        for line in mapping_file.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue

            parts = text.split()
            if len(parts) < 2:
                continue

            src, dst = parts[0], parts[1]
            if src and dst:
                mapping[src] = dst
    except Exception as e:
        print(f"读取映射文件失败，跳过映射: {e}")
        return {}

    return mapping


def normalize_icon_type_name(type_name: str) -> str:
    """规范化图标文件名中的属性名"""
    normalized = type_name.strip()
    if normalized.lower().endswith("svg"):
        normalized = normalized[:-3]
    return normalized


def build_type_icon_map() -> dict[str, str]:
    """扫描 icons 目录并返回 属性名 -> 文件名 映射"""
    icon_map: dict[str, str] = {}

    if not ICONS_DIR.exists():
        return icon_map

    for icon_file in ICONS_DIR.glob("*.svg"):
        key = normalize_icon_type_name(icon_file.stem)
        if key:
            icon_map[key] = icon_file.name

    # 兼容简称/全称属性名
    for short_name, full_name in TYPE_ICON_ALIASES.items():
        if full_name in icon_map and short_name not in icon_map:
            icon_map[short_name] = icon_map[full_name]
        if short_name in icon_map and full_name not in icon_map:
            icon_map[full_name] = icon_map[short_name]

    return icon_map


def find_pokemon_link(identifier: str) -> tuple[str, str, str]:
    """
    在列表页面中查找 Pokemon 的链接
    参数: identifier - 编号(如"0001")或名字(如"妙蛙种子")
    返回: (编号, 名字, 链接URL)
    """
    print(f"正在列表页面中查找: {identifier}")
    soup = fetch_page(LIST_URL)

    # 判断输入是编号还是名字
    is_number = identifier.isdigit()
    search_num = identifier.zfill(4) if is_number else None
    identifier_norm = normalize_name_for_match(identifier)

    # 查找所有表格 (使用 roundy 或 eplist 类)
    tables = soup.find_all("table", class_=["roundy", "eplist", "sortable"])

    fallback_match: tuple[str, str, str] | None = None

    for table in tables:
        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 7:  # 表格有较多列
                continue

            # 提取编号 (第一列)
            num_cell = cells[0].get_text(strip=True)
            num_match = re.search(r"#(\d{4})", num_cell)
            if not num_match:
                continue
            num = num_match.group(1)

            # 提取名字（保留形态后缀）
            name_cell = cells[3] if len(cells) > 3 else cells[2]
            name, base_name, href = extract_name_and_link_from_list_cell(name_cell)
            if not name:
                continue

            if href:
                detail_url = urljoin(BASE_URL, href)
            else:
                detail_url = f"{BASE_URL}/wiki/{base_name or name}"

            # 匹配
            if is_number and num == search_num:
                print(f"找到 Pokemon: #{num} {name}")
                return num, name, detail_url

            if not is_number:
                name_norm = normalize_name_for_match(name)
                base_name_norm = normalize_name_for_match(base_name)

                # 优先精确匹配（支持括号/空白差异）
                if identifier_norm and (identifier_norm == name_norm or identifier_norm == base_name_norm):
                    print(f"找到 Pokemon: #{num} {name}")
                    return num, name, detail_url

                # 退化为模糊匹配
                if identifier_norm and (
                    identifier_norm in name_norm
                    or identifier_norm in base_name_norm
                ) and fallback_match is None:
                    fallback_match = (num, name, detail_url)

    if fallback_match is not None:
        print(f"找到 Pokemon: #{fallback_match[0]} {fallback_match[1]}")
        return fallback_match

    raise ValueError(f"未找到 Pokemon: {identifier}")


def build_pinyin_aliases(text: str) -> tuple[str, str]:
    """构建中文名称对应的拼音全拼与首字母简拼"""
    full = "".join(lazy_pinyin(text, errors="ignore")).lower()
    initials = "".join(lazy_pinyin(text, style=Style.FIRST_LETTER, errors="ignore")).lower()
    return full, initials


def load_type_bg_color_map() -> dict[str, str]:
    """从 wiki 样式文件中提取属性背景色映射（.bg-属性 -> --bg）"""
    global TYPE_BG_COLOR_CACHE
    if TYPE_BG_COLOR_CACHE is not None:
        return TYPE_BG_COLOR_CACHE

    color_map: dict[str, str] = {}
    if SITE_STYLES_FILE.exists():
        css_text = SITE_STYLES_FILE.read_text(encoding="utf-8", errors="ignore")
        for name, color in re.findall(r":where\(\.bg-([^,\.\)]+)[^\)]*\)\{--bg:([^;\}]+);", css_text):
            key = name.strip()
            value = color.strip()
            if key and value and key not in color_map:
                color_map[key] = value

    TYPE_BG_COLOR_CACHE = color_map
    return color_map


def get_type_bg_color(type_name: str) -> str:
    """获取属性背景色（优先读取源站样式映射）"""
    color_map = load_type_bg_color_map()
    return color_map.get(type_name, "#94a3b8")


def parse_css_color_to_hex(color_text: str) -> str:
    """将 CSS 颜色文本解析为 #rrggbb（支持 #hex / rgb / var(..., #hex)）"""
    text = (color_text or "").strip()
    if not text:
        return ""

    hex_matches = re.findall(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", text)
    if hex_matches:
        raw = hex_matches[-1]
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        return f"#{raw.lower()}"

    rgb_match = re.search(
        r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d\.]+)?\s*\)",
        text,
        flags=re.IGNORECASE,
    )
    if rgb_match:
        r = max(0, min(255, int(rgb_match.group(1))))
        g = max(0, min(255, int(rgb_match.group(2))))
        b = max(0, min(255, int(rgb_match.group(3))))
        return f"#{r:02x}{g:02x}{b:02x}"

    return ""


def adjust_hex_color(hex_color: str, saturation_ratio: float = 0.55, lightness_ratio: float = 0.82) -> str:
    """降低饱和度并调整明度，返回 #rrggbb。ratio < 1 表示降低。"""
    normalized = parse_css_color_to_hex(hex_color)
    if not normalized:
        return ""

    r = int(normalized[1:3], 16) / 255.0
    g = int(normalized[3:5], 16) / 255.0
    b = int(normalized[5:7], 16) / 255.0

    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s = max(0.0, min(1.0, s * saturation_ratio))
    l = max(0.10, min(0.92, l * lightness_ratio))

    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(round(r2 * 255)):02x}{int(round(g2 * 255)):02x}{int(round(b2 * 255)):02x}"


def build_page_background_colors(stats_tables: list[dict], types: list[str], pokemon_name: str) -> tuple[str, str]:
    """基于普通形态种族值表主题色，生成详情页背景渐变色。"""
    default_start = "#667eea"
    default_end = "#764ba2"

    base_color = ""
    target_stats = None

    for form in stats_tables or []:
        form_name = form.get("form_name", "默认")
        if normalize_form_name_for_match(form_name, pokemon_name) == "default":
            target_stats = form
            break

    if target_stats is None and stats_tables:
        target_stats = stats_tables[0]

    if target_stats:
        base_color = parse_css_color_to_hex(target_stats.get("table_bg_color", ""))
        if not base_color:
            theme_class = target_stats.get("table_theme_class", "")
            m = re.match(r"^(?:bg|bgl|bgd)-(.+)$", theme_class)
            if m:
                type_name = normalize_type_name_for_theme(m.group(1))
                if type_name:
                    base_color = parse_css_color_to_hex(get_type_bg_color(type_name))

    if not base_color and types:
        type_name = normalize_type_name_for_theme(types[0])
        if type_name:
            base_color = parse_css_color_to_hex(get_type_bg_color(type_name))

    if not base_color:
        return default_start, default_end

    bg_start = adjust_hex_color(base_color, saturation_ratio=0.55, lightness_ratio=0.82) or default_start
    bg_end = adjust_hex_color(base_color, saturation_ratio=0.58, lightness_ratio=0.68) or default_end
    return bg_start, bg_end


def normalize_type_text(text: str) -> str:
    """统一属性文案为简体，便于匹配（如 惡->恶）"""
    normalized = re.sub(r"\s+", "", text or "")
    replacements = {
        "惡": "恶",
        "龍": "龙",
        "電": "电",
        "鋼": "钢",
        "飛": "飞",
        "蟲": "虫",
        "靈": "灵",
        "鬥": "斗",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def extract_types_from_list_cells(cells: list[BeautifulSoup]) -> list[str]:
    """从全国图鉴列表行中提取属性"""
    types: list[str] = []
    for idx in [6, 7]:
        if idx >= len(cells):
            continue
        cell = cells[idx]

        link_texts = [a.get_text(strip=True) for a in cell.find_all("a")]
        candidates = link_texts if link_texts else [cell.get_text(" ", strip=True)]

        found = ""
        for candidate in candidates:
            normalized = normalize_type_text(candidate)
            for t in TYPE_ORDER:
                if t in normalized:
                    found = t
                    break
            if found:
                break

        if found and found not in types:
            types.append(found)

    return types


def normalize_list_name_text(text: str) -> str:
    """清理列表名称文本（去空白/脚注）"""
    cleaned = re.sub(r"\[[^\]]*\]", "", text or "")
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_name_for_match(text: str) -> str:
    """统一名称匹配键（忽略空白、括号、部分分隔符差异）"""
    normalized = normalize_list_name_text(text)
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = re.sub(r"[\s()（）·・_\-/]+", "", normalized)
    return normalized.lower()


def extract_name_and_link_from_list_cell(name_cell: BeautifulSoup) -> tuple[str, str, str]:
    """提取列表名称列中的展示名、基础名和链接"""
    raw_name = normalize_list_name_text(name_cell.get_text(" ", strip=True))
    name_link = name_cell.find("a")

    if not name_link:
        return raw_name, raw_name, ""

    base_name = normalize_list_name_text(name_link.get_text(" ", strip=True))
    href = (name_link.get("href", "") or "").strip()
    display_name = raw_name or base_name

    # 列表中常见表现："索罗亚克 洗翠的样子"，统一显示为"索罗亚克（洗翠的样子）"
    if base_name and display_name and display_name != base_name and "（" not in display_name and "(" not in display_name:
        suffix = display_name.removeprefix(base_name).strip(" -·・/、，,")
        if suffix:
            display_name = f"{base_name}（{suffix}）"

    if not display_name:
        display_name = base_name

    return display_name, (base_name or display_name), href


def build_pokemon_index() -> list[dict]:
    """从列表页提取 Pokemon 索引（编号、名称、详情链接）"""
    soup = fetch_page(LIST_URL)
    tables = soup.find_all("table", class_=["roundy", "eplist", "sortable"])

    entries: list[dict] = []
    seen_entries: set[tuple[str, str, str]] = set()

    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            num_cell = cells[0].get_text(strip=True)
            num_match = re.search(r"#(\d{4})", num_cell)
            if not num_match:
                continue
            number = num_match.group(1)

            name_cell = cells[3] if len(cells) > 3 else cells[2]
            name, base_name, href = extract_name_and_link_from_list_cell(name_cell)
            if not name:
                continue

            # 同编号不同形态需要保留；只去重完全相同条目
            dedup_key = (number, normalize_name_for_match(name), href)
            if dedup_key in seen_entries:
                continue
            seen_entries.add(dedup_key)

            name_en = cells[5].get_text(" ", strip=True) if len(cells) > 5 else ""
            types = extract_types_from_list_cells(cells)
            type_colors = [get_type_bg_color(t) for t in types]
            name_pinyin, name_initials = build_pinyin_aliases(name)
            item_key = hashlib.md5(f"{number}|{name}|{href}".encode("utf-8")).hexdigest()[:12]

            detail_url = urljoin(BASE_URL, href) if href else f"{BASE_URL}/wiki/{base_name or name}"
            entries.append({
                "number": number,
                "name": name,
                "name_en": name_en,
                "types": types,
                "type_colors": type_colors,
                "name_pinyin": name_pinyin,
                "name_initials": name_initials,
                "detail_url": detail_url,
                "identifier": name,
                "item_key": item_key,
            })

    entries.sort(key=lambda x: x.get("number", "9999"))
    return entries


def get_pokemon_index() -> list[dict]:
    """获取 Pokemon 索引（内存缓存）"""
    global POKEMON_INDEX_CACHE
    if POKEMON_INDEX_CACHE is None:
        POKEMON_INDEX_CACHE = build_pokemon_index()
    return POKEMON_INDEX_CACHE


def refresh_pokemon_index(force_refresh_cache: bool = True) -> list[dict]:
    """强制刷新 Pokemon 索引，可选择同时刷新列表页缓存"""
    global POKEMON_INDEX_CACHE, REFRESH_CACHE
    old_refresh_cache = REFRESH_CACHE
    try:
        if force_refresh_cache:
            REFRESH_CACHE = True
        POKEMON_INDEX_CACHE = build_pokemon_index()
        return POKEMON_INDEX_CACHE
    finally:
        REFRESH_CACHE = old_refresh_cache


def search_pokemon_entries(query: str) -> list[dict]:
    """按编号/中文名/英文名/拼音搜索 Pokemon 条目"""
    entries = get_pokemon_index()
    q = normalize_name_for_match(query)
    if not q:
        return entries

    results: list[dict] = []
    for item in entries:
        number = item.get("number", "").lower()
        name = item.get("name", "")
        name_norm = normalize_name_for_match(name)
        name_en = item.get("name_en", "").lower()
        name_pinyin = item.get("name_pinyin", "")
        name_initials = item.get("name_initials", "")

        if (
            q in number
            or q in name_norm
            or q in name_en
            or q in name_pinyin
            or q in name_initials
        ):
            results.append(item)

    return results


def extract_base_stats(soup: BeautifulSoup) -> dict:
    """提取种族值"""
    stats = {}

    # 查找种族值表格 - 兼容简繁体标题
    tables = soup.find_all("table", class_="roundy")
    for table in tables:
        text = table.get_text()
        if any(k in text for k in ["种族值", "種族值"]) and ("ＨＰ" in text or "HP" in text):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue

                # 第一列通常是“属性名：数值”
                label_cell = cells[0].get_text(strip=True).replace(" ", "")
                value_match = re.search(r"[：:]\s*(\d+)", label_cell)
                if not value_match:
                    continue
                value_str = value_match.group(1)

                # 兼容简繁体字段
                if re.match(r"^(ＨＰ|HP)", label_cell):
                    stats["hp"] = value_str
                elif re.match(r"^(攻击|攻擊)", label_cell):
                    stats["attack"] = value_str
                elif re.match(r"^(防御|防禦)", label_cell):
                    stats["defense"] = value_str
                elif re.match(r"^特攻", label_cell):
                    stats["sp_attack"] = value_str
                elif re.match(r"^特防", label_cell):
                    stats["sp_defense"] = value_str
                elif re.match(r"^速度", label_cell):
                    stats["speed"] = value_str

            if stats:
                break

    return stats


def parse_stats_table(table: BeautifulSoup, form_name: str) -> dict | None:
    """解析单个种族值表格（基础值 + Lv.50/Lv.100）"""
    rows_data = []
    total = ""

    table_theme_class = ""
    table_bg_color = ""
    for cls in table.get("class", []):
        if isinstance(cls, str) and re.match(r"^(bg|bgl|bgd)-", cls):
            table_theme_class = cls
            break

    style_text = table.get("style", "")
    bg_match = re.search(r"background(?:-color)?\s*:\s*([^;]+)", style_text, flags=re.IGNORECASE)
    if bg_match:
        table_bg_color = bg_match.group(1).strip()

    stat_key_map = {
        "ＨＰ": ("hp", "HP"),
        "HP": ("hp", "HP"),
        "攻击": ("attack", "攻击"),
        "攻擊": ("attack", "攻击"),
        "防御": ("defense", "防御"),
        "防禦": ("defense", "防御"),
        "特攻": ("sp_attack", "特攻"),
        "特防": ("sp_defense", "特防"),
        "速度": ("speed", "速度"),
    }

    for row in table.find_all("tr"):
        first_th = row.find("th")
        if not first_th:
            continue

        first_text = first_th.get_text(" ", strip=True)
        if not first_text:
            continue

        # 总和行
        if "总和" in first_text:
            total_match = re.search(r"总和[：:]\s*(\d+)", first_text)
            if total_match:
                total = total_match.group(1)
            continue

        matched = None
        for stat_name, (stat_key, label) in stat_key_map.items():
            if first_text.startswith(stat_name):
                matched = (stat_key, label)
                break

        if not matched:
            continue

        stat_key, label = matched

        base_match = re.search(r"[：:]\s*(\d+)", first_text)
        base = base_match.group(1) if base_match else ""

        # 仅取 BasePoint 的 Lv.50/Lv.100 列
        basepoint_cells = row.find_all("th", class_=lambda cls: cls and "BasePoint" in cls)
        lv50 = basepoint_cells[0].get_text(" ", strip=True) if len(basepoint_cells) >= 1 else "—"
        lv100 = basepoint_cells[1].get_text(" ", strip=True) if len(basepoint_cells) >= 2 else "—"

        lv50 = re.sub(r"\s+", " ", lv50)
        lv100 = re.sub(r"\s+", " ", lv100)

        base_int = int(base) if str(base).isdigit() else 0
        stat_style = STAT_ROW_CLASS_MAP.get(stat_key, {})
        rows_data.append({
            "key": stat_key,
            "label": label,
            "base": base or "?",
            "base_int": base_int,
            "row_class": stat_style.get("row", ""),
            "bar_bg_class": stat_style.get("bar_bg", ""),
            "bar_bd_class": stat_style.get("bar_bd", ""),
            "lv50": lv50 or "—",
            "lv100": lv100 or "—"
        })

    if not rows_data:
        return None

    if not total:
        numeric = [int(r["base"]) for r in rows_data if str(r["base"]).isdigit()]
        total = str(sum(numeric)) if numeric else "?"

    return {
        "form_name": form_name,
        "rows": rows_data,
        "total": total,
        "table_theme_class": table_theme_class,
        "table_bg_color": table_bg_color,
    }


def extract_stats_tables(soup: BeautifulSoup) -> list[dict]:
    """提取种族值表格（支持多形态）"""
    forms = []

    # 提取形态标签映射（如 1base -> 一般, 2base -> 超级进化）
    form_label_map: dict[str, str] = {}
    for span in soup.find_all("span", class_=re.compile(r"toggle-[pl]-\d+base")):
        classes = span.get("class", [])
        text = span.get_text(" ", strip=True)
        if not text:
            continue
        for cls in classes:
            m = re.match(r"toggle-[pl]-(\d+)base", cls)
            if m:
                idx = m.group(1)
                if idx not in form_label_map:
                    form_label_map[idx] = text

    # 先尝试解析多形态块
    toggle_blocks = soup.find_all("div", class_=re.compile(r"toggle-content"))
    for block in toggle_blocks:
        classes = block.get("class", [])
        if "toggle-cbase" not in classes:
            continue

        idx = None
        for cls in classes:
            m = re.match(r"toggle-(\d+)base", cls)
            if m:
                idx = m.group(1)
                break

        table = block.find("table", class_="roundy")
        if not table:
            continue

        table_text = table.get_text(" ", strip=True)
        if "种族值" not in table_text and "種族值" not in table_text:
            continue
        if "Lv.50" not in table_text and "Lv.100" not in table_text:
            continue

        label = form_label_map.get(idx or "", "")
        form_name = "默认" if (idx == "1" or label in ["一般", "通常", ""]) else label

        parsed = parse_stats_table(table, form_name)
        if parsed:
            forms.append(parsed)

    # 多形态失败时，回退到首个种族值表
    if not forms:
        tables = soup.find_all("table", class_="roundy")
        for table in tables:
            text = table.get_text(" ", strip=True)
            if ("种族值" in text or "種族值" in text) and "Lv.50" in text and "Lv.100" in text:
                parsed = parse_stats_table(table, "默认")
                if parsed:
                    forms.append(parsed)
                break

    # 默认形态优先
    defaults = [f for f in forms if f["form_name"] == "默认"]
    others = [f for f in forms if f["form_name"] != "默认"]
    return defaults + others


def extract_types(soup: BeautifulSoup, name_mapping: dict[str, str] | None = None) -> list:
    """提取属性"""
    raw_types: list[str] = []
    known_types = list((name_mapping or {}).keys()) or [
        "一般", "格斗", "飞行", "毒", "地面", "岩石", "虫", "幽灵", "钢",
        "火", "水", "草", "电", "超能力", "冰", "龙", "恶", "妖精"
    ]

    def extract_known_types(text: str, allow_fuzzy: bool = False) -> list[str]:
        """从任意文本中提取已知属性名"""
        cleaned = text.replace("屬性", "").replace("屬", "").replace("属性", "")
        tokens = re.split(r"[／/、,，\s]+", cleaned)

        result: list[str] = []

        # 优先精确 token 匹配
        for token in tokens:
            t = token.strip()
            if t in known_types:
                result.append(t)

        # 可选：模糊匹配，仅用于兜底文本
        if allow_fuzzy and not result:
            for t in known_types:
                if t in cleaned:
                    result.append(t)

        return list(dict.fromkeys(result))

    # 方法1: 从“属性相性”表格的防守行前两列提取（最稳定）
    headers = soup.find_all(["h2", "h3"])
    target_header = None
    for h in headers:
        h_text = h.get_text()
        if "属性相性" in h_text or "屬性相性" in h_text:
            target_header = h
            break

    if target_header:
        tables = target_header.find_all_next("table", class_="roundy", limit=5)
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            header_cells = rows[0].find_all(["th", "td"])
            data_cells = rows[1].find_all(["th", "td"])
            if len(header_cells) < 19 or len(data_cells) < 2:
                continue

            header_title = header_cells[0].get_text(strip=True)
            if header_title not in ["进攻招式属性", "進攻招式屬性"]:
                continue

            for cell in data_cells[:2]:
                raw_types.extend(extract_known_types(cell.get_text(" ", strip=True), allow_fuzzy=False))

            if raw_types:
                break

    # 方法2: 从信息框中提取（兜底）
    if not raw_types:
        infobox = soup.find("table", class_=re.compile("roundy"))
        if infobox:
            rows = infobox.find_all("tr")
            for row in rows:
                th = row.find("th")
                th_text = th.get_text(strip=True) if th else ""
                if th_text in ["属性", "屬性"]:
                    tds = row.find_all("td")
                    for td in tds:
                        link_titles = [a.get("title", "") for a in td.find_all("a")]
                        for title in link_titles:
                            raw_types.extend(extract_known_types(title, allow_fuzzy=False))

                        raw_types.extend(extract_known_types(td.get_text(" ", strip=True), allow_fuzzy=False))
                    break

    # 方法3: 从页面文本中兜底提取
    if not raw_types:
        text = soup.get_text(" ", strip=True)
        patterns = [
            r"是(.+?)[屬性属性][／/](.+?)[屬性属性]宝可梦",  # 双属性
            r"是(.+?)[屬性属性]宝可梦",  # 单属性
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                for group in match.groups():
                    if group:
                        raw_types.extend(extract_known_types(group.strip(), allow_fuzzy=True))
                break

    if not raw_types:
        return []

    # 去重并保持顺序
    ordered_types = list(dict.fromkeys(raw_types))

    # 应用映射
    if name_mapping:
        ordered_types = [name_mapping.get(t, t) for t in ordered_types]

    return ordered_types


def extract_type_effectiveness(
    soup: BeautifulSoup,
    name_mapping: dict[str, str] | None = None
) -> dict:
    """提取属性克制关系（支持多形态）"""
    result = {
        "weak": [],
        "weak_4x": [],
        "resist": [],
        "immune": [],
        "strong": [],
        "weak_attack": [],
        "forms": []
    }

    # 查找属性相性章节（兼容简繁体）
    headers = soup.find_all(["h2", "h3"])
    target_header = None
    for h in headers:
        h_text = h.get_text()
        if "属性相性" in h_text or "屬性相性" in h_text:
            target_header = h
            break

    if not target_header:
        return result

    # 在章节后查找相性表格
    tables = target_header.find_all_next("table", class_="roundy", limit=8)

    forms: list[dict] = []

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        if len(header_cells) < 19:
            continue

        header_title = header_cells[0].get_text(strip=True)
        if header_title not in ["进攻招式属性", "進攻招式屬性"]:
            continue

        attack_types = [c.get_text(strip=True) for c in header_cells[1:19]]

        # 每行都可能是一个形态/计算方式
        for row_index, row in enumerate(rows[1:]):
            cells = row.find_all(["th", "td"])
            if len(cells) < len(attack_types) + 2:
                continue

            prefix_count = len(cells) - len(attack_types)
            if prefix_count < 2:
                continue

            meta_cells = cells[:prefix_count]
            multiplier_cells = cells[prefix_count:prefix_count + len(attack_types)]
            if len(multiplier_cells) != len(attack_types):
                continue

            # 属性（前两列）
            raw_form_types: list[str] = []
            for cell in meta_cells[:2]:
                type_text = cell.get_text(strip=True)
                type_text = type_text.replace("屬性", "").replace("屬", "").replace("属性", "")
                if type_text and type_text not in ["—", "-", "未知"]:
                    raw_form_types.append(type_text)
            raw_form_types = list(dict.fromkeys(raw_form_types))

            # 形态名（第3列，可能为空）
            raw_form_name = ""
            if prefix_count >= 3:
                raw_form_name = meta_cells[2].get_text(" ", strip=True)
            raw_form_name = raw_form_name.replace("未知", "").strip()
            form_name = raw_form_name if raw_form_name else "默认"

            form_effectiveness = {
                "weak": [],
                "weak_4x": [],
                "resist": [],
                "immune": [],
                "strong": [],
                "weak_attack": []
            }

            for attack_type, cell in zip(attack_types, multiplier_cells):
                type_name = attack_type.replace("屬性", "").replace("屬", "").replace("属性", "").strip()
                mult = cell.get_text(strip=True)
                mult = mult.replace(" ", "")

                if not type_name or not mult:
                    continue

                if mult in ["0", "0×"]:
                    form_effectiveness["immune"].append(type_name)
                elif mult in ["1⁄4", "1/4", "¼"]:
                    form_effectiveness["strong"].append(type_name)
                elif mult in ["1⁄2", "1/2", "½"]:
                    form_effectiveness["resist"].append(type_name)
                elif mult in ["2", "2×"]:
                    form_effectiveness["weak"].append(type_name)
                elif mult in ["4", "4×"]:
                    form_effectiveness["weak_4x"].append(type_name)

            # 去重并保持顺序
            for key in ["weak", "weak_4x", "resist", "immune", "strong", "weak_attack"]:
                form_effectiveness[key] = list(dict.fromkeys(form_effectiveness[key]))

            # 计算进攻端克制
            attack_strong, attack_weak = compute_attack_effectiveness(raw_form_types, name_mapping)

            # 应用名称映射（防守端 + 展示属性）
            display_form_types = raw_form_types
            if name_mapping:
                display_form_types = [name_mapping.get(t, t) for t in raw_form_types]
                for key in ["weak", "weak_4x", "resist", "immune", "strong", "weak_attack"]:
                    form_effectiveness[key] = [name_mapping.get(t, t) for t in form_effectiveness[key]]

            if not display_form_types and not any(form_effectiveness.values()) and not attack_strong and not attack_weak:
                continue

            forms.append({
                "form_name": form_name,
                "types": display_form_types,
                "effectiveness": form_effectiveness,
                "attack_strong": attack_strong,
                "attack_weak": attack_weak,
                "row_index": row_index
            })

        # 使用第一张有效防守表
        if forms:
            break

    if not forms:
        return result

    # 默认形态优先，其他保持出现顺序
    default_forms = [f for f in forms if f["form_name"] == "默认"]
    other_forms = [f for f in forms if f["form_name"] != "默认"]
    sorted_forms = default_forms + other_forms

    # 去掉内部排序字段
    result["forms"] = [
        {
            "form_name": f["form_name"],
            "types": f["types"],
            "effectiveness": f["effectiveness"],
            "attack_strong": f.get("attack_strong", []),
            "attack_weak": f.get("attack_weak", [])
        }
        for f in sorted_forms
    ]

    # 兼容旧字段：取默认/首个形态
    first_eff = result["forms"][0]["effectiveness"]
    for key in ["weak", "weak_4x", "resist", "immune", "strong", "weak_attack"]:
        result[key] = first_eff.get(key, [])

    return result


def is_ability_page_link(href: str) -> bool:
    """判断链接是否指向特性详情页"""
    return "（特性）" in href or "%EF%BC%88%E7%89%B9%E6%80%A7%EF%BC%89" in href


def extract_primary_form_image_src(row: BeautifulSoup) -> str:
    """从 form 行中提取主形态图（兼容 260px/300px）"""
    candidates: list[tuple[int, str]] = []

    for img in row.find_all("img"):
        src = img.get("src", "")
        if not src or "px-" not in src:
            continue

        lower = src.lower()
        if any(token in lower for token in ["tcg", "body", "sprite", "dream", "icon"]):
            continue

        size_match = re.search(r"/(\d+)px-", lower)
        size = int(size_match.group(1)) if size_match else 0
        if size < 120:
            continue

        candidates.append((size, src))

    if not candidates:
        return ""

    max_size = max(size for size, _ in candidates)
    for size, src in candidates:
        if size == max_size:
            return src

    return ""


def infer_form_name_from_image_src(image_src: str, pokemon_name: str) -> str:
    """根据形态主图文件名推断形态名称"""
    raw = (image_src or "").split("?")[0]
    filename = Path(raw).name
    filename = re.sub(r"^\d+px-", "", filename)

    stem = Path(filename).stem
    normalized_stem = stem.replace("_", "-").replace(" ", "-")
    if "-" not in normalized_stem:
        return pokemon_name

    suffix = normalized_stem.split("-", 1)[1].lower()
    normalized_suffix = suffix

    if pokemon_name == "皮卡丘":
        if any(tag in normalized_suffix for tag in ["pop-star", "phd", "libre", "belle", "rock-star", "cosplay"]):
            return "换装皮卡丘"
        if any(tag in normalized_suffix for tag in ["original", "hoenn", "sinnoh", "unova", "kalos", "alola", "partner-cap", "world", "cap"]):
            return "戴着帽子的皮卡丘"
        if normalized_suffix.startswith("partner"):
            return "搭档皮卡丘"

    if normalized_suffix.startswith("mega-x"):
        return f"超级{pokemon_name}X"
    if normalized_suffix.startswith("mega-y"):
        return f"超级{pokemon_name}Y"
    if normalized_suffix.startswith("mega"):
        return f"超级{pokemon_name}"
    if normalized_suffix.startswith("gigantamax") or normalized_suffix.startswith("gmax"):
        return f"超极巨化{pokemon_name}"
    if normalized_suffix.startswith("alola"):
        return f"阿罗拉{pokemon_name}"
    if normalized_suffix.startswith("galar"):
        return f"伽勒尔{pokemon_name}"
    if normalized_suffix.startswith("hisui"):
        return f"洗翠{pokemon_name}"
    if normalized_suffix.startswith("paldea"):
        return f"帕底亚{pokemon_name}"

    return f"{pokemon_name}（{normalized_suffix}）"


def normalize_form_name_for_match(form_name: str, pokemon_name: str) -> str:
    """将形态名归一化为可匹配键"""
    raw = re.sub(r"\s+", "", form_name or "")
    if not raw or raw in {"默认", "一般", pokemon_name}:
        return "default"

    normalized = raw.replace("（", "(").replace("）", ")").replace("超級", "超级")
    lower = normalized.lower().replace("_", "-").replace(" ", "-")

    if "超级" in normalized or "mega" in lower:
        if re.search(r"[xXＸ]", normalized) or "mega-x" in lower:
            return "mega-x"
        if re.search(r"[yYＹ]", normalized) or "mega-y" in lower:
            return "mega-y"
        return "mega"

    if "超极巨化" in normalized or "超極巨化" in normalized or "gigantamax" in lower or "gmax" in lower:
        return "gigantamax"
    if "阿罗拉" in normalized or "阿羅拉" in normalized or "alola" in lower:
        return "alola"
    if "伽勒尔" in normalized or "伽勒爾" in normalized or "galar" in lower:
        return "galar"
    if "洗翠" in normalized or "hisui" in lower:
        return "hisui"
    if "帕底亚" in normalized or "帕底亞" in normalized or "paldea" in lower:
        return "paldea"

    cleaned = normalized.replace(pokemon_name, "")
    cleaned = cleaned.replace("形态", "").replace("形態", "")
    cleaned = re.sub(r"[()（）·・_\-]+", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned.lower() if cleaned else "default"


def extract_form_images(soup: BeautifulSoup, pokemon_name: str) -> list[dict]:
    """按形态提取主图 URL"""
    form_rows = [
        tr for tr in soup.find_all("tr")
        if any(re.fullmatch(r"form\d+", cls or "") for cls in tr.get("class", []))
    ]

    form_images: list[dict] = []
    seen_form_keys: set[str] = set()

    for row in form_rows:
        image_src = extract_primary_form_image_src(row)
        if not image_src:
            continue

        form_name = infer_form_name_from_image_src(image_src, pokemon_name)
        form_key = normalize_form_name_for_match(form_name, pokemon_name)
        if form_key in seen_form_keys:
            continue
        seen_form_keys.add(form_key)

        if image_src.startswith("//"):
            image_src = "https:" + image_src

        form_images.append({
            "form_name": form_name,
            "form_key": form_key,
            "image_url": image_src,
            "image_path": "",
        })

    return form_images


def make_form_image_filename(number: str, pokemon_name: str, form_key: str) -> str:
    """生成按形态区分的图片文件名"""
    safe_key = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "-", form_key).strip("-")
    if not safe_key:
        safe_key = "default"
    return f"{number}{pokemon_name}-{safe_key}.png"


def assign_form_images_to_effectiveness_forms(
    type_effectiveness_forms: list[dict],
    form_images: list[dict],
    pokemon_name: str,
) -> None:
    """将已下载的形态图片映射到属性相性形态数据"""
    if not type_effectiveness_forms:
        return

    image_path_by_name = {
        item.get("form_name", ""): item.get("image_path", "")
        for item in form_images
        if item.get("image_path")
    }
    image_path_by_key = {
        item.get("form_key", ""): item.get("image_path", "")
        for item in form_images
        if item.get("image_path")
    }

    used_paths: set[str] = set()
    unmatched_forms: list[dict] = []

    for form in type_effectiveness_forms:
        form_name = form.get("form_name", "默认")
        form_key = normalize_form_name_for_match(form_name, pokemon_name)

        image_path = image_path_by_name.get(form_name) or image_path_by_key.get(form_key, "")
        if image_path:
            used_paths.add(image_path)
        else:
            unmatched_forms.append(form)

        form["image_path"] = image_path

    remaining_paths = [
        item["image_path"]
        for item in form_images
        if item.get("image_path") and item["image_path"] not in used_paths
    ]

    for form in unmatched_forms:
        if not remaining_paths:
            break
        form["image_path"] = remaining_paths.pop(0)


def assign_form_images_to_ability_tables(
    form_ability_tables: list[dict],
    form_images: list[dict],
    pokemon_name: str,
) -> None:
    """将已下载的形态图片映射到形态特性表"""
    if not form_ability_tables:
        return

    image_path_by_key = {
        item.get("form_key", ""): item.get("image_path", "")
        for item in form_images
        if item.get("image_path")
    }

    used_paths: set[str] = set()
    unmatched_forms: list[dict] = []

    for form in form_ability_tables:
        form_name = form.get("form_name", "默认")
        form_key = normalize_form_name_for_match(form_name, pokemon_name)
        image_path = image_path_by_key.get(form_key, "")

        if image_path:
            used_paths.add(image_path)
        else:
            unmatched_forms.append(form)

        form["image_path"] = image_path

    remaining_paths = [
        item["image_path"]
        for item in form_images
        if item.get("image_path") and item["image_path"] not in used_paths
    ]

    for form in unmatched_forms:
        if not remaining_paths:
            break
        form["image_path"] = remaining_paths.pop(0)


def normalize_type_name_for_theme(type_name: str) -> str:
    """将属性名称归一化为站点样式可识别名称"""
    t = (type_name or "").strip()
    if not t:
        return ""

    t = t.replace("飛", "飞").replace("電", "电").replace("龍", "龙").replace("鋼", "钢").replace("惡", "恶")
    t = t.replace("鬥", "斗")
    t = TYPE_ICON_ALIASES.get(t, t)
    return t


def assign_stats_theme_classes(
    stats_tables: list[dict],
    type_effectiveness_forms: list[dict],
    pokemon_name: str,
) -> None:
    """按形态为种族值表补充主题色 class（优先使用解析结果，缺失时用属性兜底）"""
    if not stats_tables:
        return

    type_theme_by_key: dict[str, str] = {}
    for form in type_effectiveness_forms:
        form_name = form.get("form_name", "默认")
        form_key = normalize_form_name_for_match(form_name, pokemon_name)
        form_types = form.get("types", []) or []
        if not form_types:
            continue

        primary_type = normalize_type_name_for_theme(form_types[0])
        if primary_type:
            type_theme_by_key[form_key] = f"bg-{primary_type}"

    fallback_theme = type_theme_by_key.get("default", "") or next(iter(type_theme_by_key.values()), "")

    for stats_form in stats_tables:
        if stats_form.get("table_theme_class"):
            continue

        form_name = stats_form.get("form_name", "默认")
        form_key = normalize_form_name_for_match(form_name, pokemon_name)
        stats_form["table_theme_class"] = type_theme_by_key.get(form_key, fallback_theme)


def extract_section_text_by_header(header: BeautifulSoup) -> str:
    """提取某个标题节点之后到下一标题前的段落文本"""
    lines: list[str] = []

    for node in header.next_elements:
        if node is header:
            continue

        tag_name = getattr(node, "name", None)
        if tag_name in ["h2", "h3", "h4"]:
            break

        if tag_name in ["p", "li"]:
            text = node.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            if text and text not in lines:
                lines.append(text)

    return " ".join(lines) if lines else ""


def extract_ability_intro_from_table(ability_soup: BeautifulSoup) -> str:
    """从特性页表格结构中提取“文字介绍”内容（兼容无标题段落页面）"""
    markers = ["文字介绍", "文字介紹"]
    stop_keywords = ["特性效果", "特性说明", "特性說明", "特性变更", "特性變更", "对战中", "對戰中"]

    for marker_node in ability_soup.find_all(["b", "th", "td", "span"]):
        marker_text = re.sub(r"\s+", "", marker_node.get_text(" ", strip=True))
        if marker_text not in markers:
            continue

        row = marker_node.find_parent("tr")
        if not row:
            continue

        # 同行内容优先
        for cell in row.find_all(["td", "th"]):
            cell_text = re.sub(r"\s+", " ", cell.get_text(" ", strip=True))
            cleaned = cell_text.replace("文字介绍", "").replace("文字介紹", "").strip(" ：:")
            if cleaned:
                return cleaned

        # 向下查找第一条有效描述
        for next_row in row.find_next_siblings("tr"):
            row_text = re.sub(r"\s+", " ", next_row.get_text(" ", strip=True))
            if not row_text:
                continue
            if any(k in row_text for k in stop_keywords):
                break

            cleaned = row_text.replace("文字介绍", "").replace("文字介紹", "").strip(" ：:")
            if cleaned:
                return cleaned

    return ""


def extract_ability_details(ability_url: str) -> dict[str, str]:
    """提取特性详情：文字介绍 + 特性效果（优先对战中）"""
    try:
        ability_soup = fetch_page(ability_url)
    except Exception as e:
        print(f"读取特性详情失败: {ability_url} ({e})")
        return {"intro": "—", "battle_effect": "—"}

    headers = ability_soup.find_all(["h2", "h3", "h4"])

    def find_section_by_keywords(keywords: list[str]) -> str:
        for h in headers:
            h_text = h.get_text(" ", strip=True)
            if any(k in h_text for k in keywords):
                section_text = extract_section_text_by_header(h)
                if section_text:
                    return section_text
        return ""

    intro_text = find_section_by_keywords(["文字介绍", "文字介紹"])
    if not intro_text:
        intro_text = extract_ability_intro_from_table(ability_soup)

    # 特性效果优先级：对战中 > 特性效果 > 第一节
    battle_text = find_section_by_keywords(["对战中", "對戰中"])
    if not battle_text:
        battle_text = find_section_by_keywords(["特性效果"])

    if not battle_text:
        skip_keywords = ["目录", "目錄", "参考", "參考", "参见", "參見", "外部链接", "外部連結"]
        for h in headers:
            h_text = h.get_text(" ", strip=True)
            if any(k in h_text for k in skip_keywords):
                continue
            section_text = extract_section_text_by_header(h)
            if section_text:
                battle_text = section_text
                break

    return {
        "intro": intro_text or "—",
        "battle_effect": battle_text or "—",
    }


def extract_ability_battle_effect(ability_url: str) -> str:
    """兼容旧调用：提取特性效果文本"""
    return extract_ability_details(ability_url).get("battle_effect", "—")


def extract_form_ability_tables(soup: BeautifulSoup, pokemon_name: str) -> list[dict]:
    """按形态提取特性并补充“文字介绍/特性效果”说明"""
    form_rows = [
        tr for tr in soup.find_all("tr")
        if any(re.fullmatch(r"form\d+", cls or "") for cls in tr.get("class", []))
    ]

    extracted_forms: list[dict] = []
    seen_form_keys: set[str] = set()

    for row in form_rows:
        image_src = extract_primary_form_image_src(row)
        if not image_src:
            continue

        form_name = infer_form_name_from_image_src(image_src, pokemon_name)
        form_key = normalize_form_name_for_match(form_name, pokemon_name)

        ability_links: list[tuple[str, str]] = []
        seen_ability_names: set[str] = set()
        for a in row.find_all("a", href=True):
            href = a.get("href", "")
            if not is_ability_page_link(href):
                continue

            ability_name = re.sub(r"\s+", "", a.get_text(" ", strip=True))
            if not ability_name or ability_name in seen_ability_names:
                continue

            seen_ability_names.add(ability_name)
            ability_links.append((ability_name, urljoin(BASE_URL, href)))

        if not ability_links:
            continue

        if form_key in seen_form_keys:
            continue
        seen_form_keys.add(form_key)

        extracted_forms.append({
            "form_name": form_name,
            "abilities": ability_links,
        })

    if not extracted_forms:
        # 单形态兜底：尽量从信息框提取特性链接
        infobox = next(
            (
                t for t in soup.find_all("table", class_=re.compile("roundy"))
                if (
                    ("属性" in t.get_text(" ", strip=True) or "屬性" in t.get_text(" ", strip=True))
                    and "特性" in t.get_text(" ", strip=True)
                )
            ),
            None,
        )
        if not infobox:
            infobox = soup.find("table", class_=re.compile("roundy"))
        if infobox:
            fallback_links: list[tuple[str, str]] = []
            seen_names: set[str] = set()
            for a in infobox.find_all("a", href=True):
                href = a.get("href", "")
                if not is_ability_page_link(href):
                    continue
                name = re.sub(r"\s+", "", a.get_text(" ", strip=True))
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                fallback_links.append((name, urljoin(BASE_URL, href)))

            if fallback_links:
                extracted_forms.append({
                    "form_name": pokemon_name,
                    "abilities": fallback_links,
                })

    detail_cache: dict[str, dict[str, str]] = {}
    form_tables: list[dict] = []

    for form in extracted_forms:
        rows: list[dict] = []
        for ability_name, ability_url in form["abilities"]:
            if ability_url not in detail_cache:
                detail_cache[ability_url] = extract_ability_details(ability_url)

            details = detail_cache[ability_url]
            rows.append({
                "name": ability_name,
                "intro": details.get("intro", "—"),
                "battle_effect": details.get("battle_effect", "—"),
            })

        if rows:
            form_tables.append({
                "form_name": form["form_name"],
                "rows": rows,
            })

    return form_tables


def normalize_move_header_text(text: str) -> str:
    """规范化招式表头文本（简繁统一）"""
    normalized = re.sub(r"\s+", "", text)
    normalized = normalized.replace("屬性", "属性").replace("分類", "分类").replace("等級", "等级")
    return normalized


def expand_cells_by_colspan(cells: list[BeautifulSoup]) -> list[BeautifulSoup]:
    """按 colspan 展开单元格，便于按列索引读取"""
    expanded: list[BeautifulSoup] = []
    for cell in cells:
        colspan_text = cell.get("colspan", "1")
        colspan = int(colspan_text) if str(colspan_text).isdigit() else 1
        expanded.extend([cell] * max(colspan, 1))
    return expanded


def iter_section_tables(header: BeautifulSoup):
    """遍历某个标题节点到下一个标题前的所有 table"""
    for sibling in header.find_next_siblings():
        if getattr(sibling, "name", None) in ["h2", "h3", "h4", "h5"]:
            break

        if getattr(sibling, "name", None) == "table":
            yield sibling
        elif hasattr(sibling, "find_all"):
            for table in sibling.find_all("table"):
                yield table


def find_move_columns(table: BeautifulSoup) -> dict[str, int] | None:
    """在表格中定位招式字段列索引（招式/属性/分类/威力）"""
    for row in table.find_all("tr"):
        th_cells = row.find_all("th")
        if not th_cells:
            continue

        expanded_headers = expand_cells_by_colspan(th_cells)
        header_texts = [normalize_move_header_text(c.get_text(" ", strip=True)) for c in expanded_headers]

        name_idx = next((i for i, t in enumerate(header_texts) if t == "招式"), None)
        type_idx = next((i for i, t in enumerate(header_texts) if t == "属性"), None)
        category_idx = next((i for i, t in enumerate(header_texts) if t == "分类"), None)
        power_idx = next((i for i, t in enumerate(header_texts) if t == "威力"), None)

        if None not in (name_idx, type_idx, category_idx, power_idx):
            return {
                "name": name_idx,
                "type": type_idx,
                "category": category_idx,
                "power": power_idx,
            }

    return None


def parse_moves_from_table(table: BeautifulSoup, source: str) -> list[dict]:
    """按列语义解析单个招式表"""
    col_map = find_move_columns(table)
    if not col_map:
        return []

    moves: list[dict] = []

    for row in table.find_all("tr"):
        td_cells = row.find_all("td")
        if not td_cells:
            continue

        expanded_cells = expand_cells_by_colspan(td_cells)

        name = expanded_cells[col_map["name"]].get_text(" ", strip=True) if len(expanded_cells) > col_map["name"] else ""
        move_type = expanded_cells[col_map["type"]].get_text(" ", strip=True) if len(expanded_cells) > col_map["type"] else ""
        category = expanded_cells[col_map["category"]].get_text(" ", strip=True) if len(expanded_cells) > col_map["category"] else ""
        power = expanded_cells[col_map["power"]].get_text(" ", strip=True) if len(expanded_cells) > col_map["power"] else ""

        name = name.replace("[详]", "").replace("[詳]", "")
        name = re.sub(r"\s+", "", name)
        move_type = move_type.replace("屬性", "").replace("屬", "").replace("属性", "").strip()
        category = category.replace("招式", "").strip()
        power = re.sub(r"\s+", "", power)

        if not name or name in ["—", "-", "", "招式"] or name.startswith("[[|"):
            continue

        valid_types = set(TYPE_ORDER) | set(TYPE_ICON_ALIASES.keys()) | set(TYPE_ICON_ALIASES.values())
        valid_categories = {"物理", "特殊", "变化", "變化", "—"}
        if move_type not in valid_types:
            continue
        if category not in valid_categories:
            continue

        moves.append({
            "source": source,
            "name": name,
            "type": move_type or "—",
            "category": "变化" if category == "變化" else (category or "—"),
            "power": power or "—",
        })

    return moves


def extract_moves_from_section(soup: BeautifulSoup, section_keywords: list[str], source: str) -> list[dict]:
    """按章节提取招式数据"""
    headers = soup.find_all(["h2", "h3", "h4", "h5"])

    for header in headers:
        header_text = header.get_text(" ", strip=True)
        if not any(keyword in header_text for keyword in section_keywords):
            continue

        for table in iter_section_tables(header):
            parsed = parse_moves_from_table(table, source)
            if parsed:
                return parsed

    return []


def extract_moves(soup: BeautifulSoup) -> list:
    """提取技能列表（升级 + 学习器 + 蛋招式）"""
    levelup_moves = extract_moves_from_section(
        soup,
        ["可学会的招式", "可學會的招式", "可学会招式", "可學會招式"],
        "升级"
    )
    machine_moves = extract_moves_from_section(
        soup,
        ["能使用的招式学习器", "能使用的招式學習器", "招式学习器", "招式學習器"],
        "学习器"
    )
    egg_moves = extract_moves_from_section(
        soup,
        ["蛋招式", "遗传招式", "遺傳招式", "可遗传招式", "可遺傳招式"],
        "蛋招式"
    )

    return levelup_moves + machine_moves + egg_moves


def dedupe_moves_by_name(moves: list[dict]) -> list[dict]:
    """按招式名去重，保留首次出现"""
    deduped: list[dict] = []
    seen_names: set[str] = set()

    for move in moves:
        name = re.sub(r"\s+", "", str(move.get("name", "")))
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        deduped.append(move)

    return deduped


def build_type_canonical_map(name_mapping: dict[str, str] | None = None) -> dict[str, str]:
    """构建属性简称/全称到规范全称的映射"""
    canonical: dict[str, str] = {t: t for t in TYPE_ORDER}

    for short_name, full_name in TYPE_ICON_ALIASES.items():
        canonical[short_name] = full_name
        canonical[full_name] = full_name

    for full_name, short_name in (name_mapping or {}).items():
        canonical[full_name] = full_name
        canonical[short_name] = full_name

    return canonical


def normalize_type_for_match(type_name: str, canonical_map: dict[str, str]) -> str:
    """规范化属性文本用于本系匹配"""
    normalized = str(type_name or "").strip()
    normalized = normalized.replace("屬性", "").replace("属性", "").replace("屬", "")
    return canonical_map.get(normalized, normalized)


def load_ignored_skills(ignore_file: Path = IGNORE_SKILLS_FILE) -> set[str]:
    """加载需要在汇总表中过滤的技能名"""
    ignored: set[str] = set()

    if not ignore_file.exists():
        return ignored

    try:
        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            ignored.add(re.sub(r"\s+", "", text))
    except Exception as e:
        print(f"读取忽略技能文件失败，跳过过滤: {e}")
        return set()

    return ignored


def build_form_move_tables(
    moves: list[dict],
    type_effectiveness_forms: list[dict],
    name_mapping: dict[str, str] | None = None,
    fallback_types: list[str] | None = None,
    ignored_skills: set[str] | None = None,
) -> list[dict]:
    """按形态构建技能池汇总（物理/特殊本系与非本系、变化）"""
    row_labels = ["物理本系", "物理非本系", "特殊本系", "特殊非本系", "变化"]
    canonical_map = build_type_canonical_map(name_mapping)

    forms = type_effectiveness_forms or [{"form_name": "默认", "types": fallback_types or []}]
    form_tables: list[dict] = []

    for form in forms:
        form_types = form.get("types") or []
        form_type_set = {
            normalize_type_for_match(t, canonical_map)
            for t in form_types
            if str(t).strip()
        }

        bucket_map: dict[str, list[str]] = {label: [] for label in row_labels}

        for move in moves:
            name = str(move.get("name", "")).strip()
            if not name:
                continue

            normalized_name = re.sub(r"\s+", "", name)
            if ignored_skills and normalized_name in ignored_skills:
                continue

            category = str(move.get("category", "")).replace("變化", "变化").strip()
            power = str(move.get("power", "")).strip()
            move_type_norm = normalize_type_for_match(str(move.get("type", "")), canonical_map)

            if category == "变化":
                bucket_map["变化"].append(name)
                continue

            if category not in ["物理", "特殊"]:
                continue

            is_stab = bool(move_type_norm) and move_type_norm in form_type_set
            bucket_key = f"{category}{'本系' if is_stab else '非本系'}"

            if power.isdigit():
                bucket_map[bucket_key].append(f"{name}{power}")
            else:
                bucket_map[bucket_key].append(name)

        form_tables.append({
            "form_name": form.get("form_name", "默认"),
            "types": form_types,
            "rows": [{"label": label, "moves": bucket_map[label]} for label in row_labels],
        })

    return form_tables


def extract_image_url(soup: BeautifulSoup, pokemon_number: str) -> str:
    """提取 Pokemon 图片 URL"""
    # 方法1: 查找包含 Pokemon 编号的图片 (如 001Bulbasaur.png)
    imgs = soup.find_all("img")
    for img in imgs:
        src = img.get("src", "")
        # 查找包含编号的图片 (如 001Bulbasaur.png, 001.png 等)
        if pokemon_number in src or f"{int(pokemon_number)}" in src:
            # 排除小图标
            if any(x in src.lower() for x in ["sprite", "dream", "body", "tcg"]):
                continue
            # 确保是主要图片
            if "px-" in src or "thumb" in src:
                if src.startswith("//"):
                    src = "https:" + src
                return src

    # 方法2: 从信息框中的第一个大图片
    infobox = soup.find("table", class_=re.compile("roundy"))
    if infobox:
        img = infobox.find("img")
        if img:
            src = img.get("src", "")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                return src

    return ""


def download_image(url: str, save_path: Path) -> bool:
    """下载图片到本地"""
    if not url:
        return False

    if save_path.exists() and save_path.stat().st_size > 0:
        print(f"使用本地图片: {save_path}")
        return True

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(response.content)

        print(f"图片已下载: {save_path}")
        return True
    except Exception as e:
        print(f"下载图片失败: {e}")
        return False


def generate_html(data: dict, output_dir: Path, html_filename: str) -> Path:
    """生成本地网页"""
    template_text = TEMPLATE_FILE.read_text(encoding="utf-8")
    template = Template(template_text)

    html_content = template.render(data=data)

    output_file = output_dir / html_filename
    output_file.write_text(html_content, encoding="utf-8")

    # 复制原站样式到输出目录，尽量复刻视觉效果
    if SITE_STYLES_FILE.exists():
        shutil.copy2(SITE_STYLES_FILE, output_dir / "wiki_site_styles.css")

    # 复制本地图标资源目录
    if ICONS_DIR.exists():
        shutil.copytree(ICONS_DIR, output_dir / "icons", dirs_exist_ok=True)

    print(f"网页已生成: {output_file}")
    return output_file


def open_html_in_default_browser(html_file: Path) -> None:
    """在系统默认浏览器中打开生成的 HTML 文件"""
    try:
        file_url = html_file.absolute().as_uri()
        opened = webbrowser.open(file_url)
        if opened:
            print(f"已在默认浏览器打开: {html_file}")
        else:
            print(f"未能自动打开浏览器，请手动打开: {html_file}")
    except Exception as e:
        print(f"自动打开浏览器失败: {e}")


def convert_pokemon_to_html(
    identifier: str,
    output_dir: Path,
    open_web: bool = False,
) -> Path:
    """按 identifier 生成单个 Pokemon HTML，返回生成文件路径"""
    # 1. 在列表页面查找 Pokemon
    number, name, detail_url = find_pokemon_link(identifier)

    # 2. 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}")

    # 3. 抓取详情页面
    print(f"正在抓取详情页面: {detail_url}")
    soup = fetch_page(detail_url)

    # 4. 加载映射并提取信息
    print("正在提取信息...")
    name_mapping = load_name_mapping()
    stats_tables = extract_stats_tables(soup)
    if stats_tables:
        first_rows = {r["key"]: r["base"] for r in stats_tables[0]["rows"]}
        stats = {
            "hp": first_rows.get("hp", "?"),
            "attack": first_rows.get("attack", "?"),
            "defense": first_rows.get("defense", "?"),
            "sp_attack": first_rows.get("sp_attack", "?"),
            "sp_defense": first_rows.get("sp_defense", "?"),
            "speed": first_rows.get("speed", "?")
        }
    else:
        stats = extract_base_stats(soup)
        stats_tables = [{
            "form_name": "默认",
            "rows": [
                {"key": "hp", "label": "HP", "base": stats.get("hp", "?"), "base_int": int(stats.get("hp", 0)) if str(stats.get("hp", "")).isdigit() else 0, "row_class": "bgl-HP", "bar_bg_class": "bg-HP", "bar_bd_class": "bd-HP", "lv50": "—", "lv100": "—"},
                {"key": "attack", "label": "攻击", "base": stats.get("attack", "?"), "base_int": int(stats.get("attack", 0)) if str(stats.get("attack", "")).isdigit() else 0, "row_class": "bgl-攻击", "bar_bg_class": "bg-攻击", "bar_bd_class": "bd-攻击", "lv50": "—", "lv100": "—"},
                {"key": "defense", "label": "防御", "base": stats.get("defense", "?"), "base_int": int(stats.get("defense", 0)) if str(stats.get("defense", "")).isdigit() else 0, "row_class": "bgl-防御", "bar_bg_class": "bg-防御", "bar_bd_class": "bd-防御", "lv50": "—", "lv100": "—"},
                {"key": "sp_attack", "label": "特攻", "base": stats.get("sp_attack", "?"), "base_int": int(stats.get("sp_attack", 0)) if str(stats.get("sp_attack", "")).isdigit() else 0, "row_class": "bgl-特攻", "bar_bg_class": "bg-特攻", "bar_bd_class": "bd-特攻", "lv50": "—", "lv100": "—"},
                {"key": "sp_defense", "label": "特防", "base": stats.get("sp_defense", "?"), "base_int": int(stats.get("sp_defense", 0)) if str(stats.get("sp_defense", "")).isdigit() else 0, "row_class": "bgl-特防", "bar_bg_class": "bg-特防", "bar_bd_class": "bd-特防", "lv50": "—", "lv100": "—"},
                {"key": "speed", "label": "速度", "base": stats.get("speed", "?"), "base_int": int(stats.get("speed", 0)) if str(stats.get("speed", "")).isdigit() else 0, "row_class": "bgl-速度", "bar_bg_class": "bg-速度", "bar_bd_class": "bd-速度", "lv50": "—", "lv100": "—"}
            ],
            "total": "?"
        }]

    effectiveness_data = extract_type_effectiveness(soup, name_mapping)
    type_effectiveness_forms = effectiveness_data.get("forms", [])

    if type_effectiveness_forms:
        types = type_effectiveness_forms[0].get("types", [])
        effectiveness = type_effectiveness_forms[0].get("effectiveness", {})
    else:
        types = extract_types(soup, name_mapping)
        effectiveness = effectiveness_data
        type_effectiveness_forms = [{
            "form_name": "默认",
            "types": types,
            "effectiveness": effectiveness,
            "attack_strong": [],
            "attack_weak": []
        }]

    form_ability_tables = extract_form_ability_tables(soup, name)

    moves = dedupe_moves_by_name(extract_moves(soup))
    ignored_skills = load_ignored_skills()
    form_move_tables = build_form_move_tables(
        moves,
        type_effectiveness_forms,
        name_mapping=name_mapping,
        fallback_types=types,
        ignored_skills=ignored_skills,
    )

    # 5. 下载按形态区分的图片
    form_images = extract_form_images(soup, name)
    if not form_images:
        fallback_image_url = extract_image_url(soup, number)
        if fallback_image_url:
            form_images = [{
                "form_name": name,
                "form_key": "default",
                "image_url": fallback_image_url,
                "image_path": "",
            }]

    for form_img in form_images:
        image_url = form_img.get("image_url", "")
        if not image_url:
            continue

        image_filename = make_form_image_filename(number, name, form_img.get("form_key", "default"))
        image_save_path = output_dir / image_filename
        if download_image(image_url, image_save_path):
            form_img["image_path"] = image_filename

    assign_form_images_to_effectiveness_forms(type_effectiveness_forms, form_images, name)
    assign_form_images_to_ability_tables(form_ability_tables, form_images, name)
    assign_stats_theme_classes(stats_tables, type_effectiveness_forms, name)

    image_path = next(
        (
            f.get("image_path", "")
            for f in type_effectiveness_forms
            if normalize_form_name_for_match(f.get("form_name", "默认"), name) == "default" and f.get("image_path")
        ),
        "",
    )
    if not image_path:
        image_path = next((f.get("image_path", "") for f in type_effectiveness_forms if f.get("image_path")), "")

    # 6. 整理数据
    type_icons = build_type_icon_map()
    page_bg_start, page_bg_end = build_page_background_colors(stats_tables, types, name)

    data = {
        "number": number,
        "name": name,
        "detail_url": detail_url,
        "types": types,
        "stats": stats,
        "stats_tables": stats_tables,
        "effectiveness": effectiveness,
        "type_effectiveness_forms": type_effectiveness_forms,
        "form_images": form_images,
        "form_ability_tables": form_ability_tables,
        "form_move_tables": form_move_tables,
        "type_icons": type_icons,
        "moves": moves,
        "image_path": image_path,
        "page_bg_start": page_bg_start,
        "page_bg_end": page_bg_end,
    }

    # 7. 生成网页
    html_filename = f"{number}{name}.html"
    html_file = generate_html(data, output_dir, html_filename)
    if open_web:
        open_html_in_default_browser(html_file)

    print(f"\n完成! 输出目录: {output_dir.absolute()}")
    print(f"网页文件: {html_file.absolute()}")
    return html_file


def render_mvp_index_page(initial_identifier: str | None = None) -> str:
    """渲染本地服务版 MVP 首页"""
    initial = json.dumps(initial_identifier or "", ensure_ascii=False)
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Pokefetch 本地服务版</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fb; }}
    .app {{ display: flex; height: 100vh; }}
    .left {{ width: 340px; border-right: 1px solid #dfe3eb; background: #fff; display: flex; flex-direction: column; }}
    .search {{ padding: 12px; border-bottom: 1px solid #eef1f6; }}
    .search-input-wrap {{ position: relative; }}
    .search input {{ width: 100%; padding: 10px 36px 10px 12px; border: 1px solid #cfd6e4; border-radius: 8px; }}
    .search-clear-btn {{
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      width: 20px;
      height: 20px;
      border: 0;
      border-radius: 50%;
      display: none;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      background: #d1d5db;
      color: #fff;
      font-size: 12px;
      line-height: 1;
      padding: 0;
    }}
    .search-clear-btn.show {{ display: inline-flex; }}
    .search-clear-btn:hover {{ background: #9ca3af; }}
    .list {{ overflow: auto; flex: 1; }}
    .item {{ width: 100%; border: 0; background: #fff; text-align: left; padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f0f2f7; }}
    .item:hover {{ background: #f7faff; }}
    .item.active {{ background: #eaf2ff; }}
    .item-main {{ display: flex; align-items: baseline; gap: 8px; }}
    .item-sub {{ margin-top: 5px; font-size: 12px; color: #64748b; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
    .id {{ color: #6b7280; margin-right: 2px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .name {{ color: #111827; font-weight: 600; }}
    .name-en {{ color: #64748b; }}
    .type-chip {{ border: 1px solid transparent; border-radius: 10px; padding: 1px 6px; color: #fff; font-weight: 600; }}
    .right {{ flex: 1; display: flex; flex-direction: column; position: relative; }}
    .toolbar {{ height: 46px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border-bottom: 1px solid #dfe3eb; background: #fff; color: #4b5563; gap: 12px; }}
    #status {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }}
    .toolbar-actions {{ display: flex; align-items: center; gap: 8px; }}
    .btn {{ border: 1px solid #cfd6e4; background: #fff; color: #1f2937; border-radius: 6px; padding: 6px 10px; cursor: pointer; }}
    .btn:hover {{ background: #f3f6fb; }}
    .btn:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    iframe {{ border: 0; width: 100%; height: calc(100vh - 46px); background: #fff; }}
    .empty-state {{
      position: absolute;
      left: 0;
      right: 0;
      top: 46px;
      bottom: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
      color: #334155;
      z-index: 2;
      padding: 20px;
      text-align: center;
    }}
    .empty-state.show {{ display: flex; }}
    .empty-card {{
      max-width: 420px;
      border: 1px solid #dbe2f0;
      border-radius: 12px;
      padding: 18px 20px;
      background: #ffffff;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }}
    .empty-title {{ font-size: 16px; font-weight: 600; color: #0f172a; margin-bottom: 6px; }}
    .empty-desc {{ font-size: 13px; color: #64748b; line-height: 1.6; }}
    .loading-mask {{
      position: absolute;
      left: 0;
      right: 0;
      top: 46px;
      bottom: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(255, 255, 255, 0.72);
      z-index: 10;
    }}
    .loading-mask.show {{ display: flex; }}
    .loading-card {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border: 1px solid #dbe2f0;
      border-radius: 8px;
      background: #ffffff;
      color: #334155;
      box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
    }}
    .spinner {{
      width: 18px;
      height: 18px;
      border: 2px solid #c7d2fe;
      border-top-color: #4f46e5;
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
    }}
    @keyframes spin {{
      from {{ transform: rotate(0deg); }}
      to {{ transform: rotate(360deg); }}
    }}
  </style>
</head>
<body>
  <div class=\"app\">
    <aside class=\"left\">
      <div class=\"search\">
        <div class=\"toolbar-actions\" style=\"margin-bottom: 8px;\">
          <button id=\"refreshListBtn\" class=\"btn\" type=\"button\">刷新列表（重新拉取）</button>
          <button id=\"luckyBtn\" class=\"btn\" type=\"button\">手气不错</button>
        </div>
        <div class=\"search-input-wrap\">
          <input id=\"searchInput\" placeholder=\"搜索编号/名字/形态(中英文拼音)\" />
          <button id=\"clearSearchBtn\" class=\"search-clear-btn\" type=\"button\" aria-label=\"清空搜索\">×</button>
        </div>
      </div>
      <div id=\"list\" class=\"list\"></div>
    </aside>
    <section class=\"right\">
      <div class=\"toolbar\">
        <span id=\"status\">就绪</span>
        <div class=\"toolbar-actions\">
          <button id=\"refreshBtn\" class=\"btn\" type=\"button\">刷新当前（忽略缓存）</button>
        </div>
      </div>
      <iframe id=\"detailFrame\" title=\"pokemon-detail\"></iframe>
      <div id=\"emptyState\" class=\"empty-state show\">
        <div class=\"empty-card\">
          <div class=\"empty-title\">欢迎使用 Pokefetch</div>
          <div class=\"empty-desc\">请从左侧选择一个宝可梦以加载详情。<br/>也可以点击“手气不错”随机开始。</div>
        </div>
      </div>
      <div id=\"loadingMask\" class=\"loading-mask\">
        <div class=\"loading-card\">
          <div class=\"spinner\"></div>
          <span id=\"loadingText\">正在加载，请稍候...</span>
        </div>
      </div>
    </section>
  </div>

  <script>
    const initialIdentifier = {initial};
    const listEl = document.getElementById('list');
    const searchInput = document.getElementById('searchInput');
    const detailFrame = document.getElementById('detailFrame');
    const statusEl = document.getElementById('status');
    const refreshBtn = document.getElementById('refreshBtn');
    const refreshListBtn = document.getElementById('refreshListBtn');
    const luckyBtn = document.getElementById('luckyBtn');
    const clearSearchBtn = document.getElementById('clearSearchBtn');
    const loadingMask = document.getElementById('loadingMask');
    const loadingText = document.getElementById('loadingText');
    const emptyState = document.getElementById('emptyState');
    let currentIdentifier = '';
    let currentSelectionKey = '';
    let currentName = '';
    let currentItems = [];

    function setStatus(text) {{
      statusEl.textContent = text;
    }}

    function updateSearchClearButton() {{
      const hasText = searchInput.value.trim().length > 0;
      clearSearchBtn.classList.toggle('show', hasText);
    }}

    function setActive(itemKey, scrollIntoView = false) {{
      currentSelectionKey = itemKey || '';
      let target = null;
      for (const btn of listEl.querySelectorAll('.item')) {{
        const isActive = (btn.dataset.key || '') === (itemKey || '');
        btn.classList.toggle('active', isActive);
        if (isActive) target = btn;
      }}
      if (scrollIntoView && target) {{
        target.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
      }}
    }}

    function setLoading(loading, text = '正在加载，请稍候...') {{
      loadingMask.classList.toggle('show', loading);
      loadingText.textContent = text;
      refreshBtn.disabled = loading;
      refreshListBtn.disabled = loading;
      luckyBtn.disabled = loading;
      clearSearchBtn.disabled = loading;
      listEl.style.pointerEvents = loading ? 'none' : 'auto';
      searchInput.style.pointerEvents = loading ? 'none' : 'auto';
    }}

    function showEmptyState(visible) {{
      emptyState.classList.toggle('show', !!visible);
    }}

    async function fetchList(query = '', forceRefresh = false) {{
      const url = '/api/pokemon?q=' + encodeURIComponent(query) + (forceRefresh ? '&refresh=1' : '');
      const res = await fetch(url);
      if (!res.ok) throw new Error('加载列表失败');
      const data = await res.json();
      return data.items || [];
    }}

    async function renderPokemon(identifier, displayName = '', forceRefresh = false, itemKey = '') {{
      if (!identifier) return;
      const hadContent = !!detailFrame.getAttribute('src');
      currentIdentifier = identifier;
      if (itemKey) setActive(itemKey);
      currentName = displayName || currentName || identifier;
      const actionText = forceRefresh ? '正在刷新' : '正在加载';
      setStatus(actionText + ' ' + (displayName || identifier) + ' 页面...');
      showEmptyState(false);
      setLoading(true, actionText + ' ' + (displayName || identifier) + ' ...');
      try {{
        const res = await fetch('/api/render', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ identifier, refresh_cache: forceRefresh }})
        }});
        const data = await res.json();
        if (!res.ok || !data.ok) {{
          throw new Error(data.error || '生成失败');
        }}
        detailFrame.src = data.html_url + '?t=' + Date.now();
        setStatus('已加载：' + (displayName || currentName || identifier));
      }} catch (err) {{
        if (!hadContent) showEmptyState(true);
        throw err;
      }} finally {{
        setLoading(false);
      }}
    }}

    function renderList(items) {{
      currentItems = items || [];
      listEl.innerHTML = '';
      for (const item of currentItems) {{
        const btn = document.createElement('button');
        btn.className = 'item';
        btn.dataset.number = item.number;
        btn.dataset.key = item.item_key || `${{item.number}}-${{item.name}}`;
        const typeHtml = (item.types || []).map((t, i) => {{
          const c = (item.type_colors || [])[i] || '#94a3b8';
          return `<span class=\"type-chip\" style=\"background:${{c}};border-color:${{c}};\">${{t}}</span>`;
        }}).join('');
        btn.innerHTML = `<div class=\"item-main\"><span class=\"id\">#${{item.number}}</span><span class=\"name\">${{item.name}}</span></div><div class=\"item-sub\"><span class=\"name-en\">${{item.name_en || ''}}</span>${{typeHtml}}</div>`;
        btn.onclick = async () => {{
          const identifier = item.number;
          setActive(btn.dataset.key || '');
          try {{
            await renderPokemon(identifier, item.name, false, btn.dataset.key || '');
          }} catch (err) {{
            setStatus('错误：' + err.message);
          }}
        }};
        listEl.appendChild(btn);
      }}
    }}

    refreshBtn.addEventListener('click', async () => {{
      if (!currentIdentifier) {{
        setStatus('请先从左侧选择一个宝可梦');
        return;
      }}
      try {{
        await renderPokemon(currentIdentifier, currentName || currentIdentifier, true, currentSelectionKey);
      }} catch (err) {{
        setStatus('错误：' + err.message);
      }}
    }});

    refreshListBtn.addEventListener('click', async () => {{
      try {{
        setStatus('正在刷新左侧列表...');
        const items = await fetchList(searchInput.value.trim(), true);
        renderList(items);
        setStatus('列表已刷新');
      }} catch (err) {{
        setStatus('错误：' + err.message);
      }}
    }});

    luckyBtn.addEventListener('click', async () => {{
      try {{
        let items = currentItems;
        if (!items || items.length === 0) {{
          items = await fetchList(searchInput.value.trim());
          renderList(items);
        }}
        if (!items || items.length === 0) {{
          setStatus('当前列表为空，无法随机选择');
          return;
        }}
        const picked = items[Math.floor(Math.random() * items.length)];
        const pickedKey = picked.item_key || `${{picked.number}}-${{picked.name}}`;
        const pickedIdentifier = picked.number;
        setActive(pickedKey, true);
        await renderPokemon(pickedIdentifier, picked.name, false, pickedKey);
      }} catch (err) {{
        setStatus('错误：' + err.message);
      }}
    }});

    let timer = null;
    searchInput.addEventListener('input', () => {{
      updateSearchClearButton();
      clearTimeout(timer);
      timer = setTimeout(async () => {{
        try {{
          const items = await fetchList(searchInput.value.trim());
          renderList(items);
        }} catch (err) {{
          setStatus('错误：' + err.message);
        }}
      }}, 200);
    }});

    clearSearchBtn.addEventListener('click', async () => {{
      searchInput.value = '';
      updateSearchClearButton();
      searchInput.focus();
      try {{
        const items = await fetchList('');
        renderList(items);
        setStatus('已清空搜索');
      }} catch (err) {{
        setStatus('错误：' + err.message);
      }}
    }});

    (async () => {{
      try {{
        const items = await fetchList('');
        renderList(items);
        updateSearchClearButton();
        if (initialIdentifier) {{
          await renderPokemon(initialIdentifier, initialIdentifier);
        }} else {{
          showEmptyState(true);
          setStatus('请选择左侧宝可梦以开始');
        }}
      }} catch (err) {{
        setStatus('错误：' + err.message);
      }}
    }})();
  </script>
</body>
</html>
"""


def start_local_mvp_service(output_dir: Path, initial_identifier: str | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    """启动本地服务版 MVP：左侧列表 + 右侧详情页"""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    class PokemonMVPHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status_code: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, text: str, status_code: int = 200) -> None:
            body = text.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_out_file(self, sub_path: str) -> None:
            relative = unquote(sub_path).lstrip("/")
            target = (output_dir / relative).resolve()
            if not target.is_file() or not target.is_relative_to(output_dir):
                self.send_error(404, "File not found")
                return

            mime, _ = mimetypes.guess_type(str(target))
            content_type = mime or "application/octet-stream"
            data = target.read_bytes()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args):
            return

        def do_GET(self):
            path_only = self.path.split("?", 1)[0]

            if path_only == "/":
                self._send_text(render_mvp_index_page(initial_identifier))
                return

            if path_only == "/api/pokemon":
                parsed_query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                query = parsed_query.get("q", [""])[0]
                refresh_flag = (parsed_query.get("refresh", ["0"])[0] or "0").lower()
                if refresh_flag in ["1", "true", "yes", "y"]:
                    refresh_pokemon_index(force_refresh_cache=True)
                entries = search_pokemon_entries(query)
                self._send_json({"items": entries})
                return

            if path_only.startswith("/out/"):
                self._serve_out_file(path_only[len("/out/"):])
                return

            self.send_error(404, "Not found")

        def do_POST(self):
            if self.path != "/api/render":
                self.send_error(404, "Not found")
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0

            body_raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(body_raw.decode("utf-8"))
            except Exception:
                self._send_json({"ok": False, "error": "请求体必须是 JSON"}, 400)
                return

            identifier = str(payload.get("identifier", "")).strip()
            if not identifier:
                self._send_json({"ok": False, "error": "identifier 不能为空"}, 400)
                return

            refresh_cache = bool(payload.get("refresh_cache", False))

            try:
                global REFRESH_CACHE
                old_refresh_cache = REFRESH_CACHE
                if refresh_cache:
                    REFRESH_CACHE = True

                html_file = convert_pokemon_to_html(identifier, output_dir, open_web=False)
                number_match = re.match(r"^(\d{4})", html_file.name)
                number = number_match.group(1) if number_match else ""
                self._send_json({
                    "ok": True,
                    "html_url": f"/out/{quote(html_file.name)}",
                    "file_name": html_file.name,
                    "number": number,
                    "refresh_cache": refresh_cache,
                })
            except ValueError as e:
                self._send_json({"ok": False, "error": str(e)}, 400)
            except requests.RequestException as e:
                self._send_json({"ok": False, "error": f"网络错误: {e}"}, 502)
            except Exception as e:
                self._send_json({"ok": False, "error": f"服务异常: {e}"}, 500)
            finally:
                REFRESH_CACHE = old_refresh_cache

    server = ThreadingHTTPServer((host, port), PokemonMVPHandler)
    app_url = f"http://{host}:{port}/"
    print(f"本地服务已启动: {app_url}")
    print("按 Enter 重新打开页面，按 Ctrl+C 停止服务")

    def open_app_page() -> None:
        try:
            webbrowser.open(app_url)
        except Exception:
            pass

    def listen_enter_to_reopen() -> None:
        while True:
            try:
                user_input = input()
            except EOFError:
                break
            except Exception:
                break

            if user_input.strip() == "":
                print("重新打开页面...")
                open_app_page()

    open_app_page()
    threading.Thread(target=listen_enter_to_reopen, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Pokemon PPT Helper Tool")
    parser.add_argument(
        "identifier",
        nargs="?",
        help="Pokemon 编号(如0001)或名字(如妙蛙种子)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用页面缓存，每次都重新请求网页"
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="刷新缓存（重新请求并覆盖缓存文件）"
    )
    parser.add_argument(
        "--output-dir",
        default="out",
        help="输出目录（默认: out）"
    )
    parser.add_argument(
        "-w",
        "--open-web",
        action="store_true",
        help="生成后自动用系统默认浏览器打开网页"
    )
    parser.add_argument(
        "-f",
        "--fetch-only",
        action="store_true",
        help="仅执行抓取并生成（旧逻辑），不启动本地服务"
    )

    args = parser.parse_args()

    global CACHE_ENABLED, REFRESH_CACHE
    CACHE_ENABLED = not args.no_cache
    REFRESH_CACHE = args.refresh_cache

    output_dir = Path(args.output_dir)

    try:
        if args.fetch_only:
            if not args.identifier:
                parser.error("--fetch-only/-f 模式下必须提供 identifier")
            convert_pokemon_to_html(args.identifier, output_dir, open_web=args.open_web)
        else:
            start_local_mvp_service(output_dir, initial_identifier=args.identifier)

    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"网络错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
