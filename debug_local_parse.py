from main import fetch_page, BASE_URL

soup = fetch_page(f"{BASE_URL}/wiki/妙蛙种子")
tables = soup.find_all("table", class_="roundy")

for i, t in enumerate(tables):
    txt = t.get_text()
    if "进攻招式属性" in txt and "一般" in txt:
        print("effect idx", i, "rows", len(t.find_all("tr")))
        rows = t.find_all("tr")
        for ri, r in enumerate(rows):
            cells = r.find_all(["th", "td"])
            vals = [c.get_text(strip=True) for c in cells]
            print("row", ri, "len", len(vals))
            print(vals)
        print("---")
