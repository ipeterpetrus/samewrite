#!/usr/bin/env python3
"""Ekstrak dari transcript Claude Code (.jsonl) apa yang dibutuhkan analisis carry.

PRIVASI — default REDACTED. Isi berkas TIDAK pernah masuk keluaran. Tiap baris
diganti hash 8-byte + jumlah tokennya, dihitung saat ekstraksi. Itu cukup untuk
difflib (blok perubahan identik) dan untuk hitungan token, tanpa menyimpan satu
karakter pun dari kodemu. `--keep-content` mematikan redaksi; keluarannya lalu
memuat isi berkas mentah — jangan dibagikan.

Yang tersimpan: indeks turn, ukuran tiap item, dan pasangan baris-ter-redaksi dari
berkas yang ditimpa. Yang TIDAK tersimpan: path, prompt, isi tool result, isi berkas.

pakai: python3 tools/extract.py OUT.pkl transcript.jsonl [...] [--keep-content]
"""
import hashlib, json, os, pickle, sys

try:
    import tiktoken
    _E = tiktoken.get_encoding("o200k_base")
    def _tok(s): return len(_E.encode(s))
    TOKENIZER = "o200k_base"
except Exception:
    def _tok(s): return max(1, round(len(s) / 3.14))
    TOKENIZER = "perkiraan chars/3.14"


def redact(text):
    """-> (hash tiap baris, token tiap baris). Isi asli tidak dikembalikan."""
    lines = text.splitlines(True)
    return ([hashlib.blake2b(l.encode("utf-8", "replace"), digest_size=8).hexdigest()
             for l in lines],
            [_tok(l) for l in lines])


def scan(path, keep=False):
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
        m, t = o.get("message") or {}, o.get("type")
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
                        cur = ct if keep else redact(ct)
                        if p in prev:
                            rew.append((turn, prev[p], cur))
                        prev[p] = cur
        elif t == "user" and isinstance(m, dict):
            for c in (m.get("content") or []):
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    ct = c.get("content")
                    items.append((turn, len(ct if isinstance(ct, str)
                                            else json.dumps(ct, ensure_ascii=False))))
    N = turn
    return dict(id=os.path.basename(path)[:8], N=N, redacted=not keep,
                ctx_in=sum(s for _, s in items),
                carry=sum(s * (N - i) for i, s in items),
                rew=rew)


def main():
    args = [a for a in sys.argv[1:] if a != "--keep-content"]
    keep = "--keep-content" in sys.argv
    if len(args) < 2:
        sys.exit(__doc__)
    out, files = args[0], args[1:]
    data = [d for d in (scan(f, keep) for f in files) if d["N"] > 0]
    pickle.dump(data, open(out, "wb"))
    print(f"tokenizer={TOKENIZER} sesi={len(data)} turn={sum(d['N'] for d in data):,} "
          f"rewrite={sum(len(d['rew']) for d in data)} "
          f"redaksi={'MATI — keluaran memuat isi berkas, jangan dibagikan' if keep else 'aktif'} -> {out}")


if __name__ == "__main__":
    main()
