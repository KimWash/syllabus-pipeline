# Parse every syllabus in the PDF into the full JSON schema (header, prose sections, tables).
# Text fields are kept as "blocks" (lines + geometry) so refine.py can rejoin auto-wrapped lines.
# usage: parse_full.py pages.jsonl segs.jsonl out.json
import sys, json, re, collections
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid import cell_of

BODY_R = 554.0          # right edge of free-text lines in the full-width body cell (measured)
CELL_PAD = BODY_R - 552.76  # text may overrun a cell's right border by this much

def lines_of(words):
    rows = collections.defaultdict(list)
    for w in words:
        rows[round(w[1] * 2) / 2].append(w)
    merged = []
    for k in sorted(rows):
        if merged and k - merged[-1][0] < 1.0:
            merged[-1][1].extend(rows[k])
        else:
            merged.append([k, list(rows[k])])
    out = []
    for y, ws in merged:
        ws.sort(key=lambda w: w[0])
        out.append({"y": y, "x0": ws[0][0], "x1": max(w[2] for w in ws),
                    "t": ' '.join(w[3] for w in ws),
                    "fw": (ws[0][2] - ws[0][0]) / max(1, len(ws[0][3]))})
    return out

def block(lines, R):
    lines = [l for l in lines if l["t"].strip()]
    if not lines:
        return None
    return {"R": R, "L": min(l["x0"] for l in lines),
            "lines": [{"t": l["t"], "x0": l["x0"], "x1": l["x1"], "fw": l["fw"]} for l in lines]}

def is_title(words):
    return ''.join(w[3] for w in words if 20 < w[1] < 35) == '강의계획서'

class Page:
    def __init__(self, no, words, seg):
        self.no, self.words = no, words
        H, V = seg["h"], seg["v"]
        self.cells = collections.defaultdict(list)
        for w in words:
            self.cells[cell_of(w, H, V)].append(w)
        self.info = {}
        for k, ws in self.cells.items():
            ls = lines_of(ws)
            self.info[k] = {"key": k, "top": k[0], "bot": k[1], "left": k[2], "right": k[3],
                            "lines": ls, "text": ' '.join(l["t"] for l in ls)}

    def find(self, pred):
        return [c for c in self.info.values() if c["left"] is not None and c["top"] is not None and pred(c)]

    def right_of(self, c):
        """Cell directly right of c (shares c's right border as its left border, overlapping rows)."""
        if c["right"] is None:
            return None
        cand = [d for d in self.info.values() if d["left"] == c["right"] and d["top"] is not None and d["bot"] is not None
                and d["top"] < c["bot"] - 0.5 and d["bot"] > c["top"] + 0.5]
        return min(cand, key=lambda d: abs(d["top"] - c["top"])) if cand else None

    def below(self, c):
        if c["bot"] is None:
            return None
        cand = [d for d in self.info.values() if d["left"] == c["left"] and d["right"] == c["right"]
                and d["top"] is not None and abs(d["top"] - c["bot"]) < 0.6]
        return cand[0] if cand else None

def cell_block(c):
    return block(c["lines"], (c["right"] or 552.76) + CELL_PAD) if c else None

def plain(c):
    """Single-value cell text (wrapped fragments joined; Latin-Latin boundaries get a space)."""
    if not c or not c["lines"]:
        return None
    s = ''
    for i, l in enumerate(c["lines"]):
        s += l["t"]
        if i < len(c["lines"]) - 1:
            n = c["lines"][i + 1]["t"]
            if re.match(r'[A-Za-z0-9.,&]', l["t"][-1]) and re.match(r'[A-Za-z0-9(&]', n[0]):
                s += ' '
    return s.strip() or None

