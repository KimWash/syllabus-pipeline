# Validate the refined syllabi, then load them into a backend by POSTing JSON chunks as multipart/form-data.
# usage: upload.py refined.json [--dry]
#   env: UPLOAD_URL (import endpoint), UPLOAD_TOKEN, UPLOAD_AUTH_HEADER (default Authorization),
#        UPLOAD_FIELD (multipart field, default file), MAX_MB (chunk size, default 4)
import sys, os, json, uuid, urllib.request, urllib.error

path = sys.argv[1]; dry = "--dry" in sys.argv
KEYS = ["년도", "학기", "출력일시", "과목명", "과목코드", "이수구분", "성적평가방법", "부복수전공절대평가여부",
        "집중이수제구분", "전화번호", "요일교시강의실", "면담가능시간", "원어강의구분", "학과", "학년", "소속", "교수",
        "학점", "강의", "실습", "교과목개요및목적", "수업목표", "수업진행방법", "수업방식비율", "기자재활용비율",
        "학습평가방법", "성적평가비율", "유의사항", "교재", "주별수업계획", "과제", "장애학생학습지원",
        "핵심역량가중치", "전공능력가중치", "_sections", "_pages"]

def validate(items):
    errs = []
    codes = set()
    for i, r in enumerate(items):
        if list(r) != KEYS:
            errs.append(f"{i}: keys differ")
        if not (isinstance(r["년도"], int) and r["학기"] and r["과목코드"]):
            errs.append(f"{i}: missing 년도/학기/과목코드")
        if r["과목코드"] in codes:
            errs.append(f"{i}: duplicate 과목코드 {r['과목코드']}")
        codes.add(r["과목코드"])
        for k in ("수업방식비율", "기자재활용비율", "성적평가비율", "핵심역량가중치"):
            if r[k] is not None and not all(v is None or isinstance(v, int) for v in r[k].values()):
                errs.append(f"{i}: {k} has non-int values")
        if not all(isinstance(w["주차"], int) and isinstance(w["내용"], str) for w in r["주별수업계획"]):
            errs.append(f"{i}: bad 주별수업계획")
        def no_blocks(o):
            if isinstance(o, dict):
                assert set(o) != {"R", "L", "lines"}
                [no_blocks(v) for v in o.values()]
            elif isinstance(o, list):
                [no_blocks(v) for v in o]
        try:
            no_blocks(r)
        except AssertionError:
            errs.append(f"{i}: unrendered text block")
    return errs

def post(raw):
    b = uuid.uuid4().hex
    field = os.environ.get("UPLOAD_FIELD", "file")
    body = (f'--{b}\r\nContent-Disposition: form-data; name="{field}"; filename="syllabus.json"\r\n'
            f'Content-Type: application/json\r\n\r\n').encode() + raw + f'\r\n--{b}--\r\n'.encode()
    h = {"Content-Type": f"multipart/form-data; boundary={b}"}
    if os.environ.get("UPLOAD_TOKEN"):
        h[os.environ.get("UPLOAD_AUTH_HEADER", "Authorization")] = os.environ["UPLOAD_TOKEN"]
    r = urllib.request.Request(os.environ["UPLOAD_URL"], data=body, method="POST", headers=h)
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            return resp.status, resp.read()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300]

items = json.load(open(path, encoding='utf-8'))
errs = validate(items)
print(f"validate: {len(items)} items, {len(errs)} problems")
for e in errs[:20]:
    print("  ", e)
if errs:
    sys.exit(1)
if dry:
    sys.exit(0)
# large multipart bodies can be dropped by the server or a proxy (a 13.5MB file broke the pipe in practice),
# and items are imported independently, so send chunks under MAX_MB each
MAX = float(os.environ.get("MAX_MB", "4")) * 1e6
chunks, cur, size = [], [], 2
for r in items:
    n = len(json.dumps(r, ensure_ascii=False).encode()) + 1
    if cur and size + n > MAX:
        chunks.append(cur); cur, size = [], 2
    cur.append(r); size += n
chunks.append(cur)
for i, ch in enumerate(chunks):
    st, d = post(json.dumps(ch, ensure_ascii=False).encode())
    print(f"upload chunk {i+1}/{len(chunks)} ({len(ch)} items): HTTP {st} {d[:120]!r}")
    if not 200 <= st < 300:
        sys.exit(1)
