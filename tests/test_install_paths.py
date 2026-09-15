#!/usr/bin/env python3
"""The install commands in README must still describe this repository.

A README command rots silently: the path moves, the file is renamed, the tag naming changes, and
nothing fails until a stranger types it. This extracts the commands from README and checks the
layout they depend on against the actual tree and against an archive built exactly the way GitHub
builds one for a tag.

Deterministic and offline. It does not download anything and does not install anything — it proves
the SHAPE is right, which is the part that can rot in a repository. Whether the published URL is
live is a release-time question, and a different one.

Standalone: run this file."""
import hashlib, io, os, re, subprocess, sys, tarfile, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


def version():
    import json
    return json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]


def readme():
    return open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()


def main():
    v = version()
    r = readme()
    print(f"product version: {v}\n")

    # ---------------------------------------------------------------- the pins
    raw = re.findall(r"raw\.githubusercontent\.com/ipeterpetrus/samewrite/([^/]+)/(\S+?)(?=[\s`|])", r)
    tars = re.findall(r"archive/refs/tags/([^/\s`]+)\.tar\.gz", r)
    check("README pins at least one raw skill URL", bool(raw), True)
    check("README pins at least one release tarball", bool(tars), True)
    # A release-pinned install must name a tag, never a moving branch. `main` here is how a user
    # ends up installing something nobody inspected.
    moving = sorted({ref for ref, _ in raw if ref in ("main", "master", "HEAD", "latest")} |
                    {t for t in tars if t in ("main", "master", "HEAD", "latest")})
    check("no install URL points at a moving ref", moving, [])
    refs = sorted({ref for ref, _ in raw} | set(tars))
    check("every pinned install ref names the current version", refs, [f"v{v}"])

    # ---------------------------------------------------------------- the paths those URLs need
    for ref, path in raw:
        q = os.path.join(ROOT, path)
        check(f"raw path exists in this tree: {path}", os.path.exists(q), True)

    # ---------------------------------------------------------------- the archive shape
    # GitHub names a tag archive's root directory `<repo>-<tag without leading v>`. Build one the
    # same way and check the subpath the README command globs for actually lands there.
    root_name = f"samewrite-{v}"
    with tempfile.TemporaryDirectory() as d:
        tgz = os.path.join(d, "candidate.tar.gz")
        subprocess.run(["git", "-C", ROOT, "archive", "--format=tar.gz",
                        f"--prefix={root_name}/", "-o", tgz, "HEAD"], check=True)
        with tarfile.open(tgz) as tf:
            names = tf.getnames()
        sub = f"{root_name}/skills/samewrite/SKILL.md"
        check("candidate archive contains the OpenClaw install subpath", sub in names, True)
        check("archive root matches the GitHub tag naming convention",
              all(n == root_name or n.startswith(root_name + "/") for n in names), True)
        # the glob the README uses must match exactly one directory
        import fnmatch
        hits = sorted({n.split("/")[0] for n in names if fnmatch.fnmatch(n, "samewrite-*/skills/samewrite")})
        check("the README glob resolves to exactly one directory", len(hits), 1)

        with tempfile.TemporaryDirectory() as e:
            with tarfile.open(tgz) as tf:
                tf.extractall(e)
            got = open(os.path.join(e, sub), "rb").read()
            want = open(os.path.join(ROOT, "skills", "samewrite", "SKILL.md"), "rb").read()
            check("archived skill is byte-identical to the working tree",
                  hashlib.sha256(got).hexdigest(), hashlib.sha256(want).hexdigest())

    # ---------------------------------------------------------------- host package manager rows
    check("README keeps the Claude package-manager command",
          "claude plugin marketplace add ipeterpetrus/samewrite" in r, True)
    check("README keeps the Codex package-manager command",
          "codex plugin marketplace add ipeterpetrus/samewrite" in r, True)

    # ---------------------------------------------------------------- no accidental version drift
    import json
    cx = json.load(open(os.path.join(ROOT, ".codex-plugin", "plugin.json")))
    mk = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
    check("codex manifest version matches", cx["version"], v)
    check("marketplace metadata version matches", mk["metadata"]["version"], v)
    check("release notes exist for this version",
          os.path.exists(os.path.join(ROOT, "docs", f"RELEASE_NOTES_{v}.md")), True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
