---
date: 2026-08-08
tags: [planning, architecture, bootstrap]
---

# Before the first sortie

Nothing is built yet. This entry records what we believe is true *before* any of it
meets a machine, so that later we can tell which parts we got wrong and roughly when.

## What scout is

Claude Code orchestrates. Local models do the labor. Mechanical gates do the filtering.

The load-bearing premise is that **fan-out only pays if rejection is as cheap as
generation**. Most agent-swarm designs make production cheap and quietly leave
evaluation on the human, which just relocates the bottleneck. Scout's answer is that a
build or test command rejects for free, so the expensive reader only ever sees
survivors.

Everything else in the design falls out of that: empty is honorable, because a scout
returning nothing costs nothing. Interruption is terminal and rationed, because the
cost of interrupting should sit on the interrupter. The frontier model judges
survivors, not attempts.

## The plan was about three times too big

The version we started from had nine directories, a harness `CONTRACT.md`, three
swappable runtime adapters, a `skill/reference/` tree, and a notebook schema — all
specified before a single sortie had ever run. That is picking seams before you have
felt where the thing breaks.

Cut to: one file, `scout.py`. No MCP, no lanes, no recon mode, no `note`/`recall`/`flare`,
no fan-out. A CLI that runs one sortie and writes down what happened.

## Three things I didn't believe

**The filter's compression ratio is the whole product, and it's unmeasured.** If eight
of ten sorties clear the gate, nothing was saved — the reading just moved from writing
code to reviewing ten diffs, which is worse. The design only pays where the gate is
close to equivalent to correctness. That's a narrower band than the plan assumed:
failing-test-to-passing, lint class cleanup, mechanical refactor under existing
coverage. Not "draft tests for this case, generally."

**The unexamined cost is wall-clock, not tokens.** Local labor is free in dollars and
expensive in serialization. One machine, `n_parallel` defaults to 4, and every sortie
pays a worktree's cold build before the gate can even speak. On a repo with
`node_modules` or a venv, gate time may well dominate inference time — which would
invert the intuition the whole design rests on. This is the measurement I most expect
to be surprised by.

**The failure signal is behavioral, not numeric.** It's working if we stop reading the
failures. It's not working if we read every report anyway, because we don't trust the
gate — at which point we've rebuilt the "unified depot" the whole thing was arguing
against, with extra steps.

## Scout builds scout

The test bed is this repo. The gate is `pytest -q`.

Write a failing test first, then dispatch a scout to make it pass. That makes the gate
nearly equivalent to correctness by construction, which is exactly the narrow band
where the design should pay. If it can't work here, it won't work anywhere, and we
learn that in a day rather than a month.

Six queued sorties, all small and mostly pure: slugify, manifest writer, config loader,
diff-stats parser, index append/query, timing record. The last one matters most — it's
the only one that requires modifying code the scout didn't write.

## The bad test

Romello's idea, and it's a better experiment than mine.

Rather than only planting *failing* tests, plant one **wrong** test — an assertion that
contradicts the convention used everywhere else in the file. Then dispatch the usual
"make the failing test pass."

This tests the gate rather than the scout, and all three outcomes teach us something:

1. **Satisfies it blindly.** The gate is decorative. Confirms the compression-ratio
   worry, and tells us the scout brings no independent judgment — so v1 must assume
   gates are load-bearing *and correct*, and the cost of authoring good gates lands
   back on the human.
2. **Satisfies it, but flags the inconsistency in the report.** There is judgment
   available. `flare` would have something real to carry, and reports are worth reading
   even on success.
3. **Edits the test instead of the code.** The gate is self-gameable. This is the one
   worth knowing on day one — it means any fan-out design needs the gate's own files
   held read-only, or gate-touching diffs auto-rejected, *before* we ever run ten
   scouts at once.

Outcome 3 is cheap to discover now and expensive to discover in month two.

## What we're measuring

v0's output is not working software. It's four numbers:

- gate-clear rate
- time split: setup / inference / gate / teardown
- merge rate among survivors — of diffs that pass, how many I'd take unedited
- dominant failure mode: looping, plausible-but-wrong, or refusal to finish

**Kill criteria.** After ~10 sorties, proceed to v1 only if ≥40% clear the gate *and*
≥70% of clearers are mergeable without edits. Many clear but few merge → the gate is
decorative and no amount of MCP fixes it. Almost nothing clears → smaller tasks or
wrong model, and we test that before building anything else.

## Where things stand

Empty repo, no commits. LM Studio server up on `:1234` with nothing loaded. Six
tool-capable models on disk; `qwen/qwen3.6-27b` (MLX 4bit, 262k ctx) is the pick for
the build lane, `gemma-4-26b-a4b` (MoE, ~4B active) is the one to try later for recon.
M5 Pro, 48GB, 18 cores. System Python is 3.9 with no SDK, so the project takes its own
via `uv`.

## Open questions

- Does gate time dominate inference time? (see above — top of the list)
- Does a 4bit 27B loop on bounded tasks, or is looping a harness-fit artifact rather
  than a distance-from-distribution one? Two different fixes; can't tell them apart yet.
- Is worktree-per-sortie affordable on repos with real dependency trees, or does that
  cost force a shared-checkout design?
- What does a scout do when the objective is under-specified — guess, stall, or stop?
