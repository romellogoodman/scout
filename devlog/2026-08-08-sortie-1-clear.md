---
date: 2026-08-08
tags: [sorties, measurement, harness]
---

# Sortie #1: clear

The first sortie ran tonight and came back clear. A local 27B wrote the first
scout-built code to land on main, and the numbers are already interesting — one of
our top-of-list worries inverted on contact.

## Setup

Harness went from zero to dispatch in one session: `scout.py` (one file — worktree,
`.act()` loop, gate, archive, teardown), `.scout/config.toml` with `uv run pytest -q`
as the gate, five baseline harness tests green, and `tests/test_slugify.py` planted
red. Objective handed to the scout, verbatim:

> Make the failing tests in tests/test_slugify.py pass.

Model: `qwen/qwen3.6-27b` (MLX 4bit), 32k context, loaded in 13.2s at 15GB. Four
tools: `list_files`, `read_file`, `write_file`, `bash`.

## The numbers

| measurement | value |
|---|---|
| status | **clear** (gate-passed), merged unedited |
| rounds | 7 of a 24 cap |
| setup / inference / gate / teardown | 0.04s / **419.24s** / 0.21s / 0.13s |
| diff | 2 files, +43/−0 |
| gate-clear rate so far | 1/1 |
| merge rate among survivors | 1/1 |

The sortie arc was clean: list files → read the failing tests → read `scout.py` and
`pyproject.toml` for context → write `scoutlib/slugify.py` + `__init__.py` in one
shot → run the gate (6/6) → run the *full* suite unprompted (11/11) → report. No
looping, no flailing, no wasted rounds. The implementation is correct NFD-normalize
diacritic stripping, word-boundary truncation, fallback — with a docstring. I took it
without edits. One nit I noticed and didn't block on: the truncation is
over-conservative when the cut lands exactly at a word end. Tests don't cover it,
behavior is safe (never cuts mid-word).

## What the numbers say

**Inference is 99.9% of wall-clock.** 419s of a 420s sortie. The worry going in was
that worktree + gate cold-start would dominate; on this repo it's noise — worktree
add is 0.04s and the harness's gate run was 0.21s. Two caveats before generalizing:
the scout pre-warmed the worktree venv by running the gate itself mid-loop (so
uv's cold sync cost is buried in inference time, where we don't mind it), and this
repo's dependency tree is tiny. The `node_modules` version of this worry is untested
and stays on the list. But the v0 lesson is the reverse of the guess: **the cost to
optimize is rounds, not infrastructure.** ~60s per round at 27B scale means every
round the prompt can shave is a minute off the sortie.

**The scout read its own harness.** Round 2, it opened `scout.py` — the report says
`crude_slug` "gave a good starting pattern." Scout-builds-scout is literal: the
worktree contains the harness, the devlog, all of it. Mostly charming, but it's a
real confound for the upcoming bad-test experiment — the devlog describes that
experiment in detail, and a scout that reads `devlog/` before touching the planted
test is contaminated. Sortie #2's setup needs to account for this: keep the bad test
free of tells, and check the journal afterward for whether it looked.

**Model behavior notes.** qwen3.6 thinks hard (60s/round is mostly reasoning, and it
reasons in a leaked-`</think>` dialect that the SDK doesn't fully strip — harness now
extracts text parts properly and strips the stray tag for `report.md`). It also ran
the whole suite after its target tests passed, unprompted. That's the right instinct
and nobody asked for it.

## Against the kill criteria

≥40% clear, ≥70% of clearers mergeable. Running total: 100% / 100%, n=1. Means
nothing yet — this was the easiest task in the queue, chosen to be. The bad test is
next, and it's designed to produce a worse number somewhere.

## Queue adjustments

1. Sortie #2 stays the bad test, with the contamination check above.
2. The report-extraction fix went in by hand rather than by sortie — it was a
   ten-line harness patch discovered mid-review. Driver fixes harness, scouts build
   scoutlib. That division held naturally tonight; worth keeping deliberate.
