#!/usr/bin/env python3
"""Bangkitkan transcript sintetis agar orang lain bisa mereproduksi metode tanpa
data siapa pun. Deterministik dari seed.

pakai: python3 tools/make_fixture.py fixture.jsonl [--seed 7] [--turns 400]
"""
import argparse, json, random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--turns", type=int, default=400)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    files = {f"/w/mod{i}.py": [f"def f{j}(): return {j}" for j in range(rnd.randint(20, 120))]
             for i in range(6)}
    with open(a.out, "w") as fh:
        for turn in range(a.turns):
            roll = rnd.random()
            if roll < 0.10:                                  # tulis berkas
                p = rnd.choice(list(files))
                if rnd.random() < 0.15:
                    pass                                     # tulis ulang IDENTIK (no-op)
                elif rnd.random() < 0.5:
                    k = rnd.randrange(len(files[p]))
                    files[p][k] += "  # ubah"                # perubahan terlokalisasi
                else:
                    files[p] = [ln + " x" for ln in files[p]]  # tersebar
                fh.write(json.dumps({"type": "assistant", "message": {"usage": {"output_tokens": 9},
                    "content": [{"type": "tool_use", "name": "Write",
                                 "input": {"file_path": p, "content": "\n".join(files[p]) + "\n"}}]}}) + "\n")
                fh.write(json.dumps({"type": "user", "message": {"content":
                    [{"type": "tool_result", "content": "ok"}]}}) + "\n")
            else:                                            # perintah shell + hasilnya
                fh.write(json.dumps({"type": "assistant", "message": {"usage": {"output_tokens": 7},
                    "content": [{"type": "tool_use", "name": "Bash",
                                 "input": {"command": "grep -n x mod.py | head -20"}}]}}) + "\n")
                fh.write(json.dumps({"type": "user", "message": {"content":
                    [{"type": "tool_result", "content": "o" * rnd.randint(100, 1800)}]}}) + "\n")
    print(f"{a.out}: {a.turns} turn, seed {a.seed}")


if __name__ == "__main__":
    main()
