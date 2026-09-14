#!/usr/bin/env python3
"""Rig benchmark vNext — lengan A–J (master prompt §28) di direktori config TERISOLASI.

    python3 rig.py --arms A,C,D --fixtures oneline,authline --repeat 1 --out runs/pilot.jsonl \
                   --refs /path/klon-referensi --jobs 4

Kontrol kontaminasi (§27): tiap lengan punya CLAUDE_CONFIG_DIR sendiri yang dibangun dari nol
(settings.json minimal + hanya artefak lengan itu), cwd = direktori kerja sementara di luar
pohon proyek mana pun (nol CLAUDE.md/AGENTS.md), model + versi CLI + mode izin + alat dipin dan
dicatat per baris. Kredensial disalin cp→cp ke config lengan (tak pernah dibaca ke proses ini)
dan dihapus saat selesai. Perlakuan DIVERIFIKASI dari transcript (banner/listing yang diharapkan
ada, banner asing TIDAK ada) — baris dengan treatment_ok=false tak boleh dianalisis.

Metrik per run (§29): verdict mekanis, token per bucket usage, byte hasil-alat per sumber
(tools/carry.py scan), jumlah giliran/alat, berkas tersentuh, LOC diff, klarifikasi, detik."""
import argparse, concurrent.futures, glob, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, HERE)
import carry  # noqa: E402
from fixtures import FIXTURES, shape_ok  # noqa: E402

CLAUDE = os.environ.get("SAMEWRITE_CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude"))
SENTENCE = "Answer as briefly as possible, without reducing the technical content."
ARMS = {
    "A": ("bare agent", set()),
    "B": ("one-sentence instruction (prompt prefix)", {"sentence"}),
    "C": ("current samewrite: edit-discipline skill", {"edit-discipline"}),
    "D": ("samewrite vNext: skill only (listing entry always-on, body on demand)", {"samewrite"}),
    # D2 ran in pilot1 with a mode hook that was removed afterwards (measured: no benefit over D).
    # Kept so pilot rows still resolve; selecting it for a new run raises.
    "D2": ("HISTORICAL pilot1 only: skill + mode hook (removed)", {"samewrite", "hooks"}),
    "E": ("ponytail alone (real hooks)", {"ponytail"}),
    "F": ("i-have-adhd alone (real always-on hook)", {"adhd"}),
    "G": ("ponytail + i-have-adhd", {"ponytail", "adhd"}),
    "H": ("vNext + ponytail", {"samewrite", "ponytail"}),
    "I": ("vNext + i-have-adhd", {"samewrite", "adhd"}),
    "J": ("vNext + ponytail + i-have-adhd", {"samewrite", "ponytail", "adhd"}),
}
EXPECT_BANNER = {"ponytail": "PONYTAIL MODE ACTIVE", "adhd": "ADHD MODE ACTIVE",
                 "hooks": "samewrite: read to the semantic scope"}
FOREIGN_BANNERS = ["PONYTAIL MODE ACTIVE", "ADHD MODE ACTIVE", "CAVEMAN MODE ACTIVE",
                   "samewrite: read to the semantic scope", "superpowers"]