def split_slash(c, nparts):
    """Split a 'A / B' cell on its standalone '/' words (positional, so names containing '/' survive)."""
    if not c:
        return [None] * nparts
    ws = sorted(c["lines"] and [w for w in PAGE_WORDS[c["key"]]], key=lambda w: w[0])
    slashes = sorted([w for w in ws if w[3] == '/'], key=lambda w: w[0])[:nparts - 1]
    cuts = [s[0] for s in slashes]
    parts = []
    bounds = [-1e9] + cuts + [1e9]
    for i in range(len(bounds) - 1):
        sub = [w for w in ws if bounds[i] < w[0] < bounds[i + 1] and w not in slashes]
        ls = lines_of(sub)
        parts.append(plain({"lines": ls}) if ls else None)
    return parts + [None] * (nparts - len(parts))

PAGE_WORDS = {}
SEGS = {}

HEADER_LABELS = ["과목명", "과목코드", "학과 / 학년", "이수구분", "성적평가방법", "부복수전공 절대평가여부",
                 "집중이수제구분", "소속 / 교수", "학점/강의/실습", "전화번호", "요일 / 교시 강의실",
                 "면담가능시간", "원어강의구분"]

def parse_header(pg):
    r = {}
    top_words = [w for w in pg.words if w[1] < 79]
    tw = ' '.join(w[3] for w in sorted(top_words, key=lambda w: (round(w[1]), w[0])))
    m = re.search(r'(\d{4}) 년도 (\S+)', tw)
    r["년도"] = int(m.group(1)); r["학기"] = m.group(2)
    d = re.search(r'출력날짜 : (\d{4})\.(\d{2})\.(\d{2})', tw); t = re.search(r'출력시간 : (AM|PM) (\d{1,2}):(\d{2})', tw)
    if d and t:
        h = int(t.group(2)) % 12 + (12 if t.group(1) == 'PM' else 0)
        r["출력일시"] = f"{d.group(1)}-{d.group(2)}-{d.group(3)} {h:02d}:{t.group(3)}"
    else:
        r["출력일시"] = None
    lab = {}
    for c in pg.find(lambda c: c["top"] is not None and c["top"] < 200):
        if c["text"] in HEADER_LABELS:
            lab[c["text"]] = c
    val = {k: pg.right_of(c) for k, c in lab.items()}
    r["과목명"] = plain(val.get("과목명"))
    r["과목코드"] = plain(val.get("과목코드"))
    r["이수구분"] = plain(val.get("이수구분"))
    r["성적평가방법"] = plain(val.get("성적평가방법"))
    r["부복수전공절대평가여부"] = plain(val.get("부복수전공 절대평가여부"))
    r["집중이수제구분"] = plain(val.get("집중이수제구분"))
    r["전화번호"] = plain(val.get("전화번호"))
    r["요일교시강의실"] = plain(val.get("요일 / 교시 강의실"))
    r["면담가능시간"] = cell_block(val.get("면담가능시간"))
    r["원어강의구분"] = plain(val.get("원어강의구분"))
    r["학과"], r["학년"] = split_slash(val.get("학과 / 학년"), 2)
    r["소속"], r["교수"] = split_slash(val.get("소속 / 교수"), 2)
    r["학점"], r["강의"], r["실습"] = split_slash(val.get("학점/강의/실습"), 3)
    return r

PCT = re.compile(r'^(\d+) ?%$')

def ratio_tables(pages, lines):
    """Label row followed by a row of 'N %' cells -> dict.
    Which table it is comes from its position between the section headers (label sets vary)."""
    out = {}
    for pg in pages:
        for c in pg.find(lambda c: True):
            b = pg.below(c)
            if not b or not PCT.match(b["text"]) or c["text"] in ("", None) or PCT.match(c["text"]):
                continue
            out.setdefault((pg.no, c["top"]), {})[c["text"].replace(' ', '')] = int(PCT.match(b["text"]).group(1))
    def pos(tag, word):
        l = next((l for l in lines if is_head(l, tag, word)), None)
        return (l["p"], l["y"]) if l else None
    marks = [("수업방식비율", pos("ⓐ", "수업방식")), ("기자재활용비율", pos("ⓑ", "기자재활용")),
             ("성적평가비율", pos("ⓐ", "성적평가비율")), (None, pos("[5]", "주교재"))]
    res = {"수업방식비율": None, "기자재활용비율": None, "성적평가비율": None}
    for key, d in sorted(out.items()):
        name = None
        for i, (n, m) in enumerate(marks[:-1]):
            nxt = next((mm for _, mm in marks[i + 1:] if mm), (10**9, 0))
            if m and m <= key < nxt:
                name = n
        if name and res[name] is None:
            res[name] = d
    return res

