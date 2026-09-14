# Reference audit: aider

Read-only audit of a depth-1 clone, 2026-09-14, by a subagent with path:line citations.
Coverage label is in the first line (FULL only where every non-binary tracked file was read).
Numeric claims quoted from the reference are EXTERNALLY_REPORTED — none was re-run by SameWrite.

```
REPO aider @ 5dc9490bb35f9729ef2c95d00a19ccd30c26339c license=Apache-2.0 (LICENSE.txt:1-3) files=691 read_fully=1 (benchmark/test_benchmark.py) partial=13 → SCOPED
top-level dirs: aider/ benchmark/ docker/ requirements/ scripts/ tests/

REPO MAP (aider/repomap.py, 867 lines):
- Tags: tree-sitter parse per file + language `*-tags.scm` query (get_tags_raw 279-302); captures `name.definition.*`→def, `name.reference.*`→ref (320-336); if a language yields defs but no refs, pygments `Token.Name` backfills refs (343-364). Cached on disk by (path, mtime) in `.aider.tags.cache.v*` (43, 233-262).
- Ranking: networkx MultiDiGraph referencer→definer edges (470-514), weight = mul × sqrt(num_refs); mul ×10 if ident mentioned in chat, ×10 if snake/camel/kebab len≥8, ×0.1 if `_private`, ×0.1 if defined in >5 files, ×50 if referencer is a chat file (484-514). `nx.pagerank(weight="weight", personalization=…)` (519-525); personalization = 100/len(fnames) for chat files, mentioned files, or path components matching mentioned idents (383, 422-445). Rank distributed across out-edges → per-(file,ident) definitions; chat files excluded from output (536-556).
- Mentions: idents = `re.split(r"\W+", cur_msg_text)` (base_coder.py:678-682); filename matches need stem len≥5 (684-708).
- Budget default: `--map-tokens default=None` (args.py:248-251) → `models.py:782-789`: `map_tokens = 1024; if max_input: max_input/8 clamped to [1024, 4096]`. RepoMap ctor default `map_tokens=1024, map_mul_no_files=8` (47-56) BUT CLI `--map-multiplier-no-files default=2` (args.py:263-266). No chat files → budget × multiplier, capped at context−4096 (121-132).
- Fit: binary search over number of ranked tags, starting at max_map_tokens//25, accept when |tokens−budget|/budget < 0.15 (667-703). Refresh policy `auto|always|files|manual` (592-612): auto caches only if last build took >1.0 s (610). Fallbacks: chat-hinted → global → unhinted (base_coder.py:724-745). RecursionError → map disabled (143-146).

EDIT STRATEGY (aider/coders/):
- Formats registered (__init__.py:19-33): diff (EditBlockCoder, SEARCH/REPLACE), diff-fenced, whole, udiff, udiff-simple, patch, architect (+editor-diff / editor-whole / editor-diff-fenced), ask/help/context. Chosen per model via `ModelSettings.edit_format` default "whole" (models.py:131) + model-settings.yml entries (e.g. gpt-4-turbo udiff yml:21-22, gemini-1.5-pro diff-fenced yml:528-529) + name heuristics (models.py:439-573); `--edit-format` overrides; copy-paste mode prefixes "editor-" (main.py:871-873).
- SEARCH/REPLACE matching cascade `replace_most_similar_chunk` (editblock_coder.py:157-188): exact (146) → exact-modulo-leading-whitespace (134-144, 243-294) → same after dropping spurious leading blank line (170-174) → `...` elision handling try_dotdotdots (190-241). FINDING: bare `return` at line 183 makes the fuzzy `replace_closest_edit_distance` (296-333, SequenceMatcher ≥0.8) UNREACHABLE — fuzzy matching is dead code; tests only cover whitespace variants (tests/basic/test_editblock.py:249-309, 29 tests).
- No-match: failed block tried against every other chat file first (56-60); then ValueError with per-block "SearchReplaceNoExactMatch" + "Did you mean…" similar lines (difflib ratio ≥0.6, 602-616) + "REPLACE lines already in file" hint + "other N blocks applied, don't re-send" (84-124). Unknown filename fuzzy-resolved with get_close_matches cutoff 0.8 (589).
- udiff: hunks normalized via difflib (250-258), dedup'd (69-83); `directly_apply_hunk` uses `flexible_search_and_replace` with preprocs {strip_blank_lines × relative_indent} (search_replace.py:528-538, 565-578; udiff_coder.py:201-207, 261-279), refuses repeated tiny context <10 chars (271-272); else splits hunk into context/change sections and applies partially (151-200). Errors: UnifiedDiffNoMatch / NotUnique texts (16-40) raised as ValueError (114-118).
- Retry loop: `apply_updates` catches ValueError → `num_malformed_responses += 1`, sets `reflected_message` (base_coder.py:2296-2316); `run` loops while reflected_message, `max_reflections = 3` (101, 932-943). After edits: auto_lint → lint_edited → confirm "Attempt to fix lint errors?" → reflect (1596-1606); auto_test → cmd_test → confirm → reflect (1616-1622). Same 3-reflection cap covers malformed edits, lint and test fixes combined.

BENCHMARK (benchmark/, Exercism-based README.md:10):
- Per-exercise loop `for i in range(tries)` (benchmark.py:848), `--tries default 2` (200); run coder → apply_updates → run_unit_tests subprocess with `timeout = 60*3` (981-982, 1027-1034); failure output appended to history and fed back as next instructions + prompts.test_failures "The tests are correct, don't try and change them" (896-906; prompts.py:10-16).
- Per-run JSON (results dict 922-955): tests_outcomes, cost, duration, test_timeouts, num_error_outputs, num_user_asks, num_exhausted_context_windows, num_malformed_responses, syntax_errors, indentation_errors (counted by scanning test output lines starting "SyntaxError"/"IndentationError", 886-887), lazy_comments (regex `^[+]? *[#].* [.][.][.] ` over the model response, 868), prompt/completion/thinking tokens, chat_hashes, editor_model/format.
- Aggregate (summarize_results 468-628): pass_rate_N = % of cases whose LAST outcome is True, credited to try index onward (503-511, 558-562); percent_cases_well_formed = 1 − cases-with-malformed/completed (587-588); seconds_per_case, total_cost, projected cost (611-623).
- Scorer self-test: ONLY test_benchmark.py (47 lines) tests `cleanup_test_output` (timing-string removal). No known-good/known-bad fixture proving pass/fail detection; correctness rests on subprocess returncode (1036-1049).
- README sample [EXTERNALLY_REPORTED]: "claude-3.5-sonnet … edit_format: diff … pass_rate_1: 57.1 / pass_rate_2: 77.4 / percent_cases_well_formed: 99.2 / test_cases: 225 / total_cost: 3.6346" (README.md:100-121); "The key statistics are the pass_rate_# entries" (125-126).

OUTPUT ECONOMY:
- No truncation of test/shell output anywhere: grep max_chars|truncat in io.py/commands.py/run_cmd.py/base_coder.py = 0 hits. `cmd_run` counts tokens and asks "Add N.Nk tokens of command output to the chat?"; test failures auto-added on nonzero exit (commands.py:1013-1052); LLM-suggested shell commands likewise confirm-then-append full output (base_coder.py:2434-2485).
- Benchmark feeds the model the FULL cleaned test stdout+stderr (1036-1049); only determinism scrubbing: strip "in 0.003s" timing and shorten testdir path (1051-1055).
- Lint feedback IS economized: `tree_context` shows only marked lines with `loi_pad=3` plus enclosing scopes, not the whole file (linter.py:112-115, 234-257).
- The repo map budget (binary search to ±15%) is the main context-economy mechanism (repomap.py:676-703); verbose prints "Repo-map: N k-tokens" (151-153).

LICENSE NOTE: Apache-2.0 → compatible with MIT downstream but NOT attribution-free: any copied code must keep the Apache license text + copyright notice, and modified files must carry a change notice (Apache §4); include a NOTICE/LICENSE-aider file. Ideas/algorithms are free to reimplement; verbatim/derivative code is not "just MIT".

BORROW CANDIDATES (ideas, not code):
1. PageRank-over-symbol-graph with chat/mention personalization + budget binary search (repomap.py:365-575, 667-703).
2. Edit-block failure feedback: "did you mean these actual lines" + "REPLACE already present" + "other N blocks applied, don't re-send" (editblock_coder.py:84-124).
3. Single reflection budget (max_reflections=3) shared across malformed-edit, lint, and test loops (base_coder.py:101, 932-943, 1596-1622).
4. Benchmark metrics beyond pass rate: lazy_comments regex, malformed-response count, syntax/indent errors, timeouts, per-try pass_rate_N (benchmark.py:868, 886-887, 922-955, 558-562).```
