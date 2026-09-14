#!/usr/bin/env python3
"""Rekonstruksi baris hasil dari direktori kerja + transcript yang TERSIMPAN, tanpa memanggil
model ulang. Dipakai sekali (14/15-Sep): loop utama rig mati pada satu exception sementara
pool tetap menjalankan 125 job — model sudah dibayar, keluaran ada di disk, hanya barisnya hilang.

    python3 reconstruct.py --fixture-set confirm --cfg-base cfg_pres --out runs/confirm1.jsonl

Skor dihitung dengan fungsi yang SAMA seperti rig (verdict/classify/expect/metrics). Yang tak
bisa dipulihkan: `sec` (durasi dinding) dan `rc` CLI — rc dicatat 0 hanya bila stdout giliran
terakhir ada dan transcript memuat usage; selain itu run ditandai INFRA_ERROR. Tiap baris
membawa `reconstructed: true`."""
import argparse, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rig_pres as rp
from fixtures_pres import classify


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture-set", default="confirm"); ap.add_argument("--cfg-base", default=os.path.join(HERE, "cfg_pres"))
    ap.add_argument("--out", required=True); ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--workglob", default="/tmp/pr-*")
    a = ap.parse_args()
    rp.FIXTURES = rp.FIXTURE_SETS[a.fixture_set]
    have = set()
    if os.path.exists(a.out):
        for l in open(a.out):
            if l.strip():
                r = json.loads(l); have.add((r["arm"], r["fixture"], r.get("rep", 0)))
    cli = "2.1.270 (Claude Code)"
    n_ok = n_infra = 0
    for w in sorted(glob.glob(a.workglob)):
        m = re.match(r".*/pr-([A-Za-z]+)-(c\d\d_[a-z_]+)-r(\d)-", w)
        if not m:
            continue
        arm, name, rep = m.group(1), m.group(2), int(m.group(3))
        if (arm, name, rep) in have or name not in rp.FIXTURES or arm not in rp.ARMS:
            continue
        spec = rp.FIXTURES[name]; d = os.path.join(w, name)
        outs = [open(os.path.join(d, f)).read() for f in sorted(os.listdir(d)) if f.startswith("_stdout_t")] if os.path.isdir(d) else []
        cfg = os.path.join(a.cfg_base, f"{arm}-{name}-r{rep}")
        tp = rp.vn.transcript_for(cfg, d) if os.path.isdir(d) else None
        complete = len(outs) == len(spec["turns"]) and bool(outs[-1].strip()) and tp is not None
        row = dict(arm=arm, arm_desc=rp.ARMS[arm][0], fixture=name, kind=spec["kind"], rep=rep, model=a.model,
                   rc=0 if complete else -3, sec=None, reconstructed=True, work=w, cli=cli)
        if complete:
            last = outs[-1]
            v, changed, extra = rp.verdict(spec, d, last)
            c_last = classify(last); c_all = [classify(o) for o in outs]
            ok = bool(spec["expect"](c_last, last, v))
            if len(spec["turns"]) > 1:
                ok = ok and all(not c["preamble"] and not c["closer"] for c in c_all)
            add, rem = rp.vn.diff_loc(spec, d)
            row.update(verdict=v, human_ok=ok, classify_last=c_last, classify_turns=c_all, files_changed=changed,
                       files_added=extra, diff_add=add, diff_rem=rem, out_chars=[len(o) for o in outs])
            row.update(rp.metrics(tp, arm, {t.strip() for t in spec["turns"]})); row["transcript"] = tp
            if not row.get("transcript_ok"):
                row["verdict"] = "INFRA_ERROR"; row["rc"] = -3
        else:
            row.update(verdict="INFRA_ERROR", human_ok=False, classify_last=classify(""), classify_turns=[], files_changed=[],
                       files_added=[], diff_add=0, diff_rem=0, out_chars=[len(o) for o in outs], treatment_ok=False, turns=0,
                       usage={}, weighted_input=0, per_turn=[], injected_bytes=0, listing_bytes=0, transcript_ok=False,
                       infra_reason=f"incomplete run: {len(outs)}/{len(spec['turns'])} turns, transcript={'yes' if tp else 'no'}")
        with open(a.out, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        have.add((arm, name, rep))
        if row["verdict"] == "INFRA_ERROR":
            n_infra += 1
        else:
            n_ok += 1
        print(f"{arm:2s} {name:26s} r{rep} {row['verdict']:11s} human={'ok' if row['human_ok'] else 'NO'} reconstructed", flush=True)
    print(f"reconstructed {n_ok} scored rows + {n_infra} INFRA_ERROR rows")


if __name__ == "__main__":
    main()