def books(pages):
    main, ref, cur = [], [], None
    for pg in pages:
        nums = sorted(pg.find(lambda c: re.fullmatch(r'\(\d+\)', c["text"] or '')), key=lambda c: c["top"])
        for n in nums:
            k = int(n["text"][1:-1])
            if k == 1:
                cur = main if cur is None else ref
            if cur is None:
                cur = main
            entry = {}
            c = pg.right_of(n)
            while c:
                if c["text"] in ("저자", "출판사", "교재명", "발행년도"):
                    v = pg.right_of(c)
                    entry[c["text"]] = plain(v) if v and v["text"] not in ("저자", "출판사", "교재명", "발행년도") else None
                c = pg.right_of(c)
            if entry.get("교재명") == "없음" and not any(entry.get(k) for k in ("저자", "출판사", "발행년도")):
                continue
            if any(entry.values()):
                cur.append({"교재명": entry.get("교재명"), "저자": entry.get("저자"),
                            "출판사": entry.get("출판사"), "발행년도": entry.get("발행년도")})
    return main, ref

def weeks(pages):
    out, last, last_page, pending = [], None, None, []
    for pg in pages:
        # a row split by a page break continues above the first drawn line of the next page
        first_h = min((h[2] for h in SEGS[pg.no]["h"]), default=None)
        top_is_week = first_h is not None and any(
            c["top"] is not None and abs(c["top"] - first_h) < 0.6 and re.fullmatch(r'제\s*\d+\s*주', c["text"] or '')
            or (c["top"] is not None and abs(c["top"] - first_h) < 0.6 and c["left"] is not None and abs(c["left"] - 127.56) < 0.6
                and c["right"] is not None and abs(c["right"] - 538.58) < 0.6 and not re.search(r'과제명|목표', c["text"]))
            for c in pg.info.values())
        if last is not None and top_is_week and last_page == pg.no - 1:
            orphan = [w for w in pg.words if w[1] + 4.5 < first_h and w[0] >= 127.56 and w[2] <= 540.5]
            if orphan:
                last["_extra"].append({"lines": lines_of(orphan)})
        labs = {c["key"]: c for c in pg.find(lambda c: re.fullmatch(r'제\s*\d+\s*주', c["text"] or ''))}
        contents = pg.find(lambda c: c["left"] is not None and abs(c["left"] - 127.56) < 0.6 and c["right"] is not None
                           and abs(c["right"] - 538.58) < 0.6)
        # labels whose content cell is empty but whose row began on the previous page
        for lab in sorted(labs.values(), key=lambda l: l["top"]):
            if pending and not any(w is not None and w.get("_lab") == lab["key"] for w in out):
                if not any(c["left"] == lab["right"] and c["top"] < lab["bot"] - 0.5 and c["bot"] > lab["top"] + 0.5 for c in contents):
                    last = {"주차": int(re.sub(r'\D', '', lab["text"])), "_cells": pending, "_extra": []}
                    pending = []
                    out.append(last)
            break
        for c in sorted(contents, key=lambda c: c["top"]):
            lab = next((l for l in labs.values() if l["right"] == c["left"] and l["top"] < c["bot"] - 0.5 and l["bot"] > c["top"] + 0.5), None)
            if lab is None:
                # a row split by a page break: its label sits on only one of the two halves
                if last is not None and c["top"] < 80 and not any(l["top"] < c["top"] for l in labs.values()):
                    last["_extra"].append(c)
                elif not any(l["top"] > c["top"] for l in labs.values()) and c["bot"] > 700:
                    pending.append(c)       # bottom half; the label is at the top of the next page
                continue
            last = {"주차": int(re.sub(r'\D', '', lab["text"])), "_cells": pending + [c], "_extra": []}
            pending = []
            out.append(last)
        if last is not None:
            last_page = pg.no
    res = []
    for w in out:
        lines = [l for c in w["_cells"] + w["_extra"] for l in c["lines"]]
        b = block(lines, 538.58 + CELL_PAD)
        if b:
            res.append({"주차": w["주차"], "내용": b})
    return res

