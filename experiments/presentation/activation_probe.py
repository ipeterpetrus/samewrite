#!/usr/bin/env python3
"""Probe aktivasi badan skill (hardening §16): kapan model MEMANGGIL `Skill(samewrite)` di bawah
`claude -p`? Tiga varian prompt × N ulangan pada lengan D (skill terpasang, nol hook):
  implicit  — tugas koding biasa (seperti benchmark)
  named     — tugas yang MENYEBUT samewrite ("follow the samewrite skill")
  slash     — prompt diawali `/samewrite` (invokasi eksplisit oleh pengguna)
Keluaran: per varian, berapa run memuat tool_use Skill dan nama skill-nya, plus token keluaran.
Nol perubahan pada produk; hanya mengukur."""
import argparse, json, os, sys, tempfile, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rig_pres as rp  # noqa: E402

TASK = "test_target.py fails. Fix the bug."
FILES = {"mod.py": "def clamp(x, lo, hi):\n    return min(lo, max(hi, x))\n",
         "test_target.py": "from mod import clamp\ndef test_clamp():\n    assert clamp(5, 0, 3) == 3\n"}
VARIANTS = {"implicit": TASK, "named": "Follow the samewrite skill. " + TASK, "slash": "/samewrite " + TASK}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--reps", type=int, default=2); ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--cred", default=os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")), ".credentials.json"))
    a = ap.parse_args()
    base = os.path.join(HERE, "cfg_probe")
    try:
        for name, prompt in VARIANTS.items():
            for rep in range(a.reps):
                cfg = rp.build_cfg("D", base, "", a.cred, "", f"{name}-r{rep}")
                work = tempfile.mkdtemp(prefix=f"probe-{name}-"); d = os.path.join(work, "probe"); os.makedirs(d)
                for fn, body in FILES.items():
                    open(os.path.join(d, fn), "w").write(body)
                env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and not k.startswith("SAMEWRITE")}
                env.update(CLAUDE_CONFIG_DIR=cfg, HOME=os.environ["HOME"])
                t0 = time.time()
                p = subprocess.run([rp.CLAUDE, "-p", prompt, "--model", a.model, "--permission-mode", "acceptEdits",
                                    "--allowedTools", "Bash(python3:*),Bash(pytest:*),Read,Edit,Write,Grep,Glob,Skill"],
                                   cwd=d, capture_output=True, text=True, timeout=300, env=env)
                tp = rp.vn.transcript_for(cfg, d)
                skills, usage, led = [], {}, rp.msgid.Ledger()
                if tp:
                    for line in open(tp, errors="replace"):
                        try:
                            o = json.loads(line)
                        except Exception:
                            continue
                        if o.get("type") == "assistant":
                            u = (o.get("message") or {}).get("usage") or {} \
                                if led.bill(o.get("message")) else {}
                            for k, v in u.items():
                                if isinstance(v, (int, float)):        # usage juga memuat objek bersarang
                                    usage[k] = usage.get(k, 0) + v
                            for c in (o.get("message") or {}).get("content") or []:
                                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Skill":
                                    skills.append(c.get("input", {}).get("skill"))
                src = open(os.path.join(d, "mod.py")).read()
                res = dict(variant=name, rep=rep, rc=p.returncode, sec=round(time.time() - t0, 1), skills=skills,
                           output_tokens=usage.get("output_tokens", 0), cache_read=usage.get("cache_read_input_tokens", 0),
                           fixed=("min(hi, max(lo, x))" in src or "max(lo, min(hi, x))" in src), stdout_head=(p.stdout or "")[:160])
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res) + "\n")
                print(f"{name:9s} r{rep} rc={p.returncode} skills={skills} out={res['output_tokens']} fixed={res['fixed']}", flush=True)
    finally:
        for f in rp.CRED_COPIES:
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    main()
