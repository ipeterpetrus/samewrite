#!/usr/bin/env python3
"""Run konfirmatori: 4 tugas BARU, endpoint & uji dikunci di PREREG_konfirmatori.md.
Menulis ledger per-request supaya hasilnya bisa diaudit orang lain."""
import argparse, json, os, re, subprocess, sys, tempfile, textwrap, time, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rig_modes import CFG, ONELINER
HERE=os.path.dirname(os.path.abspath(__file__)); CLAUDE=os.path.expanduser("~/.local/bin/claude")
def D(s): return textwrap.dedent(s).lstrip()

T = {
 "late_binding": dict(mod=D('''
    def makers():
        out = []
        for i in range(3):
            out.append(lambda: i)
        return out
 '''), test=D('''
    from mod import makers
    def test_each_closure_keeps_its_own_i():
        assert [f() for f in makers()] == [0, 1, 2]
 '''), facts=[r"closure|lambda|penutupan", r"\bi\b.{0,40}(terikat|bound|shared|dibagi|referen)|late.?bind",
              r"default.{0,15}arg|i=i|functools|partial|nilai saat itu"]),
 "set_order": dict(mod=D('''
    def firsts(names):
        return list({n[0] for n in names})
 '''), test=D('''
    from mod import firsts
    def test_order_follows_input():
        assert firsts(["zebra", "apel", "zink", "bola"]) == ["z", "a", "b"]
 '''), facts=[r"\bset\b|himpunan", r"urutan|order", r"dict\.fromkeys|list|seen|terurut|insertion"]),
 "shallow_copy": dict(mod=D('''
    def clone(config):
        return dict(config)
 '''), test=D('''
    from mod import clone
    def test_nested_not_shared():
        a = {"x": {"y": 1}}
        b = clone(a)
        b["x"]["y"] = 2
        assert a["x"]["y"] == 1
 '''), facts=[r"shallow|dangkal|dict\(", r"nested|bersarang|dalam", r"deepcopy|salin dalam|copy\.deepcopy"]),
 "identity_cmp": dict(mod=D('''
    def same_code(a, b):
        return a is b
 '''), test=D('''
    from mod import same_code
    def test_equal_strings_are_same_code():
        assert same_code("ab" + "c", "abc") is True
 '''), facts=[r"\bis\b.{0,30}identitas|identity|objek yang sama|alamat", r"==|kesetaraan|equality",
              r"interning|intern|same_code"]),
}
PROMPT=("Jelaskan kenapa test_target.py gagal dan apa perbaikan yang benar. "
        "JANGAN menyunting berkas apa pun — cukup jawab.")

# Setiap run berskor di repo ini memakai permukaan prompt Indonesia, dan itu tak pernah
# diungkap sampai 4-Sep. `--lang en` menjalankan replikasi yang dipra-registrasi di
# PREREGISTRATION_english_replication.md. Kalimatnya terjemahan SETIA dari yang Indonesia,
# bukan parafrasa yang lebih longgar — kalau yang diuji bukan padanan, hasilnya tak
# menjawab apa pun soal bahasa.
LANG = {
 "id": dict(prompt=PROMPT, oneline=ONELINER["caveman"]),
 "en": dict(prompt=("Explain why test_target.py fails and what the correct fix is. "
                    "Do NOT edit any file — just answer."),
            oneline="Answer as briefly as possible, without reducing the technical content."),
}

