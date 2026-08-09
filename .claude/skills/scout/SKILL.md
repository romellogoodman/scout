---
name: scout
description: Delegate a bounded, verifiable coding task or codebase question to a scout — a cheap model running isolated in a sandbox behind a mechanical gate. Use to read an unfamiliar codebase without spending your own context (recon), make failing tests pass in a throwaway worktree (build), or ask one question across a diverse panel of models and compare how they answer (fan-out). Reach for it when you want to hand off scoped work whose result you can check rather than trust.
---

# Using scout

Scout is a harness for disposable, verifiable delegation — the substrate you orchestrate
through, not the orchestrator. **You are the orchestrator.** Scout hands you isolated,
gated, throwaway workers; you decide what to dispatch, read what comes back, and
synthesize. It never decides for you.

The rule that governs everything: **the report is advocacy; the diff and the gate are
truth.** Never take a scout's word for its work — read what it actually did.

Invoke via the `scout` command (installed on PATH by `install.sh`). If it isn't on PATH,
run from the scout repo instead: `uv run python scout.py …`. Every run is archived under
the scout repo's `.scout-agent-notebook/`.

## Recon — ask about a codebase (read-only, any repo)

```
scout --recon "How does the server pick its listen port?" --repo /path/to/repo
```

Returns a prose answer with file citations. Use it to understand code *without* loading
files into your own context. Trust the file paths; treat exact line numbers as
approximate — reopen the file yourself if a claim is load-bearing. An "I couldn't find
it" answer is honest, not a failure.

## Build — make failing tests pass (writes code, gated)

```
scout "Make the failing tests in tests/test_foo.py pass"                 # scout's own repo
scout "Make tests/test_auth.py pass" --repo /path/to/repo                # any repo
```

The scout works in a throwaway git worktree, runs the gate (lint + tests), and keeps a
`scout/<id>` branch (in the target repo) only if the gate passed. **Then you read the
diff** (`git -C <repo> diff main..scout/<id>`) before trusting or merging — a change can
clear the gate and still be subtly wrong (narrowing an exception, special-casing a
contradiction). The gate catches *broken*; only your reading catches *wrong*.

Building another repo requires that repo to carry its own `.scout/config.toml` with a
`gate`. macOS sandbox caveat: sandboxed builds can hang when the gate provisions a Python
env on the fly (`uvx`/`uv run` in a fresh checkout); pre-build that repo's env or set
`sandbox = false` for it. Recon/fan-out are unaffected.

## Fan-out — ask a panel of different models at once

```
scout --fanout "How does auth work here?" --repo /path/to/repo
scout --fanout --questions questions.txt --repo /path/to/repo
```

Runs the question across a heterogeneous panel (different models, different labs) and
prints a JSON comparison on stdout plus a digest on stderr. **Read all of the answers.**
The value is diversity: where the panel agrees (high citation overlap) you can trust
more; where it diverges is where a blind spot is showing — read those closely. Do **not**
average the answers and do **not** pick one mechanically. Synthesize from having seen the
whole space; divergence is the signal, not noise.

## When to send a scout

All three must hold: the task is **small and well-defined**, there's a **way to check the
result** (a gate, or citations you can verify), and you'd **actually read what comes
back**. If you can't check it or wouldn't read it, do it yourself.

## Where the output lives

Each sortie: `.scout-agent-notebook/sorties/<id>/` — report, journal, diff, gate log, and
a `manifest.json` with status, timing, and token cost. Fan-out summaries:
`.scout-agent-notebook/fanout/`. Config is `.scout/config.toml` (`provider`, `model`,
`panel`, `gate`, `sandbox`). The gate is load-bearing and yours to write — a scout
faithfully satisfies whatever spec you give it, including a bad one.
