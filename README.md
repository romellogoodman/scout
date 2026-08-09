# scout

**Scout is a harness for disposable, verifiable delegation — the substrate a frontier
model orchestrates through, not the orchestrator.**

Hand a small, well-defined coding job to a cheap model, in a box where it can't do
harm and can't fake success. You give it one objective and one repository; it works
alone in a throwaway checkout; it only "passes" if a real gate (lint + tests) agrees;
you read the diff and decide whether to keep it.

Two properties make that safe:

- **It can't fake the check.** The harness runs the gate itself, not the model — so
  "tests pass" means they actually pass.
- **It can't touch what it shouldn't.** Treks run inside a macOS Seatbelt sandbox that
  denies reads of your other repos and secrets and confines writes to the worktree.

The model is a swappable part. Scouts run through [`pi`](https://pi.dev) against any
provider it supports — OpenRouter by default, a local model (Ollama/LM Studio) if you'd
rather. The durable asset isn't the model; it's the harness and the experiments in
`devlog/`.

## Setup

Requires `pi` on `PATH` and, for the default provider, an OpenRouter login
(`pi` → `/login openrouter`, or `OPENROUTER_API_KEY`). Cap your OpenRouter credits — a
scout can read its own key, and Seatbelt can't scope network egress to one host, so the
credit ceiling, not the sandbox, is the bound on both.

Config lives in `.scout/config.toml`:

```toml
[scout]
provider = "openrouter"                 # or "ollama" / "lmstudio" for local
model    = "moonshotai/kimi-k3"          # any model the provider serves
gate     = "uvx ruff check scout.py scoutlib tests && uv run pytest -q"
sandbox  = true                          # confine build treks with Seatbelt
# exclude = ["devlog"]                    # sparse-checkout paths out of the worktree
```

`./install.sh` puts a `scout` launcher on your PATH (so you can call it from any repo)
and installs a skill under `~/.claude/skills/scout/` that teaches an agent how to use it.
Pass `--symlink` to keep the skill live-linked to this repo instead of copied.

The **gate is yours to write and it is load-bearing** — a scout will faithfully satisfy
whatever you specify, including a bad spec. A missing gate is a hard error; scout refuses
to run without one.

## Use it

### Survey — ask about a codebase (read-only, safe)

```
python scout.py --survey "How does the server pick its listen port?" --repo ~/code/glass
```

Reads the target and answers in prose with file citations. This is the strongest use and
the front door. Two caveats from the testing: **name the scope** (pointed questions beat
"explain everything"), and **trust file paths over exact line numbers** — the line cites
are sometimes approximate. Read-only: no worktree, no gate, no writes.

### Build — make failing tests pass (writes code, gated, you review)

```
python scout.py "Make the failing tests in tests/test_timespan.py pass"      # this repo
python scout.py "Make tests/test_auth.py pass" --repo /path/to/other/repo     # any repo
```

The scout works in a git worktree, runs the gate, and keeps a `scout/<id>` branch (in the
target repo) only if the gate goes green. Then **you read the diff before merging** — this
is not optional. Models at this tier occasionally produce code that passes the gate but is
subtly wrong (narrowing an exception, special-casing a contradiction); the gate catches
*broken*, only your eyes catch *wrong*.

Building **another** repo requires that repo to have its own `.scout/config.toml` with a
`gate` — each repo defines what "passing" means. The trek's archive lands in scout's
central notebook; the branch lands in the target.

> **Sandbox note (macOS):** before a sandboxed build, scout pre-warms the gate's
> environment (runs it once, unsandboxed) so the scout *reuses* it rather than
> provisioning under the sandbox — provisioning a Python env inside `sandbox-exec` can
> intermittently deadlock (same family as search-party concurrency). If a sandboxed build ever
> hangs, kill and retry; `prewarm = false` disables the pre-warm, `sandbox = false` skips
> the sandbox for that repo. Surveys and search parties are unaffected.

### Search party — ask a panel of different models at once

```
python scout.py --search-party "How does the server pick its port?" --repo ~/code/glass
```

Runs the question against every model in the config `panel` and prints a JSON comparison
on stdout (plus a human digest on stderr). The panel is **deliberately heterogeneous** —
different models from different labs — because that's the only thing multiplicity uniquely
buys you: decorrelated blind spots. Ten copies of one model just agree with themselves.

Scouts run **sequentially by default** (`fanout_workers = 1`): the value here is model
diversity, not speed, and `sandbox-exec` deadlocks under concurrent tool-spawning on
macOS. Raise `fanout_workers` only with `sandbox = false`.

The output does **not** average the answers. It hands back each model's answer plus a
mechanical agreement proxy — which files each scout cited, and how much they overlap.
**Where the panel agrees, trust it; where it diverges, a blind spot is showing** and you
should read the reports. Synthesis is the caller's job; scout gives you the raw material
and flags the disagreement. Pass `--questions FILE` (one per line) to run several
questions across the panel at once (coverage + agreement in one shot).

## When to send a scout

All three must hold: the job is **small and clearly defined**, there's a **mechanical
check** for it (tests or a lint rule), and you're **willing to read the result**. If
you'd anxiously wait on the output, or you can't check it mechanically, don't send a
scout — coming back empty-handed is honorable, but so is not sending one out in the
first place.

## What you get back

Every trek is archived under `.scout-agent-notebook/sorties/<id>/`: the objective, the
model's report, the full session journal, the diff, the gate log, and a `manifest.json`
with status, timing, and token/cost usage. Treks that clear keep a `scout/<id>` branch;
the rest are torn down without ceremony. `index.jsonl` is the flat log of every run.

(Archive paths and manifest fields keep the project's original vocabulary — `sorties/`,
`recon-complete` — as do code identifiers and the model-facing prompts. Those are frozen
experimental surfaces, not drift; docs and CLI output speak trek/survey/search party.)

## Repo map

This is a working research harness, not a packaged product — and the repo reads
inverted from a normal project. Usually the library is the product and the tests defend
it; here **the harness is the product, and the "library" is evidence it works**.

- **`scout.py`** — the instrument. The whole harness, one file on purpose: surveys,
  builds, and search parties all launch from here.
- **`scoutlib/`** — the cargo. Modules built by scouts on past treks and merged only
  after they cleared the gate. Nothing in the harness imports them; they're proof,
  not infrastructure.
- **`tests/`** — the gate's teeth. `test_harness.py` covers the harness itself; the
  rest began life as specs handed to scouts ("make these pass") and stayed on as
  regression tests.
- **`tools/`** — the measurement rig: the model-evaluation batteries, the session
  auditor, and the Seatbelt profiles (`*.sb`). The fixtures in `tools/gamut/` are
  deliberately broken bait for the batteries — don't fix them.
- **`devlog/`** — the lab notebook, and half the point: what was measured, what
  failed, and why the design is what it is.
- **`install.sh`** + **`.claude/skills/`** — distribution: a `scout` launcher for
  your PATH and the skill that teaches an agent to use it.
- **`.scout/config.toml`** — provider, model, panel, gate. `.scout-agent-notebook/`
  (gitignored) accumulates every trek's full archive.