ASG_LABELS = ("과제명", "제출일", "목표", "진행방법 및 유의사항", "참고자료")

def assignments(pages):
    asg, cur = [], None
    for pg in pages:
        heads = sorted(pg.find(lambda c: re.fullmatch(r'제\s*\d+\s*과제', c["text"] or '')), key=lambda c: c["top"])
        labs = sorted(pg.find(lambda c: c["text"] in ASG_LABELS), key=lambda c: (c["top"], c["left"]))
        for lab in labs:
            h = next((h for h in heads if h["top"] - 0.5 <= lab["top"] and lab["bot"] <= h["bot"] + 0.5), None)
            if h is not None:
                no = int(re.sub(r'\D', '', h["text"]))
                if cur is None or cur["번호"] != no:
                    cur = {"번호": no, "과제명": None, "제출일": None, "목표": None, "진행방법및유의사항": None, "참고자료": None}
                    asg.append(cur)
            elif cur is None:
                continue
            v = pg.right_of(lab)
            if v and v["text"] in ASG_LABELS:
                v = None
            key = lab["text"].replace(' ', '')
            cur[key] = plain(v) if key in ("제출일",) else cell_block(v)
    return [a for a in asg if any(a[k] for k in ("과제명", "제출일", "목표", "진행방법및유의사항", "참고자료"))]

CORE = ["지식탐구", "의사소통", "문제해결", "창의융합", "협업인성", "도전창조"]

def competencies(pages):
    core = {k: None for k in CORE}; major = []
    for pg in pages:
        for c in pg.find(lambda c: c["text"] in CORE):
            b = pg.below(c)
            if b and re.fullmatch(r'\d+', b["text"]):
                core[c["text"]] = int(b["text"])
        for lab in pg.find(lambda c: c["text"] == "전공능력"):
            inside = [c for c in pg.find(lambda c: c["left"] is not None and c["left"] >= lab["right"] - 0.5
                                         and c["top"] >= lab["top"] - 0.5 and c["bot"] <= lab["bot"] + 0.5)]
            for c in sorted(inside, key=lambda c: (c["top"], c["left"])):
                if re.fullmatch(r'\d+', c["text"]):
                    continue
                b = pg.below(c)
                major.append({"전공능력": plain(c), "가중치": int(b["text"]) if b and re.fullmatch(r'\d+', b["text"]) else None})
    return core, major

SECTION = [("[1]", "교과목개요"), ("[2]", "수업목표"), ("[3]", "수업진행방법"), ("ⓐ", "수업방식"),
           ("ⓑ", "기자재활용"), ("[4]", "학습평가방법"), ("ⓐ", "성적평가비율"), ("[5]", "주교재"),
           ("[주교재]", None), ("[참고서적]", None), ("[기타서적]", None), ("[6]", "주별"), ("[7]", "과제"),
           ("[8]", "장애학생"), ("[9]", "핵심역량")]

def linear(pages):
    out = []
    for pg in pages:
        for l in lines_of(pg.words):
            if re.fullmatch(r'\d+/\d+', l["t"]) and l["x0"] > 200:
                continue
            l["p"] = pg.no
            out.append(l)
    return out

def is_head(l, tag, word):
    t = l["t"].strip()
    return t.startswith(tag) and (word is None or word in t[:20])

