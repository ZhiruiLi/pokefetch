import requests
from bs4 import BeautifulSoup
import re

url = 'https://wiki.52poke.com/wiki/%E5%A6%99%E8%9B%99%E7%A7%8D%E5%AD%90'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
response = requests.get(url, headers=headers, timeout=30)
soup = BeautifulSoup(response.content, 'lxml')

# Find base stats table - look for specific pattern
print('=== Looking for base stats tables ===')
tables = soup.find_all('table', class_='roundy')
print(f'Found {len(tables)} tables with roundy class')

for i, table in enumerate(tables):
    text = table.get_text()
    # Look for tables with both HP and 种族值 or base stats
    if ('种族值' in text or '能力值' in text or 'Base stats' in text.lower()) and ('HP' in text or 'ＨＰ' in text or '生命' in text):
        print(f'\n--- Table {i} - Potential stats table ---')
        print(text[:800])
        rows = table.find_all('tr')
        print(f'Rows: {len(rows)}')
        for j, row in enumerate(rows[:10]):
            cells = row.find_all(['th', 'td'])
            cell_texts = [c.get_text(strip=True) for c in cells]
            print(f'  Row {j}: {cell_texts}')
        break
