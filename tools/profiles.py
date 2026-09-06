#!/usr/bin/env python3
"""Find transcripts across every Claude Code profile on this machine.

One machine usually holds more than one config directory: a second account, a work
profile, a `CLAUDE_CONFIG_DIR` pointed elsewhere. `~/.claude/projects/*/*.jsonl` measures
whichever one happens to be first and reports it as "your sessions" — the shell glob gives
no hint that the other 59 projects next door were never read. This module is the fix, and
it is also the reason the tools accept directories: a glob that expands to 3,000 paths can
exceed the argument limit on some shells, and then the error is about `ARG_MAX` rather than
about your logs.

Precedence: `CLAUDE_CONFIG_DIR` (colon-separated list accepted, though the CLI itself reads
a single directory) beats the defaults, then `~/.claude`, `~/.config/claude`, then any
`~/.claude-*` sibling. Order only decides reporting; results are de-duplicated by real path.
"""
import glob, os

TRANSCRIPT_GLOB = os.path.join("projects", "*", "*.jsonl")


def config_dirs():
    """Candidate config directories, most explicit first. Existence is not checked here."""
    out, home = [], os.path.expanduser("~")
    env = os.environ.get("CLAUDE_CONFIG_DIR", "")
    out += [os.path.expanduser(p) for p in env.split(os.pathsep) if p.strip()]
    out.append(os.path.join(home, ".claude"))
    out.append(os.path.join(home, ".config", "claude"))
    out += sorted(glob.glob(os.path.join(home, ".claude-*")))
    seen, uniq = set(), []
    for d in out:
        r = os.path.realpath(d)
        if r not in seen:
            seen.add(r)
            uniq.append(d)
    return uniq


def _walk(d):
    """*.jsonl under a directory: the profile layout first, then any depth."""
    found = sorted(glob.glob(os.path.join(d, TRANSCRIPT_GLOB)))
    if found:
        return found
    out = []
    for root, _dirs, files in os.walk(d):
        out += [os.path.join(root, f) for f in sorted(files) if f.endswith(".jsonl")]
    return out


def resolve(args):
    """-> (transcript paths, roots used). Files pass through; directories are walked;
    an empty argument list means "discover every profile"."""
    paths, roots = [], []
    if args:
        for a in args:
            a = os.path.expanduser(a)
            if os.path.isdir(a):
                roots.append(a)
                paths += _walk(a)
            else:
                paths.append(a)
    else:
        for d in config_dirs():
            got = sorted(glob.glob(os.path.join(d, TRANSCRIPT_GLOB)))
            if got:
                roots.append(d)
                paths += got
    seen, uniq = set(), []
    for p in paths:
        r = os.path.realpath(p)
        if r not in seen:            # two profiles can symlink to one archive
            seen.add(r)
            uniq.append(p)
    return uniq, roots


def note(paths, roots, argv_given):
    """One stderr line naming the scope actually measured. Silence about scope is how a
    one-profile number gets reported as a whole machine."""
    if argv_given and not roots:
        return ""
    where = ", ".join(roots) if roots else "no profile directory found"
    how = "from arguments" if argv_given else "discovered"
    return f"{len(paths)} transcript(s) {how} in {len(roots)} profile(s): {where}"


if __name__ == "__main__":
    p, r = resolve([])
    print(note(p, r, False))
