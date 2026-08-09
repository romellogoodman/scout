---
date: 2026-08-09
tags: [decision, vocabulary, docs]
---

# Sorties become treks

Romello didn't like the military framing. Sortie, recon, kill criteria — the whole
aviation register. The replacement frame is camping and exploring, which turned out
to be a shorter walk than expected: scout, trap, flare, clear/blocked, and
empty-handed were already wilderness words, so most of the vocabulary crossed over
without being touched.

## The translation

| old | new |
|---|---|
| sortie | **trek** |
| recon | **survey** |
| fan-out | **search party** |
| survivor | *(retired — "a trek that clears" says it)* |
| dispatcher | *(retired — it's just "you")* |

Everything else stayed. "Search party" is arguably an upgrade on fan-out, not just a
reskin: several searchers comb the same ground independently and you compare where
their accounts diverge — that's the design argument for panel diversity compressed
into one term.

## The triage that shrank the change

The first draft of the rename had fourteen words. Romello's "do we need all these
words?" cut it to three, via a distinction worth keeping: the glossary was flattening
three different kinds of terms into one list. **Operational vocabulary** (bound to
flags, statuses, config keys — must be named), **narrative vocabulary** (coined once
inside a devlog entry to name a finding — defined where it's used, never needs a
glossary), and **tool names** (trapline, gamut — proper nouns for scripts, no more
"vocabulary" than ruff is). Only the first kind justifies a rename campaign. The rest
of the picked terms (keeper, basecamp, pack-out, turnaround criteria, set/spring)
either duplicated an existing word or live inside a single script, and applying them
would have *grown* the vocabulary the conversation started out trying to shrink.

Two words genuinely retired: survivor and dispatcher. Net glossary size went down.

## Where the seam sits, and why

Full coherence was never on the table: eight devlog entries and every archived
manifest say "sortie" permanently, because the record doesn't get rewritten. So the
choice was never "seam or no seam" — it was where the seam sits. The split we
applied (minimal-plus-one-tier):

**Renamed** — everything the user sees: README, CLAUDE.md, both skills, install.sh,
config comments, and scout.py's user-visible strings (help text, progress prints,
result lines, error messages). New flags `--survey` / `--search-party`, with
`--recon` / `--fanout` kept as working aliases so nothing installed breaks.

**Frozen** — everything the experiments see: code identifiers (`run_sortie`,
`run_recon`), the model-facing prompts ("You are a scout on a reconnaissance
sortie…" is a condition; the trapline preserves night-one wording byte-for-byte),
archive paths (`sorties/`, `fanout/`), manifest keys, the `recon-complete` status,
and the battery verdict strings. Renaming any of those either breaks comparability
with the archived record or is a silent condition change — the exact thing this log
exists to prevent.

CLAUDE.md now carries the two-line translation note so a future session doesn't
read the identifier/docs mismatch as drift and helpfully "fix" it.

## The one visible compromise

`scout --survey` prints `status=recon-complete` on success — new dialect on the
left, archive dialect on the right, in the same output line. That's the seam being
honest about where it sits. If it grates in practice, the fix is a display-layer
mapping in `main()` (print-time only, manifests untouched), which is cheap and
stays available.

## Open question

Does the docs↔code seam actually cost anything day to day? Observable: mistyped
flags, misread output, a future session confused despite the CLAUDE.md note. If
months of use never trip on it, the deep rename (identifiers, then forward-only
schema) stays unnecessary; if it trips people regularly, that's the data that
justifies tier three. Fittingly, this is measurable.
