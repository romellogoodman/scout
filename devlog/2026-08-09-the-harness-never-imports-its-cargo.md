---
date: 2026-08-09
tags: [architecture, decision, cleanup]
---

# The harness never imports its cargo

No sorties tonight. This session was a cleanup pass that backed into an architecture
decision — and reversed a plan that had been sitting in scout.py's header since night
one.

## The cleanup, briefly

Romello asked for a desplopify sweep. The finding worth recording: the slop was almost
entirely in the code the sorties wrote, not the code we wrote. `scoutlib/slugify.py`
had a docstring restating its implementation as six bullets and a comment narrating
every line (`# Lowercase` above `.lower()`); the hand-written harness had none of
that. Net −44 lines, gate green throughout, and the model-facing strings (prompts,
tool docstrings) verified byte-identical against HEAD before and after — those are
experimental conditions, not prose.

The sweep also surfaced the thing this entry is actually about.

## What we believed going in

scout.py's header has said since the start: "Anything here marked 'crude' is a
placeholder a sortie is queued to replace." Sorties #1 and #4 delivered the
replacements — `scoutlib.slugify` and `scoutlib.diffstats`, both gate-passing, both
tested. The swap never happened. `crude_slug` and `crude_diff_stats` still run every
sortie. For months of log-time that read as unfinished migration.

## The reversal

When Romello asked whether to rearchitect the repo to make its structure clearer, the
framing that fell out was: the harness is the instrument, `scoutlib/` is the cargo it
brought back — evidence the loop works, not infrastructure. And that framing predicts
the "unfinished" state exactly. So we're keeping it, on purpose now:

**scout.py never imports scoutlib.** Three reasons, in order of weight:

1. **Trust boundary.** The whole design rests on not trusting sortie output — the
   harness re-runs the gate because reports are advocacy. Importing sortie-built code
   into the machinery that judges sorties would blur the one clean line the project
   has. The gate protects against *broken*; only reading protects against *wrong*;
   and the harness is the thing doing the reading. It shouldn't stand on cargo.
2. **Behavior stability.** Sortie IDs and branch names come from `crude_slug`.
   Swapping in the real slugify changes them (diacritic stripping, word-boundary
   truncation) for zero capability gained.
3. **The cargo's value is as evidence.** Wiring it in adds nothing the harness needs
   — it needs *a* branch name, not a good one — and would spend the proof to buy
   nothing.

Honestly stated: this is a reversal dressed as a principle. The original plan was to
swap them in; the header said so. What makes it a decision rather than a
rationalization is that the boundary was already being enforced by every other part
of the design — we just hadn't noticed it applied here too. If a sortie someday
builds something the harness genuinely needs, the rule says it gets promoted
deliberately — read, reviewed, rewritten into the harness by hand — not imported.

## Rearchitecting: rejected

Same session, same question, opposite-looking answer with the same root. The layout
(`scout.py` / `scoutlib/` / `tests/`) stays generic and boring because:

- **The genericness is blinding.** Sorties work in copies of this repo with devlog,
  tools, and the notebook excluded. What remains looks like an ordinary Python
  project, which is what a subject should see. A narrative layout would leak the
  experiment to the scout standing in it.
- **The paths are frozen conditions.** The trap arms `tests/test_slugify.py`
  byte-for-byte; the gamut plants fixtures at `scoutlib/textstats.py`; the gate
  string hardcodes the directory names in config, both batteries, and every archived
  sortie prompt. Moving directories invalidates the baselines already in this log.

The clarity problem was conceptual, so it got solved with words: the README's Status
section became a repo map that states the inversion (harness is the product, the
"library" is evidence), the sandbox residuals moved into Setup next to the credit-cap
warning they half-duplicated, and `scoutlib/__init__.py` now carries a two-line
docstring saying what the package is, placed exactly where the confusion starts.

## Open questions

- The rule's pressure test hasn't arrived yet: if `crude_slug` ever causes a real
  failure — a slug collision, a garbage branch name from a unicode objective — do we
  fix the crude one in place, or does the boundary bend? Betting on fix-in-place, but
  that's a guess until it happens.
- ~~Whether the no-import rule should be enforced mechanically or left as
  documentation.~~ Resolved same session: Romello opted to enforce it.
  `test_the_harness_never_imports_its_cargo` (tests/test_harness.py) walks
  scout.py's AST and fails on any scoutlib import — verified against a planted
  violation before landing. The boundary now survives a future session that
  doesn't read this entry, because the gate reads it for them.
