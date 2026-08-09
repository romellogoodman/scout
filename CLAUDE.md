# scout

Scout is a harness for disposable, verifiable delegation — the substrate a frontier
model orchestrates through, not the orchestrator. It sends out one-shot AI coding
**treks**: one objective, one throwaway git worktree, one mechanical gate (lint +
tests), archived and torn down. Treks that clear keep a branch; a human reads the
diff and decides. `README.md` is the user-facing usage; `devlog/README.md` is the
running narrative of *why* the design is what it is.

Vocabulary: docs and CLI output say **trek** (one run), **survey** (read-only),
**search party** (panel). Code identifiers, archive paths, and the model-facing
prompts keep the original sortie/recon/fanout terms — frozen experimental surfaces,
not drift. Old devlog entries keep the old words; they're the record.

## Stack & layout

- **`scout.py`** — the whole harness, one file on purpose. CLI in `main()`; build treks
  in `run_sortie`, read-only surveys in `run_recon`, the pi backend in `run_pi_agent`.
- **`scoutlib/`** — real modules, each built *by* a scout on a trek, not hand-written.
- **`tools/`** — model-evaluation batteries and the Seatbelt sandbox profiles (`*.sb`);
  each script documents itself in its header comment.
- **`.scout/config.toml`** — provider, model, gate, sandbox. `.scout-agent-notebook/`
  (gitignored) holds every trek's full archive.

Python 3.12+ (uses `tomllib`). Inference runs through the [`pi`](https://pi.dev) CLI
against OpenRouter by default; the model is a swappable config value, never hardcoded.

## Verify any change

```
uvx ruff check scout.py scoutlib tests && uv run pytest -q
```

That is the gate. Use `uv run` (not bare `python`) — the harness needs the project's
3.12+ interpreter. Ruff owns formatting; don't hand-police style.

## What shapes decisions here

- **The gate is the only proof.** The harness re-runs it regardless of what a scout
  claims — a change is done when the gate passes, not when a report says so.
- **Reports are advocacy; read the diff.** Models produce plausible-and-wrong changes
  that clear the gate (see `devlog/`). Never merge on a report alone.
- **Empty is honorable.** Refusing a bad or contradictory spec is a correct outcome.
- **The model is a part, not the point.** Swap it in `.scout/config.toml`; the durable
  assets are the harness and the experiments in `devlog/`.

## After doing work

Write a devlog entry when treks ran, a decision was made or reversed, or a measurement
surprised you — numbers included, the misses especially. Use the `devlog` skill;
conventions are in `devlog/README.md`. Skip it for routine edits with nothing learned.
