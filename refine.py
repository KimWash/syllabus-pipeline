# Turn parsed text blocks into clean strings.
# Real newlines are kept; auto-wrapped lines are rejoined. Whether a wrap swallowed a space is decided by
# geometry when possible, else by a corpus heuristic + LLM votes (voter, optional tiebreaker), cached on disk.
# usage: refine.py parsed.json corpus.txt cache.json out.json [config.toml]   (LLM_OFF=1 to skip LLM calls)
import sys, os, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm
from wrapvote import vote

parsed_path, corpus_path, cache_path, dst = sys.argv[1:5]
cfg = llm.load_config(sys.argv[5]).get("refine", {}) if len(sys.argv) > 5 else {}
voter, tiebreak = llm.make(cfg.get("voter")), llm.make(cfg.get("tiebreak"))
BATCH, ROUNDS = cfg.get("batch", 50), cfg.get("rounds", 3)
SPW = 2.5
LAT = re.compile(r'[A-Za-z0-9]')
HANGUL_OR_CJK = re.compile(r'[가-힣　-鿿]')

# ---------- corpus heuristic ----------
tok = collections.Counter(); big = collections.Counter()
for line in open(corpus_path, encoding='utf-8'):
    ts = line.split()[1:-1]          # drop edge tokens: they may be wrap fragments
    tok.update(ts); big.update(zip(ts, ts[1:]))
pref = collections.Counter(); suf = collections.Counter()
for t, c in tok.items():
    for k in range(1, min(len(t), 8)):
        pref[t[:k]] += c; suf[t[-k:]] += c

def heuristic(a, b):
    A, B = a.split()[-1], b.split()[0]
    j, s = tok[A + B], big[(A, B)]
    if LAT.match(A[-1]) and LAT.match(B[0]):
        return 'J' if j > s else 'S'
    if j != s:
        return 'J' if j > s else 'S'
    a_st = tok[A] / (tok[A] + pref[A] + 1); b_st = tok[B] / (tok[B] + suf[B] + 1)
    r = 'S' if a_st * b_st > 0.2 else 'J'
    if len(A) >= 3 and (len(B) >= 2 or A[-1] in '던며') and A[-1] in '의을를은는던며고과와' and re.match(r'[가-힣]', B):
        r = 'S'
    return r

# ---------- walk blocks ----------
def walk(o, fn):
    if isinstance(o, dict):
        if set(o) == {"R", "L", "lines"}:
            return fn(o)
        return {k: walk(v, fn) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, fn) for v in o]
    return o

def junctions(b):
    """Yield (i, kind) for each line boundary: 'NL' real newline, 'S' certain space, or 'Q' ambiguous wrap."""
    ls = b["lines"]
    for i in range(len(ls) - 1):
        l, n = ls[i], ls[i + 1]
        fw = 8.75 if HANGUL_OR_CJK.match(n["t"][0]) else n["fw"]
        if n["x0"] > b["L"] + 1.1 or l["x1"] + fw + SPW <= b["R"]:
            yield i, 'NL'
        elif l["x1"] + fw <= b["R"]:
            yield i, 'S'
        else:
            yield i, 'Q'

def key(l, n):
    return f'{l["t"][-25:]}|{n["t"][:25]}'

cache = json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}
parsed = json.load(open(parsed_path, encoding='utf-8'))

need = {}
def collect(b):
    for i, kind in junctions(b):
        if kind in ('Q', 'S'):          # geometric 'S' is a strong prior, still double-checked by the vote
            k = key(b["lines"][i], b["lines"][i + 1])
            if k not in cache:
                need[k] = 'S' if kind == 'S' else heuristic(b["lines"][i]["t"], b["lines"][i + 1]["t"])
    return b
walk(parsed, collect)
print(f"ambiguous junctions needing a decision: {len(need)} (cache has {len(cache)})", file=sys.stderr)

# ---------- LLM voting ----------
# config [refine.voter] votes on every new junction; [refine.tiebreak] (optional) is asked only where the voter
# disagrees with the corpus heuristic, and its answer wins. No voter (or LLM_OFF=1) -> heuristic/geometry only.
if need and voter and not os.environ.get("LLM_OFF"):
    keys = sorted(need)
    v = vote(voter, keys, BATCH, ROUNDS)
    split = [k for k in keys if k in v and v[k] != need[k]]
    t = vote(tiebreak, split, BATCH, ROUNDS) if tiebreak and split else {}
    for k in keys:
        if k not in v:
            continue                      # undecided: left out of the cache so a re-run retries it
        final = v[k] if (v[k] == need[k] or not tiebreak) else t.get(k)
        if final is None:
            continue
        cache[k] = {"heur": need[k], "voter": v[k], "voter_model": voter.label,
                    "tiebreak": t.get(k), "tiebreak_model": tiebreak.label if k in t else None, "final": final}
    json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)

# ---------- render ----------
stats = collections.Counter()
def render(b):
    ls = b["lines"]; out = ls[0]["t"]
    for i, kind in junctions(b):
        n = ls[i + 1]
        if kind == 'NL':
            out += '\n'
        else:
            c = cache.get(key(ls[i], n))
            d = c["final"] if c else ('S' if kind == 'S' else need.get(key(ls[i], n)) or heuristic(ls[i]["t"], n["t"]))
            stats['llm' if c else 'heuristic-only'] += 1
            out += ' ' if d == 'S' else ''
        out += n["t"]
    out = re.sub(r'[ \t]+\n', '\n', out)
    return re.sub(r'\n{3,}', '\n\n', out).strip() or None

final = walk(parsed, render)
json.dump(final, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"refined {len(final)} syllabi; ambiguous wraps resolved by: {dict(stats)}", file=sys.stderr)
