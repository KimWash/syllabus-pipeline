# From a qpdf --qdf decompressed PDF, collect per page: table line segments (top-based coords).
import sys, re, json
H = 841.89
seg = re.compile(rb'([\d.]+) ([\d.]+) m\n([\d.]+) ([\d.]+) l\n')
out = open(sys.argv[2], 'w')
res = {}; page = None; inside = False; buf = []
with open(sys.argv[1], 'rb') as f:
    for line in f:
        if line.startswith(b'%% Contents for page'):
            page = int(line.split()[-1]); continue
        if page is not None:
            if not inside and line == b'stream\n':
                inside = True; buf = []; continue
            if inside:
                if line.startswith(b'endstream'):
                    hs, vs = res.setdefault(page, ([], []))
                    for x0, y0, x1, y1 in seg.findall(b''.join(buf)):
                        x0, y0, x1, y1 = float(x0), H - float(y0), float(x1), H - float(y1)
                        if abs(y0 - y1) < 0.5 and abs(x1 - x0) > 1:
                            hs.append([round(min(x0, x1), 2), round(max(x0, x1), 2), round(y0, 2)])
                        elif abs(x0 - x1) < 0.5 and abs(y1 - y0) > 1:
                            vs.append([round(x0, 2), round(min(y0, y1), 2), round(max(y0, y1), 2)])
                    inside = False; page = None
                else:
                    buf.append(line)
for p in sorted(res):
    hs, vs = res[p]
    out.write(json.dumps({"p": p, "h": sorted(set(map(tuple, hs)), key=lambda s: (s[2], s[0])), "v": sorted(set(map(tuple, vs)))}) + "\n")
print(len(res), file=sys.stderr)