def prose(lines, start, ends):
    """Lines strictly between the first header `start` and the next header in `ends`."""
    s = next((i for i, l in enumerate(lines) if is_head(l, *start)), None)
    if s is None:
        return None
    e = next((i for i in range(s + 1, len(lines)) if any(is_head(lines[i], *x) for x in ends)), len(lines))
    body = [l for l in lines[s + 1:e] if not is_head(l, *start)]
    return body

def parse(group, segs):
    pages = []
    for pg in group:
        p = Page(pg["p"], pg["w"], segs[pg["p"]])
        for k, ws in p.cells.items():
            PAGE_WORDS[k] = ws
        pages.append(p)
    r = parse_header(pages[0])
    PAGE_WORDS.clear()
    lines = linear(pages)
    H = {name: (tag, word) for tag, word in SECTION for name in [word or tag]}
    def P(start, ends, R=BODY_R):
        b = prose(lines, H[start], [H[e] for e in ends])
        return block(b, R) if b else None
    r["교과목개요및목적"] = P("교과목개요", ["수업목표"])
    r["수업목표"] = P("수업목표", ["수업진행방법"])
    r["수업진행방법"] = P("수업진행방법", ["수업방식", "학습평가방법"])
    r.update(ratio_tables(pages, lines))
    r["학습평가방법"] = P("학습평가방법", ["성적평가비율", "주교재"])
    # 유의사항: '·' bullets between the grade-ratio table and [5]
    notes = []
    tail = prose(lines, H["성적평가비율"], [H["주교재"]]) or []
    for l in tail:
        if PCT.match(l["t"].split()[0] if l["t"].split() else '') or re.fullmatch(r'[\d %]+', l["t"]):
            continue
        if l["t"].startswith('·'):
            notes.append([dict(l, t=l["t"].lstrip('· ').strip())])
        elif notes:
            notes[-1].append(l)
    r["유의사항"] = [block(n, BODY_R) for n in notes] or None
    main, ref = books(pages)
    r["교재"] = {"주교재": main, "참고서적": ref, "기타서적": P("[기타서적]", ["주별"])}
    r["주별수업계획"] = weeks(pages)
    r["과제"] = assignments(pages)
    r["장애학생학습지원"] = P("장애학생", ["핵심역량"])
    r["핵심역량가중치"], r["전공능력가중치"] = competencies(pages)
    r["_sections"] = [int(t[1]) for t, w in SECTION if re.fullmatch(r'\[\d\]', t)
                      and any(is_head(l, t, w) for l in lines)]
    r["_pages"] = [pages[0].no, pages[-1].no]
    return r

ORDER = ["년도", "학기", "출력일시", "과목명", "과목코드", "이수구분", "성적평가방법", "부복수전공절대평가여부",
         "집중이수제구분", "전화번호", "요일교시강의실", "면담가능시간", "원어강의구분", "학과", "학년", "소속", "교수",
         "학점", "강의", "실습", "교과목개요및목적", "수업목표", "수업진행방법", "수업방식비율", "기자재활용비율",
         "학습평가방법", "성적평가비율", "유의사항", "교재", "주별수업계획", "과제", "장애학생학습지원",
         "핵심역량가중치", "전공능력가중치", "_sections", "_pages"]

def main():
    pages_path, segs_path, dst = sys.argv[1:4]
    segs = SEGS
    for l in open(segs_path):
        o = json.loads(l); segs[o["p"]] = o
    groups = []
    for l in open(pages_path, encoding='utf-8'):
        pg = json.loads(l)
        if is_title(pg["w"]):
            groups.append([pg])
        elif groups:
            groups[-1].append(pg)
    res, fails = [], 0
    for g in groups:
        try:
            r = parse(g, segs)
            res.append({k: r.get(k) for k in ORDER})
        except Exception as e:
            fails += 1
            print("FAIL page", g[0]["p"], repr(e), file=sys.stderr)
    json.dump(res, open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"parsed {len(res)} syllabi, {fails} failures", file=sys.stderr)
    if fails:
        sys.exit(1)

if __name__ == '__main__':
    main()
