#!/usr/bin/env python3
"""Rig benchmark PRESENTASI (continuation §7): lengan A–F + varian mekanisme, config terisolasi
PER RUN, multi-giliran via `claude -p --continue`, skor mekanis + klasifikasi prosa ber-uji-diri.

    python3 rig_pres.py --arms A,B,C,D,Dh,Dm,E,F --fixtures all --out runs/pres1.jsonl \
                        --refs /path/klon --jobs 4

Lengan: A bare · B SameWrite sebelum continuation (skill_before/SKILL.md, = d4a4c76) · C i-have-adhd
penuh (hook asli + flag) · D skill baru (listing + badan on-demand) · Dh D + SessionStart
satu-kalimat P2 (echo) · Dm D + SessionStart satu-kalimat mikro P1 · E D + ponytail (hook asli) ·
F D + i-have-adhd. Lantai konstan semua lengan: listing skill bawaan CLI + skema konektor akun."""
import argparse, concurrent.futures, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "experiments", "vnext")); sys.path.insert(0, HERE)
import carry  # noqa: E402
import msgid  # noqa: E402  one assistant message, however many records carry it
from fixtures import shape_ok  # noqa: E402
from fixtures_pres import classify, blocked_verdict  # noqa: E402
import fixtures_pres, fixtures_confirm  # noqa: E402
FIXTURE_SETS = {"pres": fixtures_pres.FIXTURES, "confirm": fixtures_confirm.FIXTURES}
FIXTURES = FIXTURE_SETS["pres"]
import rig as vn  # noqa: E402  (transcript_for, diff_loc)

CLAUDE = os.environ.get("SAMEWRITE_CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude"))
P2 = ("Lead with the result, blocker, or next action. Use numbered steps only for user actions; "
      "omit unchanged state, recaps, and generic closers. Expand when requested.")
P1 = "Lead with the result or next action. Keep only information needed to act or verify; expand when explicitly requested."
ARMS = {
    "A": ("bare agent", set()),
    "B": ("SameWrite before this continuation (skill at d4a4c76)", {"before"}),
    "C": ("i-have-adhd full (real always-on hook)", {"adhd"}),
    "D": ("SameWrite now: new listing description + on-demand body", {"samewrite"}),
    "Dh": ("D + SessionStart one-liner P2 (echo hook)", {"samewrite", "p2"}),
    "Dm": ("D + SessionStart one-liner P1 micro (echo hook)", {"samewrite", "p1"}),
    "E": ("D + ponytail (real hooks)", {"samewrite", "ponytail"}),
    "F": ("D + i-have-adhd (real hook)", {"samewrite", "adhd"}),
    # confirmatory (hardening §10): coexistence arms stack on Dh, the candidate default
    "Eh": ("Dh + ponytail (real hooks)", {"samewrite", "p2", "ponytail"}),
    "Fh": ("Dh + i-have-adhd (real hook)", {"samewrite", "p2", "adhd"}),
    "Gh": ("Dh + ponytail + i-have-adhd", {"samewrite", "p2", "ponytail", "adhd"}),
}
BANNERS = {"ponytail": "PONYTAIL MODE ACTIVE", "adhd": "ADHD MODE ACTIVE", "p2": P2[:40], "p1": P1[:40]}
FOREIGN = ["PONYTAIL MODE ACTIVE", "ADHD MODE ACTIVE", "CAVEMAN MODE ACTIVE", P2[:40], P1[:40], "superpowers"]
CRED_COPIES = []


