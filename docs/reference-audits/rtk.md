# Reference audit: rtk

Read-only audit of a depth-1 clone, 2026-09-14, by a subagent with path:line citations.
Coverage label is in the first line (FULL only where every non-binary tracked file was read).
Numeric claims quoted from the reference are EXTERNALLY_REPORTED — none was re-run by SameWrite.

```
Audit selesai (25 tool-call, nol tulis). Laporan:

```
REPO rtk @ d402152ffa050ca3753672e3d49c3f2ff498a07b license=Apache-2.0 (LICENSE:1) lang=Rust (152 .rs; +20 .sh, 9 .ts, 65 .toml) files=577 read_fully=13 → SCOPED
  top-level: src/ tests/ hooks/ scripts/ docs/ openclaw/ .claude/ .github/ Formula build.rs Cargo.toml (version 0.48.0, Cargo.toml:3)

WHAT: Single Rust binary CLI proxy — `rtk <cmd>` runs the real command, captures output, and prints a shrunk version; per-agent hooks rewrite `git status` → `rtk git status` before execution so the agent never sees raw output (README.md:38-41; hooks/README.md:28).

MECHANISM:
- Claude Code: PreToolUse hook, matcher "Bash", command `rtk hook claude` (native binary; src/hooks/init.rs:1395-1401, src/hooks/constants.rs:8-12). Legacy shell variant hooks/claude/rtk-rewrite.sh:1-107 delegates to `rtk rewrite` and returns `hookSpecificOutput.updatedInput` (+ `permissionDecision: allow` when no ask/deny rule). ONLY PreToolUse — no PostToolUse/Stop/SessionStart anywhere in src/hooks (grep: only test fixtures init.rs:7535,7780).
- Native entry: src/hooks/hook_cmd.rs:692 `run_claude()` → :595 `process_claude_payload` reads `/tool_input/command`; empty/absent → Ignore (non-Bash tools untouched). Response written FIRST, then audit + sqlite log (:716-727).
- Rewrite core: src/discover/registry.rs:630 `rewrite_command` over 98 regex `RtkRule`s in src/discover/rules.rs:22-30 (e.g. `cat` → `rtk read`, rules.rs:127); heredoc skip registry.rs:321; `RTK_DISABLED=1` prefix skip :534-545; command-chain split :327.
- Permission-aware: src/hooks/permissions.rs:29-44 reads Claude's deny/ask/allow from project+global settings(.local).json (:143-171); Deny→exit 2 passthrough, Ask/Default→exit 3 rewrite-without-allow (src/hooks/rewrite_cmd.rs:96-99, :199-211 "Default MUST map to ask").
- Instruction side: `rtk init` writes ~/.claude/RTK.md + `@RTK.md` ref / `<!-- rtk-instructions vN -->` block in CLAUDE.md (init.rs:148-156, :227, :1024-1045); body = hooks/rtk-awareness.md (default = 8 lines, says nothing about rtk; high/full add `rtk proxy`, `RTK_DISABLED=1`).
- Never-worse guard: src/core/guard.rs:17-23 falls back to raw if filtered has more est. tokens; src/core/runner.rs:16-24 `emit_guarded`.

