# Dev log

Running narrative of building scout — what we believed, what we measured, and where
those two came apart.

Not ADRs. Decisions show up here, but so do surprises, dead ends, and numbers that
didn't match the guess. The point is to be able to reconstruct *why* something looked
reasonable at the time.

One file per entry, `YYYY-MM-DD-slug.md`. Newest first.

| Date | Entry | What it covers |
|------|-------|----------------|
| 2026-08-09 | [Build-anywhere, and the sandbox+uv hang](2026-08-09-build-anywhere-and-the-sandbox-uv-hang.md) | Build sorties take `--repo` (SCOUT_HOME split from target); bisecting a 6-min sandboxed-build hang to `uv`/`uvx` env-provisioning under sandbox-exec — the second Seatbelt+subprocess bite, and why a container is looking like the floor |
| 2026-08-09 | [The model was never the hard part](2026-08-09-the-model-was-never-the-hard-part.md) | Pivot to pi + OpenRouter; trap battery reranks the field (Kimi 3/3, DeepSeek 4/5, Muse 0/3); gamut proves no model sweeps and each fails differently; blinding was fake, built a real Seatbelt sandbox; sandboxed Muse fabricates anyway |
| 2026-08-09 | [Three experiments in the value regimes](2026-08-09-three-experiments.md) | Recon 4/4 on scoped questions (beat the grader once); fan-out 5/5 at ~2.5×, quality anti-correlated with effort; sunk-spec works but debt supply is the constraint; the v1 shape |
| 2026-08-09 | [The order beats the escape hatch](2026-08-09-the-order-beats-the-escape-hatch.md) | Blind replication: detection reliable, restraint isn't; #2b's refusal was the devlog's doing; authority gradient → stopping must be an action, not disobedience |
| 2026-08-09 | [The flare fired](2026-08-09-the-flare-fired.md) | Sortie #2b: one prompt line flips confabulation → honorable empty; detection clean, stop partially contaminated; parse-abort harness bug fixed; the testbed is self-aware now |
| 2026-08-08 | [The scout believed the bad test](2026-08-08-the-scout-believed-the-bad-test.md) | Sortie #2: contradictory test → confabulated requirement, shipped with a straight face; reports are advocacy; flare must be prompted |
| 2026-08-08 | [Sortie #1: clear](2026-08-08-sortie-1-clear.md) | First sortie lands: 7 rounds, 419s, merged unedited; inference is 99.9% of wall-clock; the scout read its own harness |
| 2026-08-08 | [Before the first sortie](2026-08-08-before-the-first-sortie.md) | The premise, cutting the plan down, the bad-test experiment, kill criteria |
