import requests
from bs4 import BeautifulSoup
import re

url = 'https://wiki.52poke.com/wiki/%E5%A6%99%E8%9B%99%E7%A7%8D%E5%AD%90'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
response = requests.get(url, headers=headers, timeout=30)
soup = BeautifulSoup(response.content, 'lxml')

# Find moves section
print('=== Looking for moves section ===')
headers_list = soup.find_all(["h2", "h3", "h4"])

# Look for specific section
print('\n=== Finding 可学会招式 section ===')
for h in headers_list:
    text = h.get_text(strip=True)
    if "可学会" in text and "招式" in text:
        print(f'Found: {text}')
        # Look at next siblings
        next_sibling = h.find_next_sibling()
        count = 0
        while next_sibling and count < 10:
            if next_sibling.name == "table":
                print(f'Found table: {next_sibling.get_text()[:200]}')
                # Check if it has move data
                table_text = next_sibling.get_text()
                if "撞击" in table_text or "摇尾巴" in table_text or "藤鞭" in table_text:
                    print('This table contains moves!')
                    rows = next_sibling.find_all("tr")
                    print(f'Rows: {len(rows)}')
                    for i, row in enumerate(rows[:15]):
                        cells = row.find_all(["th", "td"])
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        print(f'  Row {i}: {cell_texts}')
                break
            next_sibling = next_sibling.find_next_sibling()
            count += 1
