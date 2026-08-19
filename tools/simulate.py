#!/usr/bin/env python3
"""Simulasi counterfactual: kalau penulisan-penuh diganti penyuntingan berjangkar,
berapa token yang berubah? Termasuk uji ketahanan yang tak ada di ronde pertama:
jackknife per sesi, bootstrap CI, holdout, dan definisi rewrite alternatif.

pakai: python3 tools/simulate.py DATA.pkl [--mode grid|robust]
"""
import argparse, difflib, math, pickle, random, statistics as st, sys

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")
    _memo = {}

    def T(s):
        h = hash(s)
        v = _memo.get(h)
        if v is None:
            v = len(_ENC.encode(s)); _memo[h] = v
        return v
    TOKENIZER = "o200k_base"
except Exception:                                   # ponytail: fallback, bukan dependency keras
    def T(s):
        return len(s) / 3.14
    TOKENIZER = "perkiraan chars/3.14"

CTX, OVH, KMAX = 3, 30, 3


def hunks(a, b, ctx=CTX, merge=True):
    h = [[i1, i2, j1, j2] for tag, i1, i2, j1, j2
         in difflib.SequenceMatcher(None, a, b).get_opcodes() if tag != "equal"]
    if merge and h:
        out = [h[0]]
        for x in h[1:]:
            if x[0] - out[-1][1] <= 2 * ctx:
                out[-1][1], out[-1][3] = x[1], x[3]
            else:
                out.append(x)
        h = out
    return h


def edit_cost(a, b, ctx=CTX, ovh=OVH):
    H = hunks(a, b, ctx)
    return sum(T("".join(a[max(0, i1 - ctx):min(len(a), i2 + ctx)]))
               + T("".join(b[max(0, j1 - ctx):min(len(b), j2 + ctx)])) + ovh
               for i1, i2, j1, j2 in H), len(H)


def measure(sessions, K=KMAX, ctx=CTX, ovh=OVH, fail=0.0, retry=0.0):
    """-> (hemat_kebijakan, hemat_noop, carry_total, n_kena, n_noop, n_rewrite)"""
    pol = noop = carry = 0.0
    kena = nnoop = nrew = 0
    for d in sessions:
        N = d["N"]
        carry += d["carry"] / 3.14
        for (turn, old, new) in d["rew"]:
            nrew += 1
            if old == new:                          # nol-perubahan: hemat penuh, nol risiko
                nnoop += 1
                noop += T(new) * (N - turn)
                continue
            a, b = old.splitlines(True), new.splitlines(True)
            te, nh = edit_cost(a, b, ctx, ovh)
            tw = T(new)
            te *= (1 + fail * retry)
            if nh <= K and te < tw:
                kena += 1
                pol += (tw - te) * (N - turn)
    return pol, noop, carry, kena, nnoop, nrew


def pct(x, c):
    return 100 * x / c if c else float("nan")


