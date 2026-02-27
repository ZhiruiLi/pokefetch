from main import fetch_page, BASE_URL
import re

soup = fetch_page(f"{BASE_URL}/wiki/凯西")
links = soup.find_all("a")

type_links = []
for a in links:
    title = (a.get("title") or "").strip()
    href = (a.get("href") or "").strip()
    text = a.get_text(strip=True)
    if "属性" in title or "屬性" in title or "（属性）" in href or "（屬性）" in href:
        type_links.append((title, href, text))

print("type-like links:", len(type_links))
for item in type_links[:40]:
    print(item)
