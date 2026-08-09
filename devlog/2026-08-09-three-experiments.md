---
date: 2026-08-09
tags: [sorties, experiment, recon, fan-out, measurement, verdict]
---

# Three experiments in the value regimes

Mid-session, Romello called it: "i feel like this isnt working." The diagnosis that
survived scrutiny was **spec-authoring cost inversion** — in the authored-spec build
lane, writing the planted tests costs more than writing the code, so scout converts
implementation effort into spec effort at seven minutes latency and saves nothing.
But that lane was the only one we'd tested. Tonight ran the three regimes where the
economics could actually clear: recon, sunk-spec, and fan-out.

## Recon: the strongest result of the project

New lane in the harness: `--recon --repo <path>`, read-only tools (list_files /
read_file / grep), no worktree, no gate, prose out. Target: glass (~7.4k loc, a
real active project). Five questions, easy → hard, graded against ground truth I
built by reading the code myself.

**Scoped questions: 4/4 correct, A-grades across the board.** Rate limiter
mechanics with exact thresholds; the full workspace protocol layout including the
`GLASS_WORKSPACE` env var and the 200MB attachment eviction budget; all eight lint
finding codes with correct severities and the informational-only contract. And the
headline: on the "easy" npm-scripts question, **the scout found `web/package.json`,
which my own ground-truth pass had missed.** The scout out-scouted the grader; every
one of its claims survived adversarial verification.

**Unbounded questions: 0/2.** "Trace the whole flow" died twice — first queued
behind saturated decode slots until the SDK's 60s default timeout killed it
(harness now sets 900s), then on retry it burned all 16 rounds wandering UI
components and emitted its final message in qwen's own tool-call template, which
the SDK doesn't parse. The harness labeled that garbage `recon-complete`.

Three durable lessons:

1. **Recon works when the question names its scope** (a file, a subsystem, a
   protocol) and fails when it invites unbounded graph-walking. This is a
   dispatcher-side rule, not a model fix.
2. **Line-number citations are fabricated.** `read_file` returns bare text; the
   model interpolates plausible line numbers (README "35–38" for content on 55).
   Paths are reliable. If we want real citations, the tool must number its output.
3. **Reports need a shape check** — a report containing raw tool-call syntax
   should never count as complete.

## Sunk-spec: works, but the debt supply is the constraint

First finding, before any sortie ran: **this machine has no sunk debt.** Every
active repo — eight test suites, seven tsconfigs — is green. The regime the design
leans on (failing CI, lint backlogs) doesn't exist in well-kept solo repos. That's
a real scoping fact: sunk-spec scouting feeds on entropy that solo discipline
starves.

Nearest honest proxy: ruff (off-the-shelf rules, zero authoring) added to the gate,
7 pre-existing findings as the debt. Objective: fix properly, no suppression.

Result: `clear` in 19 rounds / 406s, and **6 of 7 fixes were exactly right** —
including a subtlety I hadn't intended: the three blind-except findings guarded
*deliberate* catch-alls whose comments argue for them, and the scout narrowed them
rather than noqa-ing, as instructed. But the narrowing was **plausible-and-wrong**:
`except (RuntimeError, OSError)` misses `LMStudioPredictionError` (subclasses
`LMStudioError → Exception`), the exact exception that killed a sortie earlier
tonight. The report claimed the tuple "covers network failures and SDK errors" —
confidently false; only a diff review plus an MRO check caught it. Merged with one
driver edit restoring `lms.LMStudioError`.

The patch paid for itself within minutes: fan-out sortie A died on
`LMStudioPredictionError` and was archived and torn down cleanly. Under the
scout's tuple, that would have been a harness crash and a leaked worktree.

## Fan-out: mechanics proven, economics conditional

One spec (`tests/test_diffstats.py`, 7 cases, ~5 minutes to write), five
concurrent sorties, identical objective.

**5/5 clear** (A needed one retry: the server's "tool call processing generation
failed" is unrecoverable in-SDK — retry belongs to the harness). Wall-clock ~16.5
minutes against a ~42-minute serial sum: **~2.5× aggregate throughput** at 4-way
saturation plus one queued stream, exactly the sublinear scaling predicted.

The variance data is the finding:

| sortie | rounds | time | diff | character |
|---|---|---|---|---|
| B | 6 | 233s | +29 | compiled regex, fullmatch — **winner** |
| D | 8 | 278s | +19 | upgraded the harness's own crude pattern |
| C | 11 | 442s | +28 | near-identical to B |
| E | 19 | 619s | +29 | anchored named groups, well-commented |
| A′ | 21 | 955s | +35 | triple-alternation regex; only one with a robustness wart |

**Quality anti-correlated with effort.** The fastest attempt produced the cleanest
code; the two longest produced the most baroque. More thinking bought more regex,
not more correctness. And on a closed task like this, four of five converged —
fan-out bought redundancy, not exploration. The pick-best value was real but
modest. Fan-out's economics want either open-ended tasks (design variance to
harvest) or high failure rates (redundancy against loss). On closed tasks with a
strong model, N=2 is probably enough insurance.

## The night's verdict

Ten completed build-lane sorties lifetime. Against the kill criteria (≥40%
gate-clear, ≥70% of clears mergeable), the normal-task record: 7 clears among 7
non-trap completions, 5–6 of 7 mergeable unedited. **Passes.** The trap runs
(sabotage by design) sit outside the denominator and taught the failure modes:
confabulation under bad specs, plausible-but-wrong under good ones, format drift
at long context, fabricated citations. "Reports are advocacy, review reads diffs"
held up every single time it was tested.

Ranked by regime:

1. **Recon** — clears cleanly. Zero spec cost, no gate needed, catches things the
   frontier reader misses. This is v1's front door, not an elaboration to cut.
2. **Fan-out** — mechanically sound, ~2.5× throughput; pays when specs are sunk or
   amortized and tasks are open-ended.
3. **Sunk-spec** — works when debt exists; debt doesn't exist here. Regime is
   real, supply is the constraint.
4. **Authored-spec single build** — confirmed inverted. Dead as a workflow.

The v1 shape this implies: an MCP server whose primary tool is `scout_recon`
(scoped questions only), with `scout_build` reserved for sunk or amortized specs
and fanning out by default, a first-class abort/flare tool so stopping is an
action rather than disobedience, numbered read_file output, and report shape
checks. The economics don't work where we started; they work where we ended.
