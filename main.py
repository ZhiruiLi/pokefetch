#!/usr/bin/env python3
"""
Pokemon PPT Helper Tool
从 wiki.52poke.com 抓取 Pokemon 信息并生成本地网页
"""

import argparse
import hashlib
import os
import re
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
    """提取属性克制关系（防守向）"""
    effectiveness = {
        "weak": [],      # 弱点 (2x/4x)
        "resist": [],    # 抗性 (0.5x)
        "immune": [],    # 免疫 (0x)
        "strong": [],    # 强抗性 (0.25x)
        "weak_attack": []  # 预留：进攻向劣势
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
        return effectiveness

    # 在章节后查找相性表格
    tables = target_header.find_all_next("table", class_="roundy", limit=5)

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        data_cells = rows[1].find_all(["th", "td"])

        # 防守向表格特征：首行为“进攻招式属性/一般/格斗...”，次行前3列是防守方属性和空白
        if len(header_cells) < 19 or len(data_cells) < 21:
            continue

        header_title = header_cells[0].get_text(strip=True)
        if header_title not in ["进攻招式属性", "進攻招式屬性"]:
            continue

        attack_types = [c.get_text(strip=True) for c in header_cells[1:19]]
        multipliers = [c.get_text(strip=True) for c in data_cells[3:3 + len(attack_types)]]

        if len(multipliers) != len(attack_types):
            continue

        for type_name, mult in zip(attack_types, multipliers):
            type_name = type_name.replace("屬性", "").replace("屬", "").replace("属性", "")
            mult = mult.strip()

            if not type_name or not mult:
                continue

            if mult in ["0", "0×"]:
                effectiveness["immune"].append(type_name)
            elif mult in ["1⁄4", "1/4", "¼"]:
                effectiveness["strong"].append(type_name)
                effectiveness["resist"].append(type_name)
            elif mult in ["1⁄2", "1/2", "½"]:
                effectiveness["resist"].append(type_name)
            elif mult in ["2", "2×", "4", "4×"]:
                effectiveness["weak"].append(type_name)

        # 去重并保持顺序
        effectiveness["weak"] = list(dict.fromkeys(effectiveness["weak"]))
        effectiveness["resist"] = list(dict.fromkeys(effectiveness["resist"]))
        effectiveness["immune"] = list(dict.fromkeys(effectiveness["immune"]))
        effectiveness["strong"] = list(dict.fromkeys(effectiveness["strong"]))
        break

    # 应用名称映射
    if name_mapping:
        for key in ["weak", "resist", "immune", "strong", "weak_attack"]:
            effectiveness[key] = [name_mapping.get(t, t) for t in effectiveness[key]]

    return effectiveness


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
        stats = extract_base_stats(soup)
        types = extract_types(soup, name_mapping)
        effectiveness = extract_type_effectiveness(soup, name_mapping)
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
            "effectiveness": effectiveness,
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
