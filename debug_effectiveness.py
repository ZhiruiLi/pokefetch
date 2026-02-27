#!/usr/bin/env python3
"""调试属性相性提取 - 改进版"""
import requests
from bs4 import BeautifulSoup
import re

BASE_URL = "https://wiki.52poke.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
}

# 抓取妙蛙种子详情页
url = f"{BASE_URL}/wiki/妙蛙种子"
response = requests.get(url, headers=HEADERS, timeout=30)
response.encoding = "utf-8"
soup = BeautifulSoup(response.text, "lxml")

print("=== 1. 使用 get_text() 查找属性相性标题 ===")
headers = soup.find_all(["h2", "h3"])
target_header = None
for h in headers:
    if "属性相性" in h.get_text():
        target_header = h
        print(f"找到标题: {h.name} - {h.get_text(strip=True)}")
        break

print(f"\n目标标题: {target_header}")

print("\n=== 2. 在属性相性标题后查找表格 ===")
if target_header:
    # 获取标题后的所有元素
    current = target_header.find_next_sibling()
    count = 0
    while current and count < 15:
        if current.name:
            text_preview = current.get_text()[:80] if current.get_text() else '(无文本)'
            print(f"[{count}] {current.name}: {text_preview}")
            # 如果是表格，打印更多细节
            if current.name == "table":
                print("  这是一个表格!")
                rows = current.find_all("tr")
                print(f"  行数: {len(rows)}")
                for j, row in enumerate(rows[:5]):
                    cells = row.find_all(["td", "th"])
                    cell_texts = [c.get_text(strip=True)[:15] for c in cells]
                    print(f"    行{j}: {cell_texts}")
        current = current.find_next_sibling()
        count += 1

print("\n=== 3. 使用 find_all_next 查找表格 ===")
if target_header:
    tables = target_header.find_all_next("table", class_="roundy", limit=3)
    print(f"找到 {len(tables)} 个表格")
    for i, table in enumerate(tables):
        print(f"\n表格 {i}:")
        text = table.get_text()[:200]
        print(f"  文本预览: {text}")
        rows = table.find_all("tr")
        print(f"  行数: {len(rows)}")
        for j, row in enumerate(rows[:8]):
            cells = row.find_all(["td", "th"])
            cell_texts = [c.get_text(strip=True)[:20] for c in cells]
            print(f"    行{j}: {cell_texts}")
