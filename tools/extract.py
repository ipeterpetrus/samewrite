#!/usr/bin/env python3
"""Ekstrak dari transcript Claude Code (.jsonl) apa yang dibutuhkan analisis carry.

Keluaran: pickle berisi, per sesi — N turn, ukuran tiap item beserta turn-nya,
dan pasangan (isi_lama, isi_baru) tiap penulisan yang menimpa berkas yang sudah
disentuh sesi itu. TIDAK menyimpan path, prompt, atau isi di luar pasangan itu.

pakai: python3 tools/extract.py OUT.pkl transcript1.jsonl [transcript2.jsonl ...]
"""
import json, os, pickle, sys


def scan(path, seen_write_only=False):
    prev, turn, items, rew = {}, 0, [], []
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line or ('"usage"' not in line and '"tool_use"' not in line
                        and '"tool_result"' not in line):
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        m = o.get("message") or {}
        t = o.get("type")
        if t == "assistant" and isinstance(m, dict):
            if m.get("usage"):
                turn += 1
            for c in (m.get("content") or []):
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    items.append((turn, len(c.get("text", ""))))
                elif c.get("type") == "tool_use":
                    inp = c.get("input") or {}
                    items.append((turn, len(json.dumps(inp, ensure_ascii=False))))
                    if c.get("name") == "Write":
                        p, ct = inp.get("file_path", "?"), inp.get("content", "")
                        if p in prev:
                            rew.append((turn, prev[p], ct))
                        prev[p] = ct
                    elif c.get("name") == "Read" and not seen_write_only:
                        prev.setdefault(inp.get("file_path", "?"), None)
        elif t == "user" and isinstance(m, dict):
            for c in (m.get("content") or []):
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    ct = c.get("content")
                    items.append((turn, len(ct if isinstance(ct, str)
                                            else json.dumps(ct, ensure_ascii=False))))
    N = turn
    return dict(id=os.path.basename(path)[:8], N=N,
                ctx_in=sum(s for _, s in items),
                carry=sum(s * (N - i) for i, s in items),
                items=items,
                rew=[(t, a, b) for (t, a, b) in rew if a is not None])


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out, files = sys.argv[1], sys.argv[2:]
    data = [d for d in (scan(f) for f in files) if d["N"] > 0]
    pickle.dump(data, open(out, "wb"))
    print(f"sesi={len(data)} turn={sum(d['N'] for d in data):,} "
          f"rewrite={sum(len(d['rew']) for d in data)} -> {out}")


if __name__ == "__main__":
    main()