def build_cfg(arm, base, refs, cred_src, before, tag):
    cfg = os.path.join(base, f"{arm}-{tag}")
    if os.path.isdir(cfg):
        shutil.rmtree(cfg)                       # direktori milik rig sendiri, dibangun ulang tiap run
    os.makedirs(os.path.join(cfg, "skills"))
    parts = ARMS[arm][1]; settings = {"hooks": {}}
    if "before" in parts:
        os.makedirs(os.path.join(cfg, "skills", "samewrite"))
        shutil.copyfile(before, os.path.join(cfg, "skills", "samewrite", "SKILL.md"))
    if "samewrite" in parts:
        shutil.copytree(os.path.join(ROOT, "skills", "samewrite"), os.path.join(cfg, "skills", "samewrite"))
        shutil.copytree(os.path.join(ROOT, "skills", "edit-discipline"), os.path.join(cfg, "skills", "edit-discipline"))
    for key, text in (("p2", P2), ("p1", P1)):
        if key in parts:
            settings["hooks"].setdefault("SessionStart", []).append(
                {"matcher": "startup|resume|clear|compact",
                 "hooks": [{"type": "command", "command": "printf '%s\\n' " + json.dumps(text)}]})
    if "ponytail" in parts:
        pd = os.path.join(refs, "ponytail", "hooks"); assert os.path.isdir(pd), "klon ponytail tak ada di --refs"
        settings["hooks"].setdefault("SessionStart", []).append(
            {"matcher": "startup|resume|clear|compact", "hooks": [{"type": "command", "command": f"node {pd}/ponytail-activate.js"}]})
        settings["hooks"].setdefault("UserPromptSubmit", []).append({"hooks": [{"type": "command", "command": f"node {pd}/ponytail-mode-tracker.js"}]})
        settings["hooks"].setdefault("SubagentStart", []).append({"hooks": [{"type": "command", "command": f"node {pd}/ponytail-subagent.js"}]})
    if "adhd" in parts:
        ad = os.path.join(refs, "i-have-adhd"); assert os.path.isdir(ad), "klon i-have-adhd tak ada di --refs"
        open(os.path.join(cfg, ".i-have-adhd-always"), "w").close()
        settings["hooks"].setdefault("SessionStart", []).append(
            {"matcher": "startup|resume|clear|compact",
             "hooks": [{"type": "command", "command": f"CLAUDE_PLUGIN_ROOT={ad} node {ad}/hooks/always-on.mjs"}]})
    if not settings["hooks"]:
        del settings["hooks"]
    json.dump(settings, open(os.path.join(cfg, "settings.json"), "w"), indent=2)
    if cred_src and os.path.exists(cred_src):
        dst = os.path.join(cfg, ".credentials.json"); shutil.copyfile(cred_src, dst); os.chmod(dst, 0o600); CRED_COPIES.append(dst)
    return cfg


def metrics(tp, arm, prompts):
    """usage total + per giliran (dipisah pada pesan user == prompt giliran), byte tersuntik, perlakuan."""
    try:
        turns, items, usage = carry.scan(tp)
    except Exception as e:
        return dict(turns=0, usage={}, bytes_by_source={}, tool_counts={}, listing_bytes=0, injected_bytes=0, per_turn=[],
                    weighted_input=0, treatment_ok=False, banners=[], transcript_ok=False, infra_reason=f"scan: {e}")
    if turns == 0 or not usage:
        return dict(turns=turns, usage=dict(usage), bytes_by_source={}, tool_counts={}, listing_bytes=0, injected_bytes=0,
                    per_turn=[], weighted_input=0, treatment_ok=False, banners=[], transcript_ok=False,
                    infra_reason="no assistant turns / no usage")
    by = {}
    for _, b, src in items:
        by[carry.bucket(src)] = by.get(carry.bucket(src), 0) + b
    per_turn, cur, listing, banners, counts, injected = [], None, "", set(), {}, 0
    ledger = msgid.Ledger()   # one message, however many records carry it
    for line in open(tp, errors="replace"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("type")
        if t == "attachment":
            a = o.get("attachment") or {}
            if a.get("type") == "skill_listing":
                listing += a.get("content") or ""
            injected += len(json.dumps(a.get("content", "")))
        if t == "user":
            c = (o.get("message") or {}).get("content")
            if isinstance(c, str) and c.strip() in prompts:
                cur = {"prompt": c.strip()[:40], "output_tokens": 0, "assistant_msgs": 0}; per_turn.append(cur)
        if t == "assistant":
            u = (o.get("message") or {}).get("usage") or {}
            if cur is not None and ledger.bill(o.get("message")):
                cur["output_tokens"] += u.get("output_tokens") or 0; cur["assistant_msgs"] += 1
            for c in (o.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    counts[c["name"]] = counts.get(c["name"], 0) + 1
        for b in FOREIGN:
            if b in line:
                banners.add(b)
    parts = ARMS[arm][1]
    expect = {BANNERS[k] for k in parts if k in BANNERS}
    low = listing.lower()
    listing_ok = (("- samewrite:" in low) == bool(parts & {"samewrite", "before"})
                  and "- edit-discipline:" not in low           # alias harus TERSEMBUNYI dari listing
                  and not any(x in low for x in ("- ponytail:", "- caveman:", "- i-have-adhd:")))
    return dict(turns=turns, usage={k: int(v) for k, v in usage.items()}, bytes_by_source=by, tool_counts=counts,
                listing_bytes=len(listing), injected_bytes=injected, per_turn=per_turn,
                weighted_input=usage.get("input_tokens", 0) + 1.25 * usage.get("cache_creation_input_tokens", 0)
                + 0.1 * usage.get("cache_read_input_tokens", 0),
                treatment_ok=(expect <= banners and not (banners - expect) and listing_ok), banners=sorted(banners),
                transcript_ok=True)


def verdict(spec, d, out):
    kind = spec["kind"]
    changed = [f for f in spec["files"] if not os.path.exists(os.path.join(d, f))
               or open(os.path.join(d, f)).read() != spec["files"][f]]
    extra = [f for f in os.listdir(d) if f not in spec["files"] and not f.startswith(("_", ".")) and f != "__pycache__"]
    if spec.get("verdict_fn"):                     # oracle khusus (blocker berkas-luar, operasi destruktif)
        spec["_dir"] = d
        return spec["verdict_fn"](spec, changed, extra, out), changed, extra
    if kind == "blocked":
        return blocked_verdict(spec, changed, extra, out), changed, extra
    if kind == "nochange":
        if changed or extra:
            return "SYMPTOM", changed, extra
        if spec.get("must_ask") and not re.search(spec.get("ask_re", r"\?"), out.strip()[-600:], re.I | re.S):
            return "FAIL", changed, extra
        return "ROOT", changed, extra
    if kind == "text":
        facts = sum(1 for r in spec["facts"] if re.search(r, out, re.I))
        shape = spec["shape_fn"](out) if spec.get("shape_fn") else shape_ok(spec["shape"], out)
        ok = facts == len(spec["facts"]) and shape and not changed and not extra
        return ("ROOT" if ok else "FAIL"), changed, extra
    if "test_target.py" in changed or extra:
        return "INVALID", changed, extra
    penv = dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="pyc-"))
    t, ttext = vn.run_pytest(d, spec.get("target", "test_target.py"), penv)
    open(os.path.join(d, "_pytest_target.txt"), "w").write(ttext)
    if t == "infra":
        return "INFRA_ERROR", changed, extra
    if t == "fail":
        return "FAIL", changed, extra
    open(os.path.join(d, "_neighbor_test.py"), "w").write(spec["neighbor"])
    n, ntext = vn.run_pytest(d, "_neighbor_test.py", penv)
    open(os.path.join(d, "_pytest_neighbor.txt"), "w").write(ntext)
    if n == "infra":
        return "INFRA_ERROR", changed, extra
    return ("ROOT" if n == "pass" else "SYMPTOM"), changed, extra


