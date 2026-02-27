#!/usr/bin/env python3
"""
Pokemon PPT Helper Tool
从 wiki.52poke.com 抓取 Pokemon 信息并生成本地网页
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from jinja2 import Template

# 常量定义
BASE_URL = "https://wiki.52poke.com"
LIST_URL = f"{BASE_URL}/wiki/宝可梦列表（按全国图鉴编号）"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
}
CACHE_DIR = Path(".cache/pages")
CACHE_ENABLED = True
REFRESH_CACHE = False
NAME_MAPPING_FILE = Path("name_mapping.txt")
TEMPLATE_FILE = Path(__file__).with_name("template.html")
SITE_STYLES_FILE = Path(__file__).with_name("wiki_site_styles.css")

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

    # 查找所有表格 (使用 roundy 或 eplist 类)
    tables = soup.find_all("table", class_=["roundy", "eplist", "sortable"])

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

            # 提取名字 (第四列，包含中文名)
            name_cell = cells[3] if len(cells) > 3 else cells[2]
            name_link = name_cell.find("a")
            if not name_link:
                # 尝试直接从单元格文本获取
                name = name_cell.get_text(strip=True)
                href = ""
            else:
                name = name_link.get_text(strip=True)
                href = name_link.get("href", "")

            if not name:
                continue

            # 匹配
            if is_number and num == search_num:
                print(f"找到 Pokemon: #{num} {name}")
                # 构建详情页URL
                if href:
                    detail_url = urljoin(BASE_URL, href)
                else:
                    detail_url = f"{BASE_URL}/wiki/{name}"
                return num, name, detail_url
            elif not is_number and identifier in name:
                print(f"找到 Pokemon: #{num} {name}")
                if href:
                    detail_url = urljoin(BASE_URL, href)
                else:
                    detail_url = f"{BASE_URL}/wiki/{name}"
                return num, name, detail_url

    raise ValueError(f"未找到 Pokemon: {identifier}")


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
        "total": total
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


def extract_moves(soup: BeautifulSoup) -> list:
    """提取技能列表"""
    moves = []

    # 查找可学会招式章节 - 尝试多种可能的标题
    headers = soup.find_all(["h2", "h3", "h4"])
    target_header = None

    for header in headers:
        header_text = header.get_text(strip=True)
        if any(keyword in header_text for keyword in ["可学会招式", "可學會招式", "招式表"]):
            target_header = header
            break

    if not target_header:
        return moves

    # 查找招式表格 - 在标题后查找包含招式数据的表格
    tables = target_header.find_all_next("table", limit=5)

    for table in tables:
        # 检查表格是否包含招式数据
        text = table.get_text(strip=True)
        if any(keyword in text for keyword in ["撞击", "摇尾巴", "藤鞭", "等級", "等级"]):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                # 需要至少3列数据（等级、招式名、属性）
                if len(cells) >= 4:
                    # 第一列是等级，第三列是招式名，第四列是属性
                    level = cells[0].get_text(strip=True)
                    name = cells[2].get_text(strip=True)
                    move_type = cells[3].get_text(strip=True)

                    # 清理数据
                    name = name.replace("[详]", "").replace("[詳]", "")
                    move_type = move_type.replace("屬性", "").replace("屬", "").replace("属性", "")

                    # 只添加有效的招式数据（有名称且不是表头）
                    if name and name not in ["—", "-", "", "招式"] and not name.startswith("[[|"):
                        moves.append({
                            "level": level if level else "—",
                            "name": name,
                            "type": move_type
                        })

            if moves:
                break

    return moves[:20]  # 限制数量


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


def generate_html(data: dict, output_dir: Path) -> None:
    """生成本地网页"""
    template_text = TEMPLATE_FILE.read_text(encoding="utf-8")
    template = Template(template_text)

    html_content = template.render(data=data)

    output_file = output_dir / "index.html"
    output_file.write_text(html_content, encoding="utf-8")

    # 复制原站样式到输出目录，尽量复刻视觉效果
    if SITE_STYLES_FILE.exists():
        shutil.copy2(SITE_STYLES_FILE, output_dir / "wiki_site_styles.css")

    print(f"网页已生成: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Pokemon PPT Helper Tool")
    parser.add_argument(
        "identifier",
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

    args = parser.parse_args()

    global CACHE_ENABLED, REFRESH_CACHE
    CACHE_ENABLED = not args.no_cache
    REFRESH_CACHE = args.refresh_cache

    try:
        # 1. 在列表页面查找 Pokemon
        number, name, detail_url = find_pokemon_link(args.identifier)

        # 2. 创建输出目录
        output_dir = Path(f"{number}{name}")
        output_dir.mkdir(exist_ok=True)
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

        moves = extract_moves(soup)
        image_url = extract_image_url(soup, number)

        # 5. 下载图片
        image_path = ""
        if image_url:
            image_filename = f"{number}{name}.png"
            image_save_path = output_dir / image_filename
            if download_image(image_url, image_save_path):
                image_path = image_filename

        # 6. 整理数据
        data = {
            "number": number,
            "name": name,
            "types": types,
            "stats": stats,
            "stats_tables": stats_tables,
            "effectiveness": effectiveness,
            "type_effectiveness_forms": type_effectiveness_forms,
            "moves": moves,
            "image_path": image_path
        }

        # 7. 生成网页
        generate_html(data, output_dir)

        print(f"\n完成! 输出目录: {output_dir.absolute()}")

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
