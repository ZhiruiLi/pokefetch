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


def extract_types(soup: BeautifulSoup) -> list:
    """提取属性"""
    types = []

    # 方法1: 从信息框中提取 - 查找包含"属性"文本的 roundy 表格
    tables = soup.find_all("table", class_="roundy")
    for table in tables:
        text = table.get_text(strip=True)
        # 检查是否是信息框（包含属性、分类等）
        if "属性" in text and "分类" in text:
            rows = table.find_all("tr")
            for row in rows:
                th = row.find("th")
                if th and "属性" in th.get_text():
                    # 在同一行或下一行查找属性值
                    tds = row.find_all("td")
                    for td in tds:
                        # 获取所有文本
                        type_text = td.get_text(strip=True)
                        # 清理属性名称
                        type_text = type_text.replace("屬性", "").replace("屬", "").replace("属性", "")
                        # 如果清理后还有内容，添加到列表
                        if type_text and type_text not in ["", "宝可梦"]:
                            types.append(type_text)
                    break
            break

    # 方法2: 从页面文本中提取
    if not types:
        # 查找 "是xx属性/xx属性宝可梦" 的模式
        text = soup.get_text()
        patterns = [
            r"是(.+?)[屬性|属性][／/](.+?)[屬性|属性]宝可梦",  # 双属性
            r"是(.+?)[屬性|属性]宝可梦",  # 单属性
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                types = [g.strip().replace("屬", "").replace("属性", "") for g in groups if g.strip()]
                break

    return list(set(types)) if types else []


def extract_type_effectiveness(soup: BeautifulSoup) -> dict:
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
    template = Template("""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ data.number }} {{ data.name }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5em;
            color: #333;
            margin-bottom: 10px;
        }
        .header .number {
            font-size: 1.2em;
            color: #666;
            font-weight: bold;
        }
        .image-section {
            text-align: center;
            margin-bottom: 30px;
        }
        .image-section img {
            max-width: 300px;
            max-height: 300px;
            border-radius: 10px;
        }
        .info-section {
            margin-bottom: 25px;
        }
        .info-section h2 {
            font-size: 1.5em;
            color: #444;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        .types {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .type {
            padding: 8px 20px;
            border-radius: 20px;
            color: white;
            font-weight: bold;
            text-transform: uppercase;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
        }
        .stat-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-item .label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }
        .stat-item .value {
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
        }
        .effectiveness-list {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .effectiveness-item {
            padding: 5px 15px;
            border-radius: 15px;
            background: #e9ecef;
            font-size: 0.9em;
        }
        .weak { background: #ff6b6b; color: white; }
        .resist { background: #51cf66; color: white; }
        .immune { background: #868e96; color: white; }
        .moves-table {
            width: 100%;
            border-collapse: collapse;
        }
        .moves-table th,
        .moves-table td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        .moves-table th {
            background: #f8f9fa;
            font-weight: bold;
        }
        .moves-table tr:hover {
            background: #f8f9fa;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="number">#{{ data.number }}</div>
            <h1>{{ data.name }}</h1>
        </div>

        <div class="image-section">
            {% if data.image_path %}
            <img src="{{ data.image_path }}" alt="{{ data.name }}">
            {% else %}
            <p>暂无图片</p>
            {% endif %}
        </div>

        <div class="info-section">
            <h2>属性</h2>
            <div class="types">
                {% for type in data.types %}
                <span class="type">{{ type }}</span>
                {% endfor %}
            </div>
        </div>

        <div class="info-section">
            <h2>种族值</h2>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="label">HP</div>
                    <div class="value">{{ data.stats.hp or "?" }}</div>
                </div>
                <div class="stat-item">
                    <div class="label">攻击</div>
                    <div class="value">{{ data.stats.attack or "?" }}</div>
                </div>
                <div class="stat-item">
                    <div class="label">防御</div>
                    <div class="value">{{ data.stats.defense or "?" }}</div>
                </div>
                <div class="stat-item">
                    <div class="label">特攻</div>
                    <div class="value">{{ data.stats.sp_attack or "?" }}</div>
                </div>
                <div class="stat-item">
                    <div class="label">特防</div>
                    <div class="value">{{ data.stats.sp_defense or "?" }}</div>
                </div>
                <div class="stat-item">
                    <div class="label">速度</div>
                    <div class="value">{{ data.stats.speed or "?" }}</div>
                </div>
            </div>
        </div>

        <div class="info-section">
            <h2>属性克制</h2>
            <h3>弱点</h3>
            <div class="effectiveness-list">
                {% for type in data.effectiveness.weak %}
                <span class="effectiveness-item weak">{{ type }}</span>
                {% endfor %}
            </div>
            <h3 style="margin-top: 15px;">抗性</h3>
            <div class="effectiveness-list">
                {% for type in data.effectiveness.resist %}
                <span class="effectiveness-item resist">{{ type }}</span>
                {% endfor %}
            </div>
            {% if data.effectiveness.immune %}
            <h3 style="margin-top: 15px;">免疫</h3>
            <div class="effectiveness-list">
                {% for type in data.effectiveness.immune %}
                <span class="effectiveness-item immune">{{ type }}</span>
                {% endfor %}
            </div>
            {% endif %}
        </div>

        <div class="info-section">
            <h2>技能列表</h2>
            <table class="moves-table">
                <thead>
                    <tr>
                        <th>等级</th>
                        <th>招式</th>
                        <th>属性</th>
                    </tr>
                </thead>
                <tbody>
                    {% for move in data.moves %}
                    <tr>
                        <td>{{ move.level }}</td>
                        <td>{{ move.name }}</td>
                        <td>{{ move.type }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // 开发辅助：检测 index.html 内容变化后自动刷新页面
        (function () {
            const CHECK_INTERVAL_MS = 2000;
            let baseline = null;

            async function checkForUpdates() {
                // file:// 协议下多数浏览器会拦截 fetch，本逻辑主要用于 http 本地预览
                if (window.location.protocol === 'file:') {
                    return;
                }

                try {
                    const response = await fetch(window.location.pathname + '?_reload=' + Date.now(), {
                        cache: 'no-store'
                    });
                    if (!response.ok) return;

                    const latest = await response.text();
                    if (!latest) return;

                    if (baseline === null) {
                        baseline = latest;
                        return;
                    }

                    if (latest !== baseline) {
                        window.location.reload();
                        return;
                    }
                } catch (e) {
                    // 忽略轮询异常，避免影响页面使用
                }
            }

            checkForUpdates();
            setInterval(checkForUpdates, CHECK_INTERVAL_MS);
        })();
    </script>
</body>
</html>
    """)

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

        # 4. 提取信息
        print("正在提取信息...")
        stats = extract_base_stats(soup)
        types = extract_types(soup)
        effectiveness = extract_type_effectiveness(soup)
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
