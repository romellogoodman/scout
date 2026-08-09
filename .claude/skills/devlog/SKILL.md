---
name: devlog
description: Write or update the scout dev log at devlog/. Use after running treks, finishing a work session, making or reversing a design decision, or learning something from the numbers that contradicts what we expected. Also use when asked to log, write up, or record what happened. Check this before ending any session where something was built or measured.
---

# Dev log

The dev log is the narrative record of building scout. It exists so that months later
we can reconstruct why a decision looked reasonable at the time, and find the exact
point where a belief met a measurement and lost.

It is **not** an ADR set. Do not write "Context / Decision / Consequences." Write prose.

## When to write an entry

Write one when any of these happened:

- Treks ran and produced numbers — always log the numbers, especially bad ones
- A design decision was made, or an earlier one was reversed
- Something surprised us: a measurement that contradicted the guess, a failure mode we
  hadn't predicted, a cost that landed somewhere unexpected
- A direction changed, or a planned piece got cut
- A session ended with meaningful work in it

Do **not** write an entry for: routine edits, passing tests that were expected to pass,
refactors with no lesson attached, or restating something an existing entry covers. An
entry with nothing learned in it is noise, and it makes the log less trustworthy.

If a session produced nothing worth recording, say so to the user rather than padding
the log.

## Mechanics

1. **New file** at `devlog/YYYY-MM-DD-slug.md`. One entry per session by default;
   multiple per day is fine when they're genuinely separate threads. Extending the same
   day's entry is fine when the work is continuous — prefer that over two thin entries.

2. **Frontmatter**, minimal:
   ```yaml
   ---
   date: YYYY-MM-DD
   tags: [planning, treks, measurement, ...]
   ---
   ```

3. **Update the index** at `devlog/README.md` — add a row, newest first. One line, with
   a hook that says what's actually in the entry.

4. **Commit** the entry with the work it describes, or on its own if the work is already
   committed:
   ```
   devlog: <short description of the entry>
   ```
   Do not push unless asked.

## What a good entry has

No fixed template — shape it to what happened. But the entries worth keeping tend to
carry:

- **What we believed going in**, stated plainly enough to be judged wrong later
- **What actually happened**, including numbers, verbatim where they matter
- **Where those two diverged**, and what it implies for the design
- **Open questions** — the things we still can't tell apart

Record the numbers even when they kill an idea. Especially then. The log's value is
proportional to how honest it is about the misses, and an entry that only records wins
is worse than no entry.

## Voice

First person, plain, specific. Name the mechanism rather than gesturing at it. Credit
ideas to whoever had them — if Romello proposed something, say so. Hedge only where
there's real uncertainty, and when hedging, say what would resolve it.

Avoid: summarizing what the code does (the code does that), restating the plan without
new information, and retrospective confidence about things that were actually guesses.

## Standing measurements

Trek entries should carry these four, since they're the ones v0 exists to answer:

- gate-clear rate
- time split: setup / inference / gate / teardown
- merge rate among clears — of the diffs that passed, how many were taken unedited
- dominant failure mode: looping, plausible-but-wrong, or refusal to finish