def run_one(arm, name, rep, cfg, model, timeout):
    """Pembungkus: exception apa pun di dalam satu run menjadi baris INFRA_ERROR ber-traceback —
    BUKAN kematian loop utama. Run konfirmatori 14-Sep kehilangan 125 baris karena satu
    FileNotFoundError (agen menghapus berkas fixture) dilempar lewat fut.result()."""
    try:
        return _run_one(arm, name, rep, cfg, model, timeout)
    except Exception:
        import traceback
        return dict(arm=arm, arm_desc=ARMS.get(arm, ("?",))[0], fixture=name, kind=FIXTURES.get(name, {}).get("kind", "?"), rep=rep, model=model,
                    rc=-2, sec=0, verdict="INFRA_ERROR", human_ok=False, classify_last=classify(""), classify_turns=[],
                    files_changed=[], files_added=[], diff_add=0, diff_rem=0, out_chars=[], work="",
                    treatment_ok=False, turns=0, usage={}, weighted_input=0, per_turn=[], injected_bytes=0,
                    listing_bytes=0, transcript_ok=False, infra_reason="rig exception: " + traceback.format_exc()[-800:])


def _run_one(arm, name, rep, cfg, model, timeout):
    spec = FIXTURES[name]
    work = tempfile.mkdtemp(prefix=f"pr-{arm}-{name}-r{rep}-"); d = os.path.join(work, name); os.makedirs(d)
    for fn, body in spec["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and not k.startswith("SAMEWRITE")}
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=os.environ["HOME"])
    outs, rc, t0 = [], 0, time.time()
    for i, prompt in enumerate(spec["turns"]):
        cmd = [CLAUDE, "-p", prompt, "--model", model, "--permission-mode", "acceptEdits",
               "--allowedTools", "Bash(python3:*),Bash(pytest:*),Bash(python:*),Read,Edit,Write,Grep,Glob"] + (["--continue"] if i else [])
        try:
            p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
            rc = p.returncode or rc; outs.append(p.stdout or "")
        except subprocess.TimeoutExpired:
            rc = -1; outs.append("")
    sec = round(time.time() - t0, 1)
    for i, o in enumerate(outs):
        open(os.path.join(d, f"_stdout_t{i + 1}.txt"), "w").write(o)
    last = outs[-1]
    if rc != 0:                                    # CLI gagal/timeout = infrastruktur, bukan model
        v, changed, extra = "INFRA_ERROR", [], []
    else:
        v, changed, extra = verdict(spec, d, last)
    c_last = classify(last); c_all = [classify(o) for o in outs]
    ok_human = bool(spec["expect"](c_last, last, v))
    if len(spec["turns"]) > 1:
        ok_human = ok_human and all(not c["preamble"] and not c["closer"] for c in c_all)
    add, rem = vn.diff_loc(spec, d)
    res = dict(arm=arm, arm_desc=ARMS[arm][0], fixture=name, kind=spec["kind"], rep=rep, model=model, rc=rc, sec=sec,
               verdict=v, human_ok=ok_human, classify_last=c_last, classify_turns=c_all, files_changed=changed,
               files_added=extra, diff_add=add, diff_rem=rem, out_chars=[len(o) for o in outs], work=work)
    tp = vn.transcript_for(cfg, d)
    if tp:
        res.update(metrics(tp, arm, {t.strip() for t in spec["turns"]})); res["transcript"] = tp
    else:
        res.update(treatment_ok=False, turns=0, usage={}, weighted_input=0, per_turn=[], injected_bytes=0, listing_bytes=0)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A,B,C,D,Dh,Dm,E,F"); ap.add_argument("--fixtures", default="all")
    ap.add_argument("--repeat", type=int, default=1); ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--timeout", type=int, default=420); ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--refs", default=os.environ.get("SAMEWRITE_REF_DIR", ""))
    ap.add_argument("--before", default=os.path.join(HERE, "skill_before", "SKILL.md"))
    ap.add_argument("--cfg-base", default=os.path.join(HERE, "cfg_pres"))
    ap.add_argument("--cred", default=os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")), ".credentials.json"))
    ap.add_argument("--fixture-set", default="pres", choices=sorted(FIXTURE_SETS))
    ap.add_argument("--resume", action="store_true", help="lewati job yang sudah punya baris di --out")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    global FIXTURES
    FIXTURES = FIXTURE_SETS[a.fixture_set]
    arms = a.arms.split(","); names = sorted(FIXTURES) if a.fixtures == "all" else a.fixtures.split(",")
    cli = subprocess.run([CLAUDE, "--version"], capture_output=True, text=True).stdout.strip()
    jobs = [(arm, n, r) for r in range(a.repeat) for n in names for arm in arms]
    if a.resume and os.path.exists(a.out):          # lanjutkan: lewati (arm, fixture, rep) yang sudah punya baris
        done = {(json.loads(l)["arm"], json.loads(l)["fixture"], json.loads(l).get("rep", 0)) for l in open(a.out) if l.strip()}
        jobs = [j for j in jobs if j not in done]
        print(f"resume: {len(done)} baris ada, {len(jobs)} job tersisa", flush=True)
    cfgs = {j: build_cfg(j[0], a.cfg_base, a.refs, a.cred, a.before, f"{j[1]}-r{j[2]}") for j in jobs}
    print(f"{len(jobs)} run · model={a.model} · cli={cli} · jobs={a.jobs} · one config per run", flush=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(run_one, arm, n, r, cfgs[(arm, n, r)], a.model, a.timeout): (arm, n, r) for arm, n, r in jobs}
            for fut in concurrent.futures.as_completed(futs):
                res = fut.result(); res["cli"] = cli
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                u = res.get("usage", {}); c = res["classify_last"]
                print(f"{res['arm']:2s} {res['fixture']:16s} {res['verdict']:8s} human={'ok ' if res['human_ok'] else 'NO '} rc={res['rc']:>2} "
                      f"out={u.get('output_tokens', 0):>5} inj={res.get('injected_bytes', 0):>6} pre={int(c['preamble'])} clo={int(c['closer'])} "
                      f"dec={c['decor_steps']} usr={c['user_steps']} st={c['state_lines']} treat={'ok' if res.get('treatment_ok') else 'BAD'}", flush=True)
    finally:
        for f in CRED_COPIES:
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    main()
