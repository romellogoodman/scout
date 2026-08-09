#!/usr/bin/env python3
"""scout v0 — dispatch one sortie: worktree, act loop, gate, archive, teardown.

One file on purpose. The pieces that deserve to be real modules get built *by
sorties* (see devlog/2026-08-08-before-the-first-sortie.md) and land in scoutlib/.
Anything here marked "crude" is a placeholder a sortie is queued to replace.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

CONFIG_PATH = ".scout/config.toml"
NOTEBOOK = ".scout-agent-notebook"
WORKTREES = ".scout-worktrees"
TOOL_OUTPUT_CAP = 8000

RECON_PROMPT = """\
You are a scout on a reconnaissance sortie: answer a question about the
repository you are standing in. You have read-only tools: list_files,
read_file, and grep. All paths are relative to the repository root.

Rules:
- Answer only from what you actually read in this repository. If you cannot
  find the answer, say so plainly — a wrong answer is worse than no answer.
- Cite file paths (with line numbers where useful) for every claim.
- Finish with a concise prose answer to the question. No code changes, no
  diffs, no speculation beyond what the files support.
"""

SYSTEM_PROMPT = """\
You are a scout: a short-lived autonomous coding agent working alone in a git
worktree checkout of a repository. You have four tools: list_files, read_file,
write_file, and bash. All paths are relative to the repository root.

Rules:
- Work only toward the objective you are given. Make the smallest change that
  achieves it.
- Verify your work by running the gate command with the bash tool: `{gate}`
- You get two gate attempts. If the gate still fails after your second attempt,
  stop and report honestly what you tried and where it failed.
- Coming back empty-handed is honorable. A plausible-looking but wrong change
  is not.
- If the objective or the tests themselves appear contradictory or wrong, stop
  and report that instead of special-casing your way around it.
- Finish by replying with a short plain-text report: what you changed, why, and
  anything that surprised you. Do not paste the diff into the report.
"""


class ScoutError(RuntimeError):
    pass


# ---------- config ----------

def load_config(repo_root: str | Path) -> dict:
    """Read .scout/config.toml. A missing file or missing gate is an error, not a
    default: a gate-less scout is just a depot, and we argued against those."""
    path = Path(repo_root) / CONFIG_PATH
    if not path.exists():
        raise ScoutError(f"no config at {path} — scout refuses to run without a gate")
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    cfg = raw.get("scout", {})
    gate = cfg.get("gate")
    if not gate or not str(gate).strip():
        raise ScoutError("config has no gate command — refusing to run")
    return {
        "model": cfg.get("model", "qwen/qwen3.6-27b"),
        "gate": str(gate),
        "max_rounds": int(cfg.get("max_rounds", 24)),
        "bash_timeout": int(cfg.get("bash_timeout", 180)),
        "gate_timeout": int(cfg.get("gate_timeout", 600)),
        "recon_max_rounds": int(cfg.get("recon_max_rounds", 16)),
        # Paths withheld from sortie worktrees via sparse-checkout (e.g. lab
        # notes during blind experiments). Excluded files stay in history and
        # in any commit the sortie produces; they're just absent on disk.
        "exclude": [str(p) for p in cfg.get("exclude", [])],
    }


# ---------- crude placeholders (sorties replace these) ----------

def crude_slug(text: str, max_len: int = 40) -> str:
    """Deliberately dumb. Sortie #1 builds the real scoutlib.slugify; the harness
    only needs *a* branch name, not a good one."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].strip("-")
    return s or "sortie"


def crude_diff_stats(shortstat: str) -> dict:
    """Parse `git diff --shortstat` output. Crude; sortie #4 builds the real one."""
    def grab(pattern: str) -> int:
        m = re.search(pattern, shortstat)
        return int(m.group(1)) if m else 0

    return {
        "files": grab(r"(\d+) files? changed"),
        "insertions": grab(r"(\d+) insertions?"),
        "deletions": grab(r"(\d+) deletions?"),
    }


# ---------- subprocess helpers ----------

def sh(args: list[str] | str, cwd: Path, timeout: int = 120,
       shell: bool = False) -> subprocess.CompletedProcess:
    # Scrub VIRTUAL_ENV so `uv run` inside a worktree resolves the worktree's own
    # env instead of warning about the harness's.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(args, cwd=cwd, shell=shell, capture_output=True,
                          text=True, timeout=timeout, env=env)


def git(repo: Path, *args: str) -> str:
    p = sh(["git", *args], cwd=repo)
    if p.returncode != 0:
        raise ScoutError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


# ---------- scout tools ----------