FILTERS (strategy per class):
- Tests = failures-only + collapsed pass count: pytest src/cmds/python/pytest_cmd.rs:1,75-168 (cap CAP_WARNINGS=10 failures :9-10); cargo test/nextest src/cmds/rust/cargo_cmd.rs:163,222-225,633-823.
- Git = reformat: status from porcelain src/cmds/git/git.rs:2036-2044; add/commit/push → "ok"/"ok abc1234" :2208,2359-2361,2410.
- Search = group-by-file + cap + tee overflow, engine never substituted: src/cmds/system/search.rs:1-4,582,810.
- ls = tree + CAP_INVENTORY=50 truncation src/cmds/system/ls.rs:367-368; log/docker/kubectl logs = dedupe with counts src/cmds/system/log_cmd.rs:1,67-110.
- Caps global: src/core/truncate.rs:5-12 (errors 20 / warnings 10 / list 20 / inventory 50).
- Declarative DSL: src/core/toml_filter.rs:1-27 — 8-stage pipeline (strip_ansi→replace→match_output→strip/keep_lines→truncate_lines_at→head/tail→max_lines→on_empty), lookup `.rtk/filters.toml` > `~/.config/rtk/filters.toml` > built-in src/filters/*.toml (embedded by build.rs, e.g. ping.toml:1-12 with inline tests). Source-file read = comment/body stripping src/core/filter.rs:1,312-320.

RAW-PRESERVATION: YES, failure/truncation-driven. src/core/tee.rs:1-58: mode sqlite (default) stores raw ONLY when exit≠0 (:53-57) → hint `[full output: rtk recall <12-hex>]` (:24); tee mode writes files on failure, or on success too with `tee_on_success` (:40-51). Store: src/core/retriever.rs (content-addressed sha256 cmd+content :83-88, gzip, defaults 10 MiB/entry, 200 entries, 30-day retention :15-17, MIN_FAILURE_BYTES=500 :18); path `$XDG_DATA_HOME/rtk/recall.db` or `RTK_RECALL_DB` (:171-186). Legacy tee dir `~/.local/share/rtk/tee`, 0700 (src/core/tee_file.rs:1-2,319). Successful truncated output is NOT stored in sqlite mode — hint says so but there's no spool of it.

PRIVACY: No general secret redaction of output. Targeted: aws lambda/iam skip Environment/policy docs (src/cmds/cloud/aws_cmd.rs:840,869) BUT `secretsmanager get-secret-value` prints `Secret: ...` (:1503-1519); dotnet binlog scrubs env-like vars to [REDACTED] (src/cmds/dotnet/binlog.rs:640). Local state stores FULL command lines (not output): history.db `commands.original_cmd/rtk_cmd`, `hook_decisions.raw_cmd` per Bash call incl. session_id/tool_use_id/cwd (src/core/tracking.rs:327-334,391-401); hook-audit.log (opt-in RTK_HOOK_AUDIT, hook_cmd.rs:538-556); recall.db holds raw failing output (gz, private dir). Telemetry opt-in, names only (README.md:481-497).

CLAIMS (EXTERNALLY_REPORTED): README.md:6 "cuts up to 90% of the bash output your agent reads"; :62 "RTK cuts **up to 90% of the bash output** ... not the same as cutting your bill by 90%"; per-command "-90%"/"-80%"/"-99%" tags :206-252; :358 "100% rtk adoption across all conversations and subagents". Scorer = `bytes/4` (README.md:66; tracking.rs:1705-1713). Benchmark exists: scripts/benchmark.sh:31-34 `count_tokens=(len+3)/4`, runs unix vs rtk pairs and flags NEGATIVE cases (:67-80); scripts/benchmark/run.ts = Multipass VM integration suite. Scorer self-test: estimate_tokens has unit test (tracking.rs:1884-1886); benchmark.sh's own count_tokens has NO test; no real tokenizer anywhere (README.md:66 admits).

OWNED IDENTIFIERS: commands `rtk {gain,discover,learn,init,config,proxy,recall,run,hook,hook-audit,pipe,cc-economics,verify,trust,untrust,session,rewrite,telemetry,smart,deps,json}` (src/core/constants.rs:9-33). Files: ~/.config/rtk/{config.toml,filters.toml,trusted_filters.json}; ~/.local/share/rtk/{history.db,recall.db,tee/,hook-audit.log}; ~/.claude/{RTK.md,hooks/rtk-rewrite.sh,hooks/.rtk-hook.sha256}; project `.rtk/filters.toml`; CLAUDE.md markers `@RTK.md` + `<!-- rtk-instructions … -->`; cache `~/.cache/rtk-hook-version-ok`. Env: RTK_DISABLED RTK_TELEMETRY_DISABLED RTK_DB_PATH RTK_RECALL RTK_RECALL_DB RTK_TEE RTK_TEE_DIR RTK_HOOK_AUDIT RTK_AUDIT_DIR RTK_NO_TOML RTK_TOML_DEBUG RTK_TRUST_PROJECT_FILTERS RTK_BIN RTK_TELEMETRY_URL/TOKEN. settings.json: `hooks.PreToolUse[matcher=Bash]`.

COMPOSE NOTES: No direct conflict — rtk touches only PreToolUse(Bash) and ignores payloads without `tool_input.command` (hook_cmd.rs:596-603), so a samewrite PreToolUse(Write) hook never meets it. Two soft overlaps: (1) both edit CLAUDE.md — samewrite's skill block must not sit inside rtk's `<!-- rtk-instructions -->` markers (rtk rewrites/uninstalls that region, init.rs:1045); (2) if samewrite ever registers a Bash-matcher hook, ordering matters: rtk emits `updatedInput` and may set `permissionDecision: allow` (hook_cmd.rs:577-590), and Claude Code applies multiple hooks' updatedInput sequentially — a later hook sees the `rtk`-prefixed command. Also: rtk logs every Bash command line to history.db regardless of rewrite (hook_cmd.rs:716-727 "fires on every single Bash tool call now") — relevant if samewrite's Write content is echoed through Bash. Any rtk `cat`/`head`/`grep` rewrite (`cat` → `rtk read`) changes what Read-via-Bash returns — samewrite must not assume byte-exact file echo from Bash; use the Read tool (bypasses hook, README.md:145).

BORROW CANDIDATES (max 4):
1. never-worse guard (emit filtered only if est. tokens ≤ raw) → src/core/guard.rs:17-23 + runner.rs:16-24.
2. failure-only raw spool with content-hash recall hint → src/core/tee.rs:20-26,53-57 + retriever.rs:83-88 (samewrite could keep the pre-image of a Write for recall the same way).
3. Permission-precedence contract: Deny>Ask>Allow>Default-as-ask, never auto-allow on no-match → src/hooks/permissions.rs:24-29 + rewrite_cmd.rs:199-211 (tested).
4. Hook hygiene: response-first-then-log, stdin 1 MiB cap, BOM strip, exit 0 on every failure path → hook_cmd.rs:17-28,716-727; hooks/README.md:281-291.
```

Coverage: 13 berkas dibaca utuh / 577; sisanya lewat `grep -n`/`sed -n` sampel bertarget (main.rs, init.rs 11k baris, registry.rs 7k, tracking.rs, retriever.rs, hook_cmd.rs, git.rs, cargo/pytest/ls/log/search cmds, config.rs, toml_filter.rs, benchmark.sh). Tidak diperiksa: openclaw/, hooks/{hermes,pi,opencode,…}, docs/ selain savings-explained, tests/*.rs isi, telemetry.rs.```