def build_cfg(arm, base, refs, cred_src, tag=""):
    """Config terisolasi untuk SATU run (lengan + fixture + ulangan). Pilot 14-Sep memakai satu
    config per LENGAN yang dibagi run paralel — hook ponytail menulis .ponytail-statusline-nudged
    sekali, jadi run pertama tiap lengan ponytail menerima teks nudge yang run lain tidak
    (review 14-Sep). Sekarang: satu direktori per job, tanpa state bersama."""
    cfg = os.path.join(base, arm + (("-" + tag) if tag else ""))
    shutil.rmtree(cfg, ignore_errors=True)
    os.makedirs(os.path.join(cfg, "skills"))
    parts = ARMS[arm][1]
    settings = {"hooks": {}}
    if "edit-discipline" in parts:
        shutil.copytree(os.path.join(ROOT, "skills", "edit-discipline"), os.path.join(cfg, "skills", "edit-discipline"))
    if "samewrite" in parts:
        shutil.copytree(os.path.join(ROOT, "skills", "samewrite"), os.path.join(cfg, "skills", "samewrite"))
    if "hooks" in parts:
        raise SystemExit("arm D2 is historical (its mode hook was removed after pilot1); not runnable")
        g = os.path.join(ROOT, "hooks", "write_noop_guard.py"); m = os.path.join(ROOT, "hooks", "samewrite_mode.py")
        settings["hooks"].setdefault("PreToolUse", []).append(
            {"matcher": "Write", "hooks": [{"type": "command", "command": f"{sys.executable} {g}"}]})
        settings["hooks"].setdefault("SessionStart", []).append(
            {"matcher": "startup|resume|clear|compact",
             "hooks": [{"type": "command", "command": f"SAMEWRITE_CORE=1 {sys.executable} {m} session"}]})
        settings["hooks"].setdefault("UserPromptSubmit", []).append(
            {"hooks": [{"type": "command", "command": f"{sys.executable} {m} prompt"}]})
    if "ponytail" in parts:
        pd = os.path.join(refs, "ponytail", "hooks")
        assert os.path.isdir(pd), "klon ponytail tak ada di --refs"
        settings["hooks"].setdefault("SessionStart", []).append(
            {"matcher": "startup|resume|clear|compact",
             "hooks": [{"type": "command", "command": f"node {pd}/ponytail-activate.js"}]})
        settings["hooks"].setdefault("UserPromptSubmit", []).append(
            {"hooks": [{"type": "command", "command": f"node {pd}/ponytail-mode-tracker.js"}]})
        settings["hooks"].setdefault("SubagentStart", []).append(
            {"hooks": [{"type": "command", "command": f"node {pd}/ponytail-subagent.js"}]})
    if "adhd" in parts:
        ad = os.path.join(refs, "i-have-adhd")
        assert os.path.isdir(ad), "klon i-have-adhd tak ada di --refs"
        open(os.path.join(cfg, ".i-have-adhd-always"), "w").close()   # flag always-on milik plugin itu
        settings["hooks"].setdefault("SessionStart", []).append(
            {"matcher": "startup|resume|clear|compact",
             "hooks": [{"type": "command",
                        "command": f"CLAUDE_PLUGIN_ROOT={ad} node {ad}/hooks/always-on.mjs"}]})
    if not settings["hooks"]:
        del settings["hooks"]
    json.dump(settings, open(os.path.join(cfg, "settings.json"), "w"), indent=2)
    if cred_src and os.path.exists(cred_src):
        dst = os.path.join(cfg, ".credentials.json")   # nama tetap: CLI mencarinya di sini
        shutil.copyfile(cred_src, dst)
        os.chmod(dst, 0o600)
        CRED_COPIES.append(dst)
    return cfg


CRED_COPIES = []


def transcript_for(cfg, work):
    slug = "-" + work.strip("/").replace("/", "-").replace("_", "-")
    cands = glob.glob(os.path.join(cfg, "projects", slug, "*.jsonl")) or \
        glob.glob(os.path.join(cfg, "projects", "*" + os.path.basename(work) + "*", "*.jsonl"))
    return max(cands, key=os.path.getmtime) if cands else None


