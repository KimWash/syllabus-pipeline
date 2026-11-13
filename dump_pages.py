# Stream `pdftotext -bbox` output and dump compact per-page word lists (JSONL).
import sys, re, json, html
pat = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')
out = open(sys.argv[1], 'w', encoding='utf-8')
page = None; n = 0
for line in sys.stdin:
    if '<page ' in line:
        page = []
    elif '</page>' in line:
        n += 1
        out.write(json.dumps({"p": n, "w": page}, ensure_ascii=False) + "\n")
    else:
        m = pat.search(line)
        if m:
            x0, y0, x1, y1, t = m.groups()
            page.append([round(float(x0),1), round(float(y0),1), round(float(x1),1), html.unescape(t)])
print(n, file=sys.stderr)
