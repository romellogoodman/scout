---
date: 2026-08-09
tags: [build, cross-repo, sandbox, seatbelt, uv, failure-modes, bisection]
---

# Build-anywhere, and the sandbox+uv hang

Two things this session: build sorties can now target any repo, not just scout's own;
and getting there surfaced a second macOS-sandbox failure mode that's worth naming
because it's the same family as the fan-out deadlock.

## What we believed / wanted

Build was repo-locked. `run_sortie` resolved `repo_root = Path(__file__).parent`, so a
build sortie could only ever operate on scout's own checkout. Recon and fan-out already
took `--repo` and read any repo; build didn't. For the vision Romello keeps pointing at —
a frontier model orchestrating scouts to do real work across the repos it's actually
touching — build-in-scout's-own-repo is nearly useless. The scoped, delegatable unit has
to land where the work is.

## What build-anywhere took

The fix was untangling two things `scout.py` had conflated under one name. There's
**where scout lives** — the sandbox profiles in `tools/`, the central notebook — and
there's **the repo a sortie operates on**. Both were `repo_root`. Split them: a module
constant `SCOUT_HOME = Path(__file__).parent` for the former, and `run_sortie(objective,
repo, cfg)` where `repo` is the target for the latter. The worktree and the survivor
`scout/<id>` branch land in the target repo; the archive stays central in `SCOUT_HOME`.

One real decision inside that: whose config? Recon/fan-out keep using scout's own config
(your models, your panel — no gate needed to read). Build loads the *target* repo's
`.scout/config.toml`, because the gate has to match that repo — only the target knows
what "passing" means for itself. So building another repo requires that repo to carry a
`.scout/config.toml` with a gate. That's consistent with scout's founding stance (no
gate, no build), just applied per-target.

It works. An external throwaway repo built clean: **8s non-sandboxed** (deepseek, 7.5K
tokens, $0.0006), `thing.py` created on a `scout/<id>` branch in the target, archive in
scout's notebook.

## The hang

The *sandboxed* external build hung. First run: 6m40s, killed. Empty session, no file
created. This is the failure mode the whole project exists to distrust — a silent hang
reads like progress until you look. So I bisected it instead of shrugging.

What I ruled out, one at a time, each with a real test:

- Two concurrent `pi` processes — fine (this was the earlier fan-out diagnostic, but
  worth re-confirming). Not raw concurrency.
- Build profile + `pi`, trivial prompt — **2s, fine.** Not the parameterized profile.
- `pi` with cwd = a git worktree whose gitdir sits under the denied `REPO` — **1s,
  fine.** Not the worktree/gitdir.
- The `~/.pi/agent/sessions` read-deny (build profile has it, recon doesn't) — removed
  it, **still hung.** Not that.
- Re-allowing `REPO/.git` in the profile — **still hung.** Not the gitdir after all.
- Build profile + `--session-dir` + trivial prompt — **2s, fine.** Not the session.

Every component worked in isolation; only a *real objective* hung. The discriminator that
cracked it: I swapped the target's gate from `uvx pytest -q` to `grep -q 'def add'
thing.py` — a check that provisions no environment. **It built in 16s.** Put the
`uvx`/`uv` gate back, it hangs.

## The mechanism

The scout, verifying its own work, runs the gate via its bash tool *inside the sandbox*.
When that gate provisions a Python environment on the fly — `uvx pytest` resolving a tool
env, or `uv run` creating a project venv in a fresh checkout — it hangs under
`sandbox-exec`. Lock files, venv materialization (clonefile), subprocess fan — the
lock-heavy, subprocess-heavy work is what Seatbelt chokes on.

Scout's *own* sandboxed builds never hit this, which is why I hadn't seen it: scout's
gate is `uvx ruff check && uv run pytest`, and both reuse *already-built* environments
(the ruff tool is cached; `uv run` uses scout's committed `uv.lock` venv). No provisioning
under the sandbox, no hang. The external target had no venv, so its first `uv` invocation
tried to build one — under the sandbox — and stalled.

Note the tell in the wreckage: the hung run left an **empty session**. pi flushes its
journal on clean exit, so a killed pi looks like it did nothing even when it hung
mid-work. I spent a while reading "empty session" as "hung at startup," which was wrong —
it hung deep in a tool call. Worth remembering next time: an empty session under a hang
is evidence of *nothing*, not evidence of an early failure.

## The pattern I want on record

This is the **second** time `sandbox-exec` bit us on the same seam. The first was
fan-out: two concurrent sandboxed scouts spawning tool subprocesses deadlocked. This is:
one sandboxed scout spawning `uv` deadlocks. Both are Seatbelt + lock/subprocess-heavy
tooling. The through-line: **Seatbelt is reliable for the scout's own file I/O — read,
write, grep, run a cached tool — and flaky the moment the sandboxed process becomes a
process manager itself** (concurrency, env provisioning, lock contention).

We chose Seatbelt because it was already on the machine and needed no daemon. That was
the right call to ship. But we're now two-for-two on it having a lower ceiling than hoped,
and both limits are things a real container (Linux namespaces, a clean filesystem, its own
package cache) simply wouldn't have. The container we deferred for lack of Docker is
looking less like a nicety and more like the eventual floor.

## What shipped

Build-anywhere, plus the limitation told plainly rather than hidden (README + the scout
skill): sandboxed builds are reliable when the gate runs in a pre-built environment; a
gate that provisions an env on the fly can hang under the macOS sandbox — pre-build that
repo's env, or set `sandbox = false` for it. Recon, fan-out, and builds against
pre-built envs are unaffected. The honest shape of the feature is: fully working
non-sandboxed; fully working sandboxed against pre-built-env gates; one documented
sandbox hole on macOS.

## Open questions

- Is the fix to the sandbox hole a container, or is there a Seatbelt profile that lets
  `uv` provision without hanging? I didn't chase the exact syscall (clonefile? a flock?)
  — the bisection got me to the class, not the line. A container sidesteps the whole
  question and fixes fan-out concurrency too, which is the tell that it's the right floor.
- Could the harness pre-warm the target's env (run the gate once, unsandboxed, to
  materialize the venv) before the sandboxed sortie, so the scout's in-sandbox `uv run`
  reuses it? Cheap to try, might convert the hole into a non-issue for uv-based gates
  without a container. Untested.