def _clip(text: str, cap: int = TOOL_OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n[... clipped {len(text) - cap} chars]"


def make_tools(wt: Path, bash_timeout: int) -> list:
    wt = wt.resolve()

    def _inside(rel: str) -> Path:
        p = (wt / rel).resolve()
        if p != wt and wt not in p.parents:
            raise ValueError(f"path escapes the worktree: {rel}")
        return p

    def list_files() -> str:
        """List every file in the repository (tracked and untracked; ignored files excluded)."""
        p = sh(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=wt)
        # ls-files reports sparse-excluded index entries too; list only what's on disk
        present = [ln for ln in p.stdout.splitlines() if (wt / ln).exists()]
        return _clip("\n".join(present)) or "(no files)"

    def read_file(path: str) -> str:
        """Read a file. `path` is relative to the repository root."""
        return _clip(_inside(path).read_text())

    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file with `content`. `path` is relative to the
        repository root. Parent directories are created as needed."""
        target = _inside(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def bash(command: str) -> str:
        """Run a shell command from the repository root; returns its exit code,
        stdout, and stderr. Use this to run the gate command."""
        try:
            p = sh(command, cwd=wt, timeout=bash_timeout, shell=True)
        except subprocess.TimeoutExpired:
            return f"command timed out after {bash_timeout}s"
        out = f"exit code: {p.returncode}\n"
        if p.stdout:
            out += f"stdout:\n{_clip(p.stdout)}\n"
        if p.stderr:
            out += f"stderr:\n{_clip(p.stderr)}\n"
        return out

    return [list_files, read_file, write_file, bash]


# ---------- the sortie ----------

def _msg_text(msg) -> str:
    """Pull the text parts out of an SDK message; fall back to the raw repr."""
    try:
        parts = [t for p in getattr(msg, "content", []) if (t := getattr(p, "text", None))]
        return "\n".join(parts) if parts else str(msg)
    except Exception:
        return repr(msg)


def _strip_think(text: str) -> str:
    """qwen3.6 leaks a stray closing think tag into content; drop everything
    through the last one so report.md reads as the report, not the reasoning."""
    return re.sub(r"^.*</think>\s*", "", text, flags=re.DOTALL)


def make_recon_tools(root: Path) -> list:
    root = root.resolve()

    def _inside(rel: str) -> Path:
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise ValueError(f"path escapes the repository: {rel}")
        return p

    def list_files() -> str:
        """List every file in the repository (tracked and untracked; ignored files excluded)."""
        p = sh(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root)
        present = [ln for ln in p.stdout.splitlines() if (root / ln).exists()]
        return _clip("\n".join(present)) or "(no files)"

    def read_file(path: str) -> str:
        """Read a file. `path` is relative to the repository root."""
        return _clip(_inside(path).read_text())

    def grep(pattern: str, path: str = ".") -> str:
        """Search file contents with a regex (like grep -rn). `path` optionally
        limits the search to a subdirectory or single file."""
        _inside(path)
        p = sh(["grep", "-rn", "-I", "--exclude-dir=.git", "--exclude-dir=node_modules",
                "--exclude-dir=.venv", "--exclude-dir=__pycache__", "--exclude-dir=dist",
                "-e", pattern, path], cwd=root, timeout=30)
        return _clip(p.stdout) or f"(no matches for {pattern!r})"

    return [list_files, read_file, grep]


def run_recon(question: str, target: Path, repo_root: Path, cfg: dict) -> dict:
    """A recon sortie: read-only, no worktree, no gate, no branch. Prose out."""
    started = datetime.now()
    sid = (f"{started.strftime('%Y-%m-%dT%H-%M-%S')}-{os.urandom(2).hex()}"
           f"-recon-{crude_slug(question, 32)}")
    sortie_dir = repo_root / NOTEBOOK / "sorties" / sid
    timing: dict[str, float] = {}

    import lmstudio as lms
    # Default is 60s per API call — a request queued behind n_parallel saturated
    # decode slots dies through no fault of its own. Concurrency needs headroom.
    lms.set_sync_api_timeout(900)

    journal: list[str] = []
    last_assistant: list[str] = []
    parse_failures = {"n": 0}
    act_error = None

    def on_round_start(round_index: int) -> None:
        print(f"[recon] round {round_index + 1}", flush=True)

    def on_message(msg) -> None:
        text = _msg_text(msg)
        journal.append(text)
        if type(msg).__name__ == "AssistantResponse":
            last_assistant.append(text)
        print(f"[recon] {' '.join(text.split())[:200]}", flush=True)

    def on_invalid_tool_request(error, request):
        parse_failures["n"] += 1
        return (f"Your tool call could not be parsed ({error}). "
                "Re-issue it as a single valid tool call.")

    t = time.monotonic()
    result = None
    try:
        model = lms.llm(cfg["model"])
        chat = lms.Chat(RECON_PROMPT)
        chat.add_user_message(f"Question: {question}")
        result = model.act(
            chat,
            make_recon_tools(target),
            max_prediction_rounds=cfg["recon_max_rounds"],
            on_message=on_message,
            on_round_start=on_round_start,
            handle_invalid_tool_request=on_invalid_tool_request,
        )
    except Exception as e:
        act_error = f"{type(e).__name__}: {e}"
        print(f"[recon] act failed: {act_error}", flush=True)
    timing["inference_s"] = round(time.monotonic() - t, 2)
    timing["total_s"] = timing["inference_s"]

    sortie_dir.mkdir(parents=True, exist_ok=True)
    (sortie_dir / "objective.md").write_text(question + "\n")
    (sortie_dir / "journal.md").write_text("\n\n---\n\n".join(journal) or "(no messages)\n")
    (sortie_dir / "report.md").write_text(
        (_strip_think(last_assistant[-1]) if last_assistant else "(no report)") + "\n")

    manifest = {
        "id": sid,
        "mode": "recon",
        "objective": question,
        "target": str(target),
        "status": "error" if act_error else "recon-complete",
        "model": cfg["model"],
        "rounds": result.rounds if result else None,
        "tool_parse_failures": parse_failures["n"],
        "act_error": act_error,
        "timing": timing,
        "created": started.isoformat(timespec="seconds"),
    }
    (sortie_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with open(repo_root / NOTEBOOK / "index.jsonl", "a") as f:
        f.write(json.dumps(manifest) + "\n")
    return manifest


def run_sortie(objective: str, repo_root: Path, cfg: dict) -> dict:
    started = datetime.now()
    sid = (f"{started.strftime('%Y-%m-%dT%H-%M-%S')}-{os.urandom(2).hex()}"
           f"-{crude_slug(objective)}")
    branch = f"scout/{sid}"
    wt = repo_root / WORKTREES / sid
    sortie_dir = repo_root / NOTEBOOK / "sorties" / sid
    timing: dict[str, float] = {}

    # -- setup: worktree on a fresh branch from HEAD
    t = time.monotonic()
    wt.parent.mkdir(exist_ok=True)
    git(repo_root, "worktree", "add", "-b", branch, str(wt), "HEAD")
    if cfg["exclude"]:
        git(wt, "sparse-checkout", "set", "--no-cone", "/*",
            *[f"!/{p}" for p in cfg["exclude"]])
    timing["setup_s"] = round(time.monotonic() - t, 2)

    # -- inference: the act loop
    import lmstudio as lms  # lazy: tests and --help shouldn't need a server
    lms.set_sync_api_timeout(900)  # queue wait under concurrency; see run_recon

    journal: list[str] = []
    last_assistant: list[str] = []
    parse_failures = {"n": 0}
    status, exit_reason, act_error = "error", "unknown", None

    def on_round_start(round_index: int) -> None:
        print(f"[scout] round {round_index + 1}", flush=True)

    def on_message(msg) -> None:
        text = _msg_text(msg)
        journal.append(text)
        if type(msg).__name__ == "AssistantResponse":
            last_assistant.append(text)
        preview = " ".join(text.split())[:200]
        print(f"[scout] {preview}", flush=True)

    def on_invalid_tool_request(error, request):
        # One malformed call must not vaporize a sortie: feed the parse error
        # back to the model as the tool result so it can re-issue the call.
        parse_failures["n"] += 1
        print(f"[scout] malformed tool call #{parse_failures['n']}: {error}", flush=True)
        return (f"Your tool call could not be parsed ({error}). "
                "Re-issue it as a single valid tool call.")

    t = time.monotonic()
    result = None
    try:
        model = lms.llm(cfg["model"])
        chat = lms.Chat(SYSTEM_PROMPT.format(gate=cfg["gate"]))
        chat.add_user_message(f"Objective: {objective}")
        result = model.act(
            chat,
            make_tools(wt, cfg["bash_timeout"]),
            max_prediction_rounds=cfg["max_rounds"],
            on_message=on_message,
            on_round_start=on_round_start,
            handle_invalid_tool_request=on_invalid_tool_request,
        )
    except Exception as e:  # archive what we have; the notebook outlives the crash
        act_error = f"{type(e).__name__}: {e}"
        print(f"[scout] act failed: {act_error}", flush=True)
    timing["inference_s"] = round(time.monotonic() - t, 2)

    # -- gate: the harness runs the official one regardless of what the scout claims
    t = time.monotonic()
    gate_code: int | None = None
    gate_log = f"$ {cfg['gate']}\n"
    if act_error is None:
        try:
            p = sh(cfg["gate"], cwd=wt, timeout=cfg["gate_timeout"], shell=True)
            gate_code = p.returncode
            gate_log += f"exit code: {p.returncode}\n\n{p.stdout}\n{p.stderr}"
        except subprocess.TimeoutExpired:
            gate_log += f"TIMED OUT after {cfg['gate_timeout']}s"
    else:
        gate_log += f"skipped: act loop failed ({act_error})"
    timing["gate_s"] = round(time.monotonic() - t, 2)

    # -- verdict + capture diff (stage everything so new files show up)
    t = time.monotonic()
    git(wt, "add", "-A")
    diff_text = git(wt, "diff", "--cached")
    stats = crude_diff_stats(git(wt, "diff", "--cached", "--shortstat"))
    empty = not diff_text.strip()

    if act_error is not None:
        status, exit_reason = "error", "act-failed"
    elif empty:
        status, exit_reason = "empty", "no-diff"
    elif gate_code == 0:
        status, exit_reason = "clear", "gate-passed"
    else:
        status, exit_reason = "blocked", "gate-failed"

    # -- archive BEFORE teardown, always
    sortie_dir.mkdir(parents=True, exist_ok=True)
    (sortie_dir / "objective.md").write_text(objective + "\n")
    (sortie_dir / "journal.md").write_text("\n\n---\n\n".join(journal) or "(no messages)\n")
    (sortie_dir / "report.md").write_text(
        (_strip_think(last_assistant[-1]) if last_assistant else "(no report)") + "\n")
    (sortie_dir / "diff.patch").write_text(diff_text)
    (sortie_dir / "gate.log").write_text(gate_log)

    # -- teardown: survivors keep their branch, everything else is discarded
    if status == "clear":
        git(wt, "commit", "-q", "-m", f"scout: {objective}")
    git(repo_root, "worktree", "remove", "--force", str(wt))
    if status != "clear":
        git(repo_root, "branch", "-D", branch)
    timing["teardown_s"] = round(time.monotonic() - t, 2)
    timing["total_s"] = round(sum(timing.values()), 2)

    manifest = {
        "id": sid,
        "objective": objective,
        "status": status,
        "exit_reason": exit_reason,
        "branch": branch if status == "clear" else None,
        "model": cfg["model"],
        "gate": {"cmd": cfg["gate"], "exit_code": gate_code},
        "diff": stats,
        "rounds": result.rounds if result else None,
        "tool_parse_failures": parse_failures["n"],
        "act_error": act_error,
        "timing": timing,
        "created": started.isoformat(timespec="seconds"),
    }
    (sortie_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with open(repo_root / NOTEBOOK / "index.jsonl", "a") as f:
        f.write(json.dumps(manifest) + "\n")
    return manifest


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="dispatch one scout sortie")
    ap.add_argument("objective", help="the objective (build) or question (recon)")
    ap.add_argument("--recon", action="store_true",
                    help="read-only recon: no worktree, no gate, prose answer")
    ap.add_argument("--repo", type=Path, default=None,
                    help="target repository for recon (default: this repo)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent
    try:
        cfg = load_config(repo_root)
        if args.recon:
            target = (args.repo or repo_root).resolve()
            if not target.is_dir():
                raise ScoutError(f"recon target is not a directory: {target}")
            m = run_recon(args.objective, target, repo_root, cfg)
            t = m["timing"]
            print(f"\nrecon {m['id']}  status={m['status']}")
            print(f"inference {t['inference_s']}s | rounds: {m['rounds']}")
            return 0 if m["status"] == "recon-complete" else 1
        m = run_sortie(args.objective, repo_root, cfg)
    except ScoutError as e:
        print(f"scout: {e}", file=sys.stderr)
        return 1
    t = m["timing"]
    print(f"\nsortie {m['id']}  status={m['status']} ({m['exit_reason']})")
    print(f"setup {t['setup_s']}s | inference {t['inference_s']}s | "
          f"gate {t['gate_s']}s | teardown {t['teardown_s']}s | total {t['total_s']}s")
    print(f"rounds: {m['rounds']}  diff: {m['diff']['files']} files "
          f"+{m['diff']['insertions']}/-{m['diff']['deletions']}")
    if m["branch"]:
        print(f"branch: {m['branch']}")
    return 0 if m["status"] == "clear" else 1


if __name__ == "__main__":
    sys.exit(main())