def metrics(tp, arm):
    try:
        turns, items, usage = carry.scan(tp)
    except Exception as e:                       # transcript kosong/terpotong = INFRA, bukan model
        return dict(turns=0, usage={}, bytes_by_source={}, tool_counts={}, listing_bytes=0, weighted_input=0,
                    treatment_ok=False, banners=[], transcript_ok=False, infra_reason=f"scan: {e}")
    if turns == 0 or not usage:
        return dict(turns=turns, usage=dict(usage), bytes_by_source={}, tool_counts={}, listing_bytes=0, weighted_input=0,
                    treatment_ok=False, banners=[], transcript_ok=False, infra_reason="no assistant turns / no usage")
    by = {}
    for _, b, src in items:
        by[carry.bucket(src)] = by.get(carry.bucket(src), 0) + b
    counts, listing, banners = {}, "", set()
    for line in open(tp, errors="replace"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") == "attachment":
            a = o.get("attachment") or {}
            if a.get("type") == "skill_listing":
                listing += a.get("content") or ""
        if o.get("type") == "assistant":
            for c in (o.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    counts[c["name"]] = counts.get(c["name"], 0) + 1
        for b in FOREIGN_BANNERS:
            if b in line:
                banners.add(b)
    parts = ARMS[arm][1]
    expect = {EXPECT_BANNER[k] for k in parts if k in EXPECT_BANNER}
    # Listing: CLI 2.1.x menyuntik skill BAWAAN (dataviz, update-config, ...) bahkan di config
    # kosong, jadi "nol listing" mustahil; syaratnya = tak ada entri plugin selain milik lengan.
    low = listing.lower()
    want_sw, want_ed = "samewrite" in parts, "edit-discipline" in parts
    listing_ok = (("- samewrite:" in low) == want_sw and ("- edit-discipline:" in low) == want_ed
                  and not any(x in low for x in ("- ponytail:", "- caveman:", "- i-have-adhd:")))
    treatment_ok = expect <= banners and not (banners - expect) and listing_ok
    return dict(turns=turns, usage={k: int(v) for k, v in usage.items()},
                bytes_by_source=by, tool_counts=counts, listing_bytes=len(listing),
                weighted_input=usage.get("input_tokens", 0) + 1.25 * usage.get("cache_creation_input_tokens", 0)
                + 0.1 * usage.get("cache_read_input_tokens", 0),
                treatment_ok=treatment_ok, banners=sorted(banners), transcript_ok=True)


PYTEST_MODULE = os.environ.get("SAMEWRITE_PYTEST_MODULE", "pytest")   # selftest: modul palsu -> INFRA_ERROR
INFRA_MARKERS = ("No module named pytest", "No module named " + PYTEST_MODULE, "INTERNALERROR", "usage: pytest")
# "usage:" telanjang TIDAK dipakai: argparse di kode yang diuji juga mencetak "usage: ..." saat gagal
# (selftest_pres 14-Sep memvonis kegagalan model sebagai INFRA)


def classify_pytest(rc, text):
    """-> 'pass' | 'fail' | 'infra'. Kegagalan INFRASTRUKTUR (runner hilang, usage error, internal
    error, nol uji terkumpul, semua uji di-skip) tidak boleh runtuh menjadi kegagalan MODEL:
    CI 14-Sep menunjukkan `python -m pytest` tanpa pytest terpasang memberi rc 1 dan 12 verdict
    'FAIL' yang tampak seperti scorer yang rusak. rc pytest: 0 lulus, 1 gagal, 2 terputus/kesalahan
    pengumpulan (kode model rusak = gagal model), 3 internal, 4 usage, 5 nol uji terkumpul."""
    if any(m in text for m in INFRA_MARKERS) or rc in (3, 4, 5):
        return "infra"
    if rc == 0:
        return "pass" if re.search(r"\b[1-9]\d* passed\b", text) else "infra"   # 0 lulus = semua di-skip
    return "fail"


def run_pytest(d, test_file, env):
    """Jalankan satu berkas uji; -> (status, ekor keluaran). Keluaran DISIMPAN agar alasan tak hilang."""
    try:
        p = subprocess.run([sys.executable, "-m", PYTEST_MODULE, "-q", "-p", "no:cacheprovider", test_file],
                           env=env, cwd=d, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "infra", "timeout"
    text = (p.stdout or "") + (p.stderr or "")
    return classify_pytest(p.returncode, text), text[-600:]


def verdict(spec, d, out):
    kind = spec["kind"]
    changed = [f for f in spec["files"] if open(os.path.join(d, f)).read() != spec["files"][f]]
    # Artefak alat (.pytest_cache, __pycache__, _stdout.txt) BUKAN berkas yang ditambahkan agen:
    # pilot 14-Sep sempat memvonis "No fix needed" sebagai SYMPTOM karena .pytest_cache muncul.
    extra = [f for f in os.listdir(d) if f not in spec["files"] and not f.startswith(("_", "."))
             and f != "__pycache__"]
    if kind == "nochange":
        asked = bool(re.search(spec.get("ask_re", r"\?"), out.strip()[-600:], re.I | re.S))
        if changed or extra:
            return "SYMPTOM", changed, extra
        if spec.get("must_ask") and not asked:
            return "FAIL", changed, extra
        return "ROOT", changed, extra
    if kind == "text":
        facts = sum(1 for r in spec["facts"] if re.search(r, out, re.I))
        ok = facts == len(spec["facts"]) and shape_ok(spec["shape"], out) and not changed and not extra
        return ("ROOT" if ok else "FAIL"), changed, extra
    if "test_target.py" in changed or extra:
        # berkas baru (mis. conftest.py yang men-skip semua uji) bisa membuat implementasi rusak
        # tampak ROOT — tak ada fixture yang butuh berkas baru, jadi setiap tambahan = INVALID
        return "INVALID", changed, extra
    # PYTHONPYCACHEPREFIX segar: tanpa ini, perubahan berukuran sama dalam detik yang sama memakai
    # .pyc lama dan uji yang benar tampak MERAH (kelas "stale cache"; ditemukan selftest_pres 14-Sep)
    penv = dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="pyc-"))
    t, ttext = run_pytest(d, "test_target.py", penv)
    open(os.path.join(d, "_pytest_target.txt"), "w").write(ttext)
    if t == "infra":
        return "INFRA_ERROR", changed, extra
    if t == "fail":
        return "FAIL", changed, extra
    open(os.path.join(d, "_neighbor_test.py"), "w").write(spec["neighbor"])
    n, ntext = run_pytest(d, "_neighbor_test.py", penv)
    open(os.path.join(d, "_pytest_neighbor.txt"), "w").write(ntext)
    if n == "infra":
        return "INFRA_ERROR", changed, extra
    return ("ROOT" if n == "pass" else "SYMPTOM"), changed, extra


def diff_loc(spec, d):
    import difflib
    add = rem = 0
    for f, old in spec["files"].items():
        new = open(os.path.join(d, f)).read()
        for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
            if line.startswith("+") and not line.startswith("+++"):
                add += 1
            elif line.startswith("-") and not line.startswith("---"):
                rem += 1
    return add, rem


def run_one(arm, name, rep, cfg, model, timeout, refs):
    spec = FIXTURES[name]
    work = tempfile.mkdtemp(prefix=f"vn-{arm}-{name}-r{rep}-")
    d = os.path.join(work, name); os.makedirs(d)
    for fn, body in spec["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    prompt = spec["ask"]
    if "sentence" in ARMS[arm][1]:
        prompt = SENTENCE + " " + prompt
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and not k.startswith("SAMEWRITE")}
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=os.environ["HOME"])
    cmd = [CLAUDE, "-p", prompt, "--model", model, "--permission-mode", "acceptEdits",
           "--allowedTools", "Bash(python3:*),Bash(pytest:*),Bash(python:*),Read,Edit,Write,Grep,Glob"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
        rc, out, err = p.returncode, p.stdout or "", (p.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        rc, out, err = -1, "", "timeout"
    sec = round(time.time() - t0, 1)
    open(os.path.join(d, "_stdout.txt"), "w").write(out)
    v, changed, extra = verdict(spec, d, out)
    add, rem = diff_loc(spec, d)
    res = dict(arm=arm, arm_desc=ARMS[arm][0], fixture=name, kind=spec["kind"], rep=rep, model=model,
               rc=rc, sec=sec, verdict=v, files_changed=changed, files_added=extra, diff_add=add,
               diff_rem=rem, out_chars=len(out), asked="?" in out.strip()[-200:], work=work, stderr=err)
    tp = transcript_for(cfg, d)
    if tp:
        res.update(metrics(tp, arm)); res["transcript"] = tp
    else:
        res.update(treatment_ok=False, turns=0, usage={}, bytes_by_source={}, weighted_input=0)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A,B,C,D,E,F,G,H,I,J")
    ap.add_argument("--fixtures", default="all")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--refs", default=os.environ.get("SAMEWRITE_REF_DIR", ""))
    ap.add_argument("--cfg-base", default=os.path.join(HERE, "cfg_vnext"))
    ap.add_argument("--cred", default=os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")),
                                                   ".credentials.json"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    arms = a.arms.split(",")
    names = sorted(FIXTURES) if a.fixtures == "all" else a.fixtures.split(",")
    cli = subprocess.run([CLAUDE, "--version"], capture_output=True, text=True).stdout.strip()
    jobs = [(arm, n, r) for r in range(a.repeat) for n in names for arm in arms]
    cfgs = {(arm, n, r): build_cfg(arm, a.cfg_base, a.refs, a.cred, f"{n}-r{r}") for arm, n, r in jobs}
    print(f"{len(jobs)} run · model={a.model} · cli={cli} · jobs={a.jobs} · one config dir per run", flush=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(run_one, arm, n, r, cfgs[(arm, n, r)], a.model, a.timeout, a.refs): (arm, n, r)
                    for arm, n, r in jobs}
            for fut in concurrent.futures.as_completed(futs):
                res = fut.result(); res["cli"] = cli
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                u = res.get("usage", {})
                print(f"{res['arm']:2s} {res['fixture']:14s} r{res['rep']} {res['verdict']:8s} rc={res['rc']:>2} "
                      f"{res['sec']:>6}s turns={res.get('turns', 0):>2} in={u.get('input_tokens', 0):>5} "
                      f"cr={u.get('cache_read_input_tokens', 0):>7} cc={u.get('cache_creation_input_tokens', 0):>6} "
                      f"out={u.get('output_tokens', 0):>5} treat={'ok' if res.get('treatment_ok') else 'BAD'}", flush=True)
    finally:
        for f in CRED_COPIES:       # tiap salinan kredensial yang dibuat: hapus, apa pun nama asalnya
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    main()
