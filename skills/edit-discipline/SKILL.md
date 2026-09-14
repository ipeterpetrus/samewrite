---
name: edit-discipline
description: Compatibility alias kept for 1.0.0 installs — the edit rule and everything around it now live in the samewrite skill.
disable-model-invocation: true
---

# edit-discipline → samewrite

Deprecated alias, kept so a 1.0.0 install and `/edit-discipline` keep working. Not listed to
the model (it costs nothing per turn); the canonical policy is `samewrite` — invoke that.

The rule this skill used to carry, unchanged: overwriting an existing file that is
**byte-identical** → do not write; **under ~25%** of the file changes → anchored Edit;
**over ~40%** → full rewrite and say why. Measured on 1,316 Claude Code transcripts
(741 overwrites, 20.8% identical); method and retractions in `docs/FINDINGS.md`.