def usage_rows(work, task, run_id, arm, rep):
    s="-"+os.path.join(work,task).strip("/").replace("/","-").replace("_","-")
    rows=[]; seen=set()
    for R in ("cfg_plain/projects","cfg_cav/projects"):
        for f in glob.glob(os.path.join(HERE,R,s,"*.jsonl")):
            b=os.path.basename(f)
            if b in seen: continue
            seen.add(b)
            t=0
            for line in open(f,errors="replace"):
                if '"usage"' not in line: continue
                try: o=json.loads(line)
                except: continue
                u=(o.get("message") or {}).get("usage") or {}
                if not u: continue
                t+=1
                rows.append(dict(run_id=run_id, arm=arm, task=task, rep=rep, turn=t,
                    input_tokens=u.get("input_tokens") or 0,
                    cache_creation=u.get("cache_creation_input_tokens") or 0,
                    cache_read=u.get("cache_read_input_tokens") or 0,
                    output_tokens=u.get("output_tokens") or 0))
    return rows

def one(task, arm, rep, model, timeout, ledger, lang="id"):
    spec=T[task]; work=tempfile.mkdtemp(prefix=f"c9-{task}-{arm}-"); d=os.path.join(work,task)
    os.makedirs(d)
    open(os.path.join(d,"mod.py"),"w").write(spec["mod"])
    open(os.path.join(d,"test_target.py"),"w").write(spec["test"])
    cfg=os.path.join(HERE, CFG["caveman" if arm=="mode" else arm])
    L=LANG[lang]
    prompt=L["prompt"] if arm!="oneline" else L["oneline"]+" "+L["prompt"]
    env=dict(os.environ, CLAUDE_CONFIG_DIR=cfg); t0=time.time()
    try:
        p=subprocess.run([CLAUDE,"-p",prompt,"--model",model,"--permission-mode","acceptEdits"],
                         cwd=d,capture_output=True,text=True,timeout=timeout,env=env)
        rc,out=p.returncode,(p.stdout or "")
    except subprocess.TimeoutExpired: rc,out=-1,""
    run_id=f"{task}-{arm}-{rep}" if lang=="id" else f"{lang}-{task}-{arm}-{rep}"
    rows=usage_rows(work,task,run_id,arm,rep)
    with open(ledger,"a") as fh:
        for r in rows: fh.write(json.dumps(r)+"\n")
    banner=any("MODE ACTIVE" in open(f,errors="replace").read(60000)
               for R in ("cfg_plain/projects","cfg_cav/projects")
               for f in glob.glob(os.path.join(HERE,R,
                   "-"+os.path.join(work,task).strip("/").replace("/","-").replace("_","-"),"*.jsonl")))
    return dict(run_id=run_id, lang=lang, task=task, arm=arm, rep=rep, rc=rc, sec=round(time.time()-t0,1),
                banner=banner, turns=len(rows),
                output_total=sum(r["output_tokens"] for r in rows),
                facts=sum(1 for r in spec["facts"] if re.search(r,out,re.I)),
                facts_total=len(spec["facts"]), work=work)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repeat",type=int,default=4)
    ap.add_argument("--model",default="claude-haiku-4-5-20251001")
    ap.add_argument("--timeout",type=int,default=420)
    ap.add_argument("--out",default="confirm.jsonl"); ap.add_argument("--ledger",default="ledger.jsonl")
    ap.add_argument("--lang",default="id",choices=sorted(LANG))
    # Lengan `mode` butuh cfg_cav (banner lewat hook SessionStart). Replikasi bahasa hanya
    # menguji kalimat vs tanpa-instruksi, jadi ia jalan tanpa config perlakuan sama sekali.
    ap.add_argument("--arms",default="plain,oneline,mode")
    a=ap.parse_args()
    arms=tuple(x for x in a.arms.split(",") if x)
    for rep in range(a.repeat):
        for task in sorted(T):
            for arm in arms:
                r=one(task,arm,rep,a.model,a.timeout,a.ledger,a.lang)
                with open(a.out,"a") as fh: fh.write(json.dumps(r)+"\n")
                print(f"{task:14s} {arm:8s} rep{rep} rc={r['rc']} out={r['output_total']:>5} "
                      f"turn={r['turns']:>2} banner={r['banner']} facts={r['facts']}/{r['facts_total']}",flush=True)
if __name__=="__main__": main()
