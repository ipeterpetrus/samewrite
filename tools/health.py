#!/usr/bin/env python3
"""Apakah guard masih benar-benar terpasang, dan apa yang terjadi pada run ini?

Ledger yang diam BUKAN jawaban: diam bisa berarti guard lepas dari settings.json,
atau memang tak ada sesi. Alat ini membandingkan ledger dengan kanal LAIN — mtime
transcript sesi — supaya deteksinya tidak melingkar, lalu menulis SATU baris rekaman
per run. Tanpa baris itu, "job jalan tapi diam" tak terbedakan dari "job mati".

pakai: health.py --ledgers L [L ...] [--sessions DIR ...] [--runlog OUT.jsonl]
                 [--field nama=nilai ...] [--stale-hours 24] [--grace-hours 72]
Mencetak ringkasan manusia, plus satu baris "ALERT|SEV|TYPE|pesan" per masalah.
"""
import argparse, glob, json, os, time

H = 3600.0


def newest_mtime(dirs):
    """Sesi terakhir kali aktif, dibaca dari transcript — sumber yang tak dipengaruhi guard."""
    best = 0.0
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            try:
                best = max(best, os.path.getmtime(f))
            except OSError:
                pass
    return best


def scan(paths):
    checked = denied = 0
    last = 0
    for p in paths:
        try:
            fh = open(p, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                ev = r.get("event")
                if ev == "checked":
                    checked += 1
                    last = max(last, int(r.get("ts", 0)))
                elif ev == "denied":
                    denied += 1
    return checked, denied, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers", nargs="+", required=True)
    ap.add_argument("--sessions", nargs="*", default=[])
    ap.add_argument("--runlog")
    ap.add_argument("--field", action="append", default=[])
    ap.add_argument("--stale-hours", type=float, default=24)
    ap.add_argument("--grace-hours", type=float, default=72)
    a = ap.parse_args()

    now = time.time()
    checked, denied, last = scan(a.ledgers)
    sess = newest_mtime(a.sessions)
    rec = {"ts": int(now), "checked": checked, "denied": denied,
           "ledger_age_h": round((now - last) / H, 2) if last else None,
           "session_age_h": round((now - sess) / H, 2) if sess else None}
    for pair in a.field:
        name, _, value = pair.partition("=")
        rec[name] = value
    if a.runlog:
        try:
            with open(a.runlog, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"ALERT|MED|failed|samewrite: rekaman run gagal ditulis ke {a.runlog}: {e}")

    sess_fresh = sess and (now - sess) < a.stale_hours * H
    if sess_fresh and last and (now - last) > a.stale_hours * H:
        print(f"ALERT|MED|stale|samewrite: sesi Claude aktif {rec['session_age_h']}j lalu tapi "
              f"ledger guard diam {rec['ledger_age_h']}j — guard mungkin lepas dari settings.json")
    elif sess_fresh and not last:
        # belum pernah sekali pun menulis: beri masa tenggang, guard yang baru dipasang wajar diam
        oldest = min((os.path.getmtime(p) for p in a.ledgers if os.path.exists(p)), default=0)
        if oldest and (now - oldest) > a.grace_hours * H:
            print(f"ALERT|MED|stale|samewrite: sesi Claude aktif tapi ledger nol record "
                  f"selama >{a.grace_hours:.0f} jam — guard tak pernah menembak sekali pun")
    print(f"rekaman: checked={checked} denied={denied} "
          f"ledger_age={rec['ledger_age_h']}j session_age={rec['session_age_h']}j")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