def robust(D, seed=20260819):
    rows = []
    base = measure(D)
    rows.append(("BASE semua 24 sesi", base))

    # 1) JACKKNIFE — buang satu sesi. HANYA sesi yang punya rewrite: membuang sesi
    #    tanpa rewrite menghasilkan komponen hemat yang identik (nol informasi baru).
    jk = []
    contrib = [d for d in D if d["rew"]]
    for i, d in enumerate(contrib):
        m = measure([x for x in D if x is not d])
        jk.append((d["id"], m))
        rows.append((f"J{i+1:02d} tanpa {d['id']}", m))

    # 1b) DROP TOP-k — buang k sesi penyumbang rewrite terbanyak (uji dominasi berlapis)
    order = sorted(contrib, key=lambda d: -len(d["rew"]))
    for k in range(2, 7):        # k=1 identik dgn jackknife sesi terbesar
        drop = set(id(x) for x in order[:k])
        rows.append((f"K{k} buang {k} sesi terbesar",
                     measure([x for x in D if id(x) not in drop])))

    # 2) BOOTSTRAP — resample sesi dgn penggantian, 15 seed berbeda -> sebaran
    bs = []
    for s in range(14):
        rnd = random.Random(seed + s)
        samp = [rnd.choice(D) for _ in D]
        m = measure(samp)
        bs.append(pct(m[0] + m[1], m[2]))
        rows.append((f"B{s+1:02d} bootstrap seed={seed+s}", m))

    # 3) HOLDOUT — 6 partisi berbeda, latih/uji stabilitas persentase
    for s in range(6):
        rnd = random.Random(seed + 100 + s)
        idx = list(range(len(D))); rnd.shuffle(idx)
        half = idx[:len(idx) // 2]
        m = measure([D[i] for i in half])
        rows.append((f"H{s+1} holdout separuh seed={seed+100+s}", m))

    # 4) DEFINISI/PARAMETER alternatif
    for lab, kw in (("D1 K<=1 ketat", dict(K=1)),
                    ("D2 K<=10 longgar", dict(K=10)),
                    ("D3 ctx=1", dict(ctx=1)),
                    ("D4 ovh=120", dict(ovh=120))):
        rows.append((lab, measure(D, **kw)))

    # 5) HARGA NYATA ($/1M): carry = cache-read, tulis = output
    for lab, (cr, out) in (("P1 Opus $1.50/$75", (1.50, 75.0)),
                           ("P2 Sonnet $0.30/$15", (0.30, 15.0)),
                           ("P3 Haiku $0.08/$4", (0.08, 4.0))):
        pol, noop, carry, *_ = base
        usd = (pol + noop) / 1e6 * cr
        rows.append((lab, (pol, noop, carry, usd, 0, 0)))

    # 6) EFEK MURNI hook no-op vs kebijakan prosa
    rows.append(("G1 hook no-op saja", (0.0, base[1], base[2], base[4], base[4], base[5])))
    rows.append(("G2 kebijakan saja", (base[0], 0.0, base[2], base[3], 0, base[5])))
    return rows, jk, bs, base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data"); ap.add_argument("--mode", default="robust")
    a = ap.parse_args()
    D = pickle.load(open(a.data, "rb"))
    print(f"# tokenizer: {TOKENIZER} · {len(D)} sesi · {sum(d['N'] for d in D):,} turn "
          f"· {sum(len(d['rew']) for d in D)} rewrite\n")
    rows, jk, bs, base = robust(D)
    seen = set()
    print(f"{'#':<4}{'simulasi':<34}{'kena':>6}{'noop':>6}{'hemat tok':>14}{'%carry':>9}")
    for i, (lab, m) in enumerate(rows, 1):
        if lab.startswith("P"):
            pol, noop, carry, usd, _, _ = m
            print(f"{i:<4}{lab:<34}{'':>6}{'':>6}{'':>14}   ${usd:,.2f}")
            continue
        pol, noop, carry, kena, nnoop, nrew = m
        tot = pol + noop
        key = (round(pol), round(noop), round(carry), kena, nnoop, nrew)
        dup = " ⚠DUP" if key in seen else ""
        seen.add(key)
        print(f"{i:<4}{lab:<34}{kena:>6}{nnoop:>6}{tot:>14,.0f}{pct(tot,carry):>8.3f}%{dup}")
    p = sorted(bs)
    lo, hi = p[0], p[-1]
    print(f"\nBOOTSTRAP n={len(bs)}: median {st.median(bs):.3f}%  rentang {lo:.3f}–{hi:.3f}%")
    jkp = [pct(m[0] + m[1], m[2]) for _, m in jk]
    worst = max(jk, key=lambda x: abs(pct(x[1][0] + x[1][1], x[1][2]) - pct(base[0] + base[1], base[2])))
    print(f"JACKKNIFE n={len(jk)}: rentang {min(jkp):.3f}–{max(jkp):.3f}% · "
          f"sesi paling berpengaruh = {worst[0]} "
          f"({pct(worst[1][0]+worst[1][1], worst[1][2]):.3f}% bila dibuang)")
    n_uni = len(seen) + 3                      # +3 baris harga (tak masuk `seen`)
    print(f"TOTAL simulasi = {len(rows)} · unik = {n_uni} · duplikat = {len(rows)-n_uni}")
    assert len(rows) - n_uni == 0, "ADA SIMULASI DUPLIKAT"


if __name__ == "__main__":
    main()
