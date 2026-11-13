#!/usr/bin/env python3
"""Syllabus pipeline: PDF -> extract -> parse -> refine (LLM) -> validate -> [upload + verify].

  pipeline.py run  <pdf> <work_dir> [-c configs/router.toml] [--from STAGE] [--to STAGE] [--upload] [--force]
  pipeline.py llm-test [-c configs/router.toml]      # send a 4-item probe to every configured LLM role

Stages: extract (cached in work_dir; --force redoes it), parse, refine, validate, upload.
Upload needs --upload and [upload] endpoint in the config (token from env, see configs/router.toml). Line-wrap votes are cached in work_dir/cache.json.
"""
import argparse, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import llm

STAGES = ["extract", "parse", "refine", "validate", "upload"]
PY = [sys.executable, "-I"]

def sh(args, **kw):
    print("  $", " ".join(map(str, args)), file=sys.stderr)
    subprocess.run(args, check=True, **kw)

def fresh(path, force):
    return not force and os.path.exists(path) and os.path.getsize(path) > 0

def extract(pdf, force):
    if not fresh("corpus.txt", force):
        sh(["pdftotext", "-layout", pdf, "corpus.txt"])
    if not fresh("pages.jsonl", force):
        print("  $ pdftotext -bbox | dump_pages.py", file=sys.stderr)
        src = subprocess.Popen(["pdftotext", "-bbox", pdf, "-"], stdout=subprocess.PIPE)
        subprocess.run(PY + [f"{HERE}/dump_pages.py", "pages.jsonl"], stdin=src.stdout, check=True)
        if src.wait():
            sys.exit("pdftotext -bbox failed")
    if not fresh("segs.jsonl", force):
        try:
            sh(["qpdf", "--qdf", "--object-streams=disable", pdf, "qdf.pdf"])
            sh(PY + [f"{HERE}/segments.py", "qdf.pdf", "segs.jsonl"])
        finally:
            if os.path.exists("qdf.pdf"):
                os.remove("qdf.pdf")

def run(a):
    pdf = os.path.abspath(a.pdf)
    cfg_path = os.path.abspath(a.config)
    cfg = llm.load_config(cfg_path)
    os.makedirs(a.work, exist_ok=True)
    os.chdir(a.work)
    up = cfg.get("upload", {})
    token_env = up.get("token_env", "UPLOAD_TOKEN")
    env = {**os.environ, "UPLOAD_URL": up.get("endpoint", ""), "UPLOAD_TOKEN": os.environ.get(token_env, ""),
           "UPLOAD_AUTH_HEADER": up.get("auth_header", "Authorization"), "UPLOAD_FIELD": up.get("field", "file"),
           "MAX_MB": str(up.get("max_mb", 4))}
    todo = STAGES[STAGES.index(a.from_):STAGES.index(a.to) + 1]
    for st in todo:
        print(f"\n== {st}", file=sys.stderr); t0 = time.time()
        if st == "extract":
            extract(pdf, a.force)
        elif st == "parse":
            sh(PY + [f"{HERE}/parse_full.py", "pages.jsonl", "segs.jsonl", "parsed.json"])
        elif st == "refine":
            sh(PY + [f"{HERE}/refine.py", "parsed.json", "corpus.txt", "cache.json", "refined.json", cfg_path])
        elif st == "validate":
            sh(PY + [f"{HERE}/upload.py", "refined.json", "--dry"])
        elif st == "upload":
            if not a.upload:
                print("  skipped (pass --upload)", file=sys.stderr); continue
            if not env["UPLOAD_URL"]:
                sys.exit("set [upload] endpoint in the config")
            sh(PY + [f"{HERE}/upload.py", "refined.json"], env=env)
        print(f"  ({time.time() - t0:.0f}s)", file=sys.stderr)
    print(f"\nresult: {os.path.abspath('refined.json')}", file=sys.stderr)

PROBE = {"강의를 통해 학습하게 됩|니다.": "J", "물리적 공|간의 구조를": "J",
         "학생들은 다양한|문화를 이해하고": "S", "machine|learning basics": "S"}

def llm_test(a):
    from wrapvote import ask
    cfg = llm.load_config(a.config).get("refine", {})
    ok = True
    for role in ("voter", "tiebreak"):
        try:
            p = llm.make(cfg.get(role))
        except (llm.LLMError, ValueError, TypeError) as e:
            print(f"{role}: config error: {e}"); ok = False; continue
        if not p:
            print(f"{role}: (not configured)"); continue
        t0 = time.time()
        got = ask(p, list(PROBE), attempts=1)
        right = sum(got.get(k) == v for k, v in PROBE.items())
        print(f"{role}: {p.label}  {right}/{len(PROBE)} correct, {len(got)} answered, {time.time() - t0:.1f}s")
        ok &= len(got) == len(PROBE)
    sys.exit(0 if ok else 1)

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("run")
r.add_argument("pdf"); r.add_argument("work")
r.add_argument("-c", "--config", default=f"{HERE}/configs/router.toml")
r.add_argument("--from", dest="from_", choices=STAGES, default=STAGES[0])
r.add_argument("--to", choices=STAGES, default=STAGES[-1])
r.add_argument("--upload", action="store_true")
r.add_argument("--force", action="store_true", help="redo extraction even if cached")
t = sub.add_parser("llm-test")
t.add_argument("-c", "--config", default=f"{HERE}/configs/router.toml")
a = ap.parse_args()
run(a) if a.cmd == "run" else llm_test(a)
