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
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

# Fan-out runs many recon sorties concurrently; serialize appends to the shared
# notebook index so their lines can't interleave.
_INDEX_LOCK = threading.Lock()

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

# pi exposes read/write/edit/bash rather than the SDK's named tools, so the pi
# path gets prompts worded for those. The rules are otherwise identical — the
# "stop if the spec is wrong" line is load-bearing (see devlog).
PI_BUILD_PROMPT = """\
You are a scout: a short-lived autonomous coding agent working alone in a
checkout of a repository. You have tools to read files, write files, and run
bash commands. All paths are relative to the repository root.

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

PI_RECON_PROMPT = """\
You are a scout on a reconnaissance sortie: answer a question about the
repository you are standing in. Use your tools read-only: read files and grep
with bash. Do not modify anything.

Rules:
- Answer only from what you actually read in this repository. If you cannot
  find the answer, say so plainly — a wrong answer is worse than no answer.
- Cite file paths (with line numbers where useful) for every claim.
- Finish with a concise prose answer to the question. No code changes, no
  diffs, no speculation beyond what the files support.
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
        # provider selects the inference backend. "openrouter" (default) and any
        # other pi-supported provider ("ollama", …) run through the pi CLI;
        # "lmstudio" uses the in-process LM Studio SDK (the v0 path).
        "provider": str(cfg.get("provider", "openrouter")),
        "model": cfg.get("model", "moonshotai/kimi-k3"),
        # The panel for heterogeneous recon fan-out: a question is asked of every
        # model here at once. Deliberately DIFFERENT models (different labs), so
        # their blind spots decorrelate — agreement means something, and the
        # places they diverge are the signal. Same-model-repeated buys nothing.
        "panel": [str(m) for m in cfg.get(
            "panel", ["moonshotai/kimi-k3", "deepseek/deepseek-v4-flash-0731"])],
        # Fan-out concurrency. Default 1 (sequential) because sandbox-exec +
        # concurrent tool-spawning subprocesses deadlock on macOS; the value of
        # fan-out is model diversity, not speed, so sequential is the honest
        # default. Raise it only with sandbox = false.
        "fanout_workers": int(cfg.get("fanout_workers", 1)),
        # Optional reasoning-effort passthrough for pi providers that require or
        # accept it (e.g. some models mandate thinking).
        "thinking": cfg.get("thinking"),
        # Confine pi-run sorties with the Seatbelt sandbox. Ignored for lmstudio.
        "sandbox": bool(cfg.get("sandbox", True)),
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
    return subprocess.run(args, cwd=cwd, shell=shell, capture_output=True, check=False,
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
    except (AttributeError, TypeError):
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


# ---------- backends ----------

def _import_lmstudio():
    """The LM Studio SDK is an optional extra (`uv sync --extra lmstudio`); the
    default provider is pi, which needs no Python dependency."""
    try:
        import lmstudio as lms
    except ModuleNotFoundError as e:
        raise ScoutError(
            "provider is 'lmstudio' but the lmstudio SDK isn't installed — "
            "run: uv sync --extra lmstudio") from e
    return lms


def _pi_profile(repo_root: Path, kind: str) -> Path | None:
    """Locate the Seatbelt profile for a build or recon run. Returns None when the
    platform can't sandbox (non-macOS, or sandbox-exec/profile absent) — the run
    then proceeds unconfined rather than failing."""
    if sys.platform != "darwin" or not shutil.which("sandbox-exec"):
        return None
    name = "scout_sandbox_recon.sb" if kind == "recon" else "scout_sandbox.sb"
    p = repo_root / "tools" / name
    return p if p.exists() else None


def _pi_session_usage(sess: Path) -> dict | None:
    """Roll up token usage and cost across pi's session journal."""
    if not sess.exists():
        return None
    tot = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0,
           "total_tokens": 0, "cost_usd": 0.0}
    seen = False
    for f in sess.glob("*.jsonl"):
        for line in f.read_text().splitlines():
            try:
                u = (json.loads(line).get("message") or {}).get("usage")
            except json.JSONDecodeError:
                continue
            if not u:
                continue
            seen = True
            tot["input"] += u.get("input", 0)
            tot["output"] += u.get("output", 0)
            tot["reasoning"] += u.get("reasoning", 0)
            tot["cache_read"] += u.get("cacheRead", 0)
            tot["total_tokens"] += u.get("totalTokens", 0)
            tot["cost_usd"] += (u.get("cost") or {}).get("total", 0.0)
    return tot if seen else None


def _pi_journal(sess: Path) -> str:
    """Best-effort readable journal from pi's session jsonl (text + tool calls)."""
    out: list[str] = []
    if not sess.exists():
        return "(no journal)"
    for f in sorted(sess.glob("*.jsonl")):
        for raw in f.read_text().splitlines():
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for part in (ev.get("message") or {}).get("content", []) or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and part.get("text"):
                    out.append(part["text"])
                elif part.get("type") == "toolCall":
                    a = part.get("arguments", {}) or {}
                    detail = a.get("command") or a.get("path") or ""
                    out.append(f"[tool: {part.get('name')}] {str(detail)[:200]}")
    return "\n\n".join(out) or "(no journal)"


def run_pi_agent(*, cwd: Path, cfg: dict, system_prompt: str, user_msg: str,
                 read_only: bool, worktree: Path, profile: Path | None,
                 repo_root: Path, timeout: int) -> dict:
    """Run one pi sortie. The sandbox denies reads under REPO and node fstat()s
    its own stdio at startup, so pi's session lands in tmp and the report comes
    back on stdout — the caller archives both. Returns report/journal/usage/error."""
    sess_parent = Path(tempfile.mkdtemp(prefix="scout-pi-"))
    sess = sess_parent / "session"

    cmd: list[str] = []
    if profile is not None:
        cmd += ["sandbox-exec",
                "-D", f"HOME={Path.home()}",
                "-D", f"REPO={repo_root}",
                "-D", f"WORKTREE={worktree}",
                "-f", str(profile)]
    cmd += ["pi", "--provider", cfg["provider"], "--model", cfg["model"],
            "--system-prompt", system_prompt,
            "--no-extensions", "--no-skills", "--no-context-files",
            "--session-dir", str(sess)]
    if cfg.get("thinking"):
        cmd += ["--thinking", str(cfg["thinking"])]
    if read_only:
        cmd += ["--tools", "read,bash"]
    cmd += ["-p", user_msg]

    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    report, error = "", None
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env, check=False)
        report = (p.stdout or "").strip()
        if p.returncode != 0:
            error = f"pi exit {p.returncode}: {(p.stderr or '').strip()[:400]}"
    except FileNotFoundError:
        error = "pi not found on PATH"
    except subprocess.TimeoutExpired:
        error = f"pi timed out after {timeout}s"

    return {"report": report or "(no report)", "journal": _pi_journal(sess),
            "usage": _pi_session_usage(sess), "error": error,
            "session": sess, "session_parent": sess_parent}


def run_recon(question: str, target: Path, repo_root: Path, cfg: dict) -> dict:
    """A recon sortie: read-only, no worktree, no gate, no branch. Prose out."""
    started = datetime.now(tz=UTC)
    sid = (f"{started.strftime('%Y-%m-%dT%H-%M-%S')}-{os.urandom(2).hex()}"
           f"-recon-{crude_slug(question, 32)}")
    sortie_dir = repo_root / NOTEBOOK / "sorties" / sid
    timing: dict[str, float] = {}

    report_text, journal_text, rounds, usage, act_error = "(no report)", "(no messages)", None, None, None

    t = time.monotonic()
    if cfg["provider"] == "lmstudio":
        lms = _import_lmstudio()
        lms.set_sync_api_timeout(900)  # queue wait under concurrency needs headroom
        journal: list[str] = []
        last_assistant: list[str] = []

        def on_message(msg) -> None:
            text = _msg_text(msg)
            journal.append(text)
            if type(msg).__name__ == "AssistantResponse":
                last_assistant.append(text)
            print(f"[recon] {' '.join(text.split())[:200]}", file=sys.stderr, flush=True)

        try:
            model = lms.llm(cfg["model"])
            chat = lms.Chat(RECON_PROMPT)
            chat.add_user_message(f"Question: {question}")
            result = model.act(
                chat, make_recon_tools(target),
                max_prediction_rounds=cfg["recon_max_rounds"],
                on_message=on_message,
                on_round_start=lambda i: print(f"[recon] round {i + 1}", file=sys.stderr, flush=True),
                handle_invalid_tool_request=lambda e, r: (
                    f"Your tool call could not be parsed ({e}). "
                    "Re-issue it as a single valid tool call."),
            )
            rounds = result.rounds
        except (RuntimeError, OSError, lms.LMStudioError) as e:
            act_error = f"{type(e).__name__}: {e}"
            print(f"[recon] act failed: {act_error}", file=sys.stderr, flush=True)
        report_text = _strip_think(last_assistant[-1]) if last_assistant else "(no report)"
        journal_text = "\n\n---\n\n".join(journal) or "(no messages)"
    else:
        profile = _pi_profile(repo_root, "recon") if cfg["sandbox"] else None
        print(f"[recon] pi {cfg['provider']}/{cfg['model']}"
              f"{' (sandboxed)' if profile else ''}", file=sys.stderr, flush=True)
        r = run_pi_agent(cwd=target, cfg=cfg, system_prompt=PI_RECON_PROMPT,
                         user_msg=f"Question: {question}", read_only=True,
                         worktree=target, profile=profile, repo_root=repo_root,
                         timeout=cfg["gate_timeout"])
        report_text, journal_text, usage, act_error = (
            r["report"], r["journal"], r["usage"], r["error"])
        shutil.rmtree(r["session_parent"], ignore_errors=True)
    timing["inference_s"] = round(time.monotonic() - t, 2)
    timing["total_s"] = timing["inference_s"]

    sortie_dir.mkdir(parents=True, exist_ok=True)
    (sortie_dir / "objective.md").write_text(question + "\n")
    (sortie_dir / "journal.md").write_text(journal_text + "\n")
    (sortie_dir / "report.md").write_text(report_text + "\n")

    manifest = {
        "id": sid,
        "mode": "recon",
        "objective": question,
        "target": str(target),
        "status": "error" if act_error else "recon-complete",
        "provider": cfg["provider"],
        "model": cfg["model"],
        "rounds": rounds,
        "usage": usage,
        "act_error": act_error,
        "timing": timing,
        "created": started.isoformat(timespec="seconds"),
    }
    (sortie_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with _INDEX_LOCK, open(repo_root / NOTEBOOK / "index.jsonl", "a") as f:
        f.write(json.dumps(manifest) + "\n")
    return manifest


# ---------- heterogeneous recon fan-out ----------

def _cited_files(report: str) -> list[str]:
    """Heuristic: pull path-like tokens (a/b/c.ext) a report cites. A mechanical
    proxy for *what evidence a scout looked at*, not a semantic judgment — used
    to compare panels, never to score an answer."""
    hits = re.findall(r"(?:[\w.-]+/)+[\w.-]+\.[A-Za-z][\w]{0,5}", report)
    return sorted({h.rstrip(".") for h in hits})


def run_recon_fanout(questions: list[str], target: Path, repo_root: Path,
                     cfg: dict, panel: list[str]) -> dict:
    """Ask each question of every model in `panel`, concurrently. Returns the raw
    per-model answers plus MECHANICAL agreement proxies (shared vs. divergent
    citations) — never an averaged answer. Divergence is the signal: where a
    diverse panel disagrees is where a blind spot is showing. Synthesis is the
    caller's job; this hands back structured material to synthesize from."""
    tasks = [(q, m) for q in questions for m in panel]

    def _one(q: str, m: str) -> dict:
        man = run_recon(q, target, repo_root, {**cfg, "model": m})
        report = (repo_root / NOTEBOOK / "sorties" / man["id"] / "report.md").read_text()
        return {
            "model": m,
            "status": man["status"],
            "sid": man["id"],
            "cost_usd": (man.get("usage") or {}).get("cost_usd"),
            "cited_files": _cited_files(report),
            "report": report.strip(),
            "error": man.get("act_error"),
        }

    by_q: dict[str, list[dict]] = {q: [] for q in questions}
    workers = max(1, min(cfg.get("fanout_workers", 1), len(tasks) or 1))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, q, m): (q, m) for q, m in tasks}
        for fut in as_completed(futs):
            q, m = futs[fut]
            try:
                by_q[q].append(fut.result())
            except Exception as e:  # a dead scout is a row, not a crash  # noqa: BLE001
                by_q[q].append({"model": m, "status": "error", "sid": None,
                                "cost_usd": None, "cited_files": [], "report": "",
                                "error": f"{type(e).__name__}: {e}"})

    results = []
    for q in questions:
        rows = sorted(by_q[q], key=lambda r: r["model"])
        answered = [r for r in rows if r["status"] == "recon-complete"]
        filesets = [set(r["cited_files"]) for r in answered if r["cited_files"]]
        shared = sorted(set.intersection(*filesets)) if filesets else []
        union = sorted(set.union(*filesets)) if filesets else []
        jaccard = round(len(shared) / len(union), 2) if union else None
        flags = []
        if len(answered) < len(rows):
            flags.append(f"{len(rows) - len(answered)}/{len(rows)} scouts did not answer")
        if len(answered) > 1 and jaccard is not None and jaccard < 0.5:
            flags.append("low citation overlap — panel looked at different evidence; "
                         "treat as low-agreement, read the reports")
        if len(answered) > 1 and not shared and union:
            flags.append("no file cited by every answering scout")
        results.append({
            "question": q, "scouts": rows, "shared_files": shared,
            "all_cited_files": union, "citation_jaccard": jaccard, "flags": flags,
        })

    summary = {
        "mode": "recon-fanout",
        "target": str(target),
        "panel": panel,
        "questions": len(questions),
        "sorties": len(tasks),
        "total_cost_usd": round(sum((r["cost_usd"] or 0)
                                    for res in results for r in res["scouts"]), 4),
        "results": results,
        "created": datetime.now(tz=UTC).isoformat(timespec="seconds"),
    }
    fdir = repo_root / NOTEBOOK / "fanout"
    fdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%S") + "-" + os.urandom(2).hex()
    (fdir / f"{stamp}.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_sortie(objective: str, repo_root: Path, cfg: dict) -> dict:
    started = datetime.now(tz=UTC)
    sid = (f"{started.strftime('%Y-%m-%dT%H-%M-%S')}-{os.urandom(2).hex()}"
           f"-{crude_slug(objective)}")
    branch = f"scout/{sid}"
    # Sandboxed runs put the worktree in tmp: the Seatbelt profile denies ~/code,
    # so an in-repo worktree would be unreadable to the scout. Unsandboxed runs
    # keep it in-repo. The shared .git lives in repo_root either way; the gate
    # (lint+tests) doesn't touch it, and commit/teardown run unsandboxed.
    sandboxed = cfg["provider"] != "lmstudio" and cfg["sandbox"]
    profile = _pi_profile(repo_root, "build") if sandboxed else None
    if profile is not None:
        wt_parent = Path(tempfile.mkdtemp(prefix="scout-wt-"))
        wt = wt_parent / "wt"
    else:
        wt_parent = None
        wt = repo_root / WORKTREES / sid
    sortie_dir = repo_root / NOTEBOOK / "sorties" / sid
    timing: dict[str, float] = {}

    # -- setup: worktree on a fresh branch from HEAD
    t = time.monotonic()
    if wt_parent is None:
        wt.parent.mkdir(exist_ok=True)
    git(repo_root, "worktree", "add", "-b", branch, str(wt), "HEAD")
    if cfg["exclude"]:
        git(wt, "sparse-checkout", "set", "--no-cone", "/*",
            *[f"!/{p}" for p in cfg["exclude"]])
    timing["setup_s"] = round(time.monotonic() - t, 2)

    status, exit_reason, act_error = "error", "unknown", None
    report_text, journal_text, rounds, usage = "(no report)", "(no messages)", None, None

    # -- inference: provider-dispatched
    t = time.monotonic()
    if cfg["provider"] == "lmstudio":
        lms = _import_lmstudio()  # lazy: tests and --help shouldn't need the SDK
        lms.set_sync_api_timeout(900)  # queue wait under concurrency; see run_recon
        journal: list[str] = []
        last_assistant: list[str] = []
        parse_failures = {"n": 0}

        def on_message(msg) -> None:
            text = _msg_text(msg)
            journal.append(text)
            if type(msg).__name__ == "AssistantResponse":
                last_assistant.append(text)
            print(f"[scout] {' '.join(text.split())[:200]}", flush=True)

        def on_invalid_tool_request(error, request):
            # One malformed call must not vaporize a sortie: feed the parse error
            # back so the model can re-issue the call.
            parse_failures["n"] += 1
            print(f"[scout] malformed tool call #{parse_failures['n']}: {error}", flush=True)
            return (f"Your tool call could not be parsed ({error}). "
                    "Re-issue it as a single valid tool call.")

        try:
            model = lms.llm(cfg["model"])
            chat = lms.Chat(SYSTEM_PROMPT.format(gate=cfg["gate"]))
            chat.add_user_message(f"Objective: {objective}")
            result = model.act(
                chat, make_tools(wt, cfg["bash_timeout"]),
                max_prediction_rounds=cfg["max_rounds"],
                on_message=on_message,
                on_round_start=lambda i: print(f"[scout] round {i + 1}", flush=True),
                handle_invalid_tool_request=on_invalid_tool_request,
            )
            rounds = result.rounds
        except (RuntimeError, OSError, lms.LMStudioError) as e:  # notebook outlives the crash
            act_error = f"{type(e).__name__}: {e}"
            print(f"[scout] act failed: {act_error}", flush=True)
        report_text = _strip_think(last_assistant[-1]) if last_assistant else "(no report)"
        journal_text = "\n\n---\n\n".join(journal) or "(no messages)"
    else:
        print(f"[scout] pi {cfg['provider']}/{cfg['model']}"
              f"{' (sandboxed)' if profile else ''}", flush=True)
        r = run_pi_agent(cwd=wt, cfg=cfg,
                         system_prompt=PI_BUILD_PROMPT.format(gate=cfg["gate"]),
                         user_msg=f"Objective: {objective}", read_only=False,
                         worktree=wt, profile=profile, repo_root=repo_root,
                         timeout=cfg["gate_timeout"])
        report_text, journal_text, usage, act_error = (
            r["report"], r["journal"], r["usage"], r["error"])
        shutil.rmtree(r["session_parent"], ignore_errors=True)
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
    (sortie_dir / "journal.md").write_text(journal_text + "\n")
    (sortie_dir / "report.md").write_text(report_text + "\n")
    (sortie_dir / "diff.patch").write_text(diff_text)
    (sortie_dir / "gate.log").write_text(gate_log)

    # -- teardown: survivors keep their branch, everything else is discarded
    if status == "clear":
        git(wt, "commit", "-q", "-m", f"scout: {objective}")
    git(repo_root, "worktree", "remove", "--force", str(wt))
    if status != "clear":
        git(repo_root, "branch", "-D", branch)
    if wt_parent is not None:
        shutil.rmtree(wt_parent, ignore_errors=True)
    timing["teardown_s"] = round(time.monotonic() - t, 2)
    timing["total_s"] = round(sum(timing.values()), 2)

    manifest = {
        "id": sid,
        "objective": objective,
        "status": status,
        "exit_reason": exit_reason,
        "branch": branch if status == "clear" else None,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "gate": {"cmd": cfg["gate"], "exit_code": gate_code},
        "diff": stats,
        "rounds": rounds,
        "usage": usage,
        "act_error": act_error,
        "timing": timing,
        "created": started.isoformat(timespec="seconds"),
    }
    (sortie_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with _INDEX_LOCK, open(repo_root / NOTEBOOK / "index.jsonl", "a") as f:
        f.write(json.dumps(manifest) + "\n")
    return manifest


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="dispatch one scout sortie")
    ap.add_argument("objective", nargs="?",
                    help="the objective (build) or question (recon/fan-out)")
    ap.add_argument("--recon", action="store_true",
                    help="read-only recon: no worktree, no gate, prose answer")
    ap.add_argument("--fanout", action="store_true",
                    help="heterogeneous recon: ask the question of every model in "
                         "the config panel at once; emits a JSON comparison on stdout")
    ap.add_argument("--questions", type=Path, default=None,
                    help="fan-out only: a file of questions (one per line) instead "
                         "of / in addition to the positional question")
    ap.add_argument("--repo", type=Path, default=None,
                    help="target repository for recon (default: this repo)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent
    try:
        cfg = load_config(repo_root)
        if args.fanout:
            target = (args.repo or repo_root).resolve()
            if not target.is_dir():
                raise ScoutError(f"recon target is not a directory: {target}")
            questions = [args.objective] if args.objective else []
            if args.questions:
                questions += [ln.strip() for ln in
                              args.questions.read_text().splitlines() if ln.strip()]
            if not questions:
                raise ScoutError("fan-out needs a question (positional or --questions)")
            print(f"[fanout] {len(questions)}q x {len(cfg['panel'])} models "
                  f"= {len(questions) * len(cfg['panel'])} scouts: "
                  f"{', '.join(cfg['panel'])}", file=sys.stderr, flush=True)
            summary = run_recon_fanout(questions, target, repo_root, cfg, cfg["panel"])
            print(json.dumps(summary, indent=2))
            _print_fanout_digest(summary)
            return 0
        if args.recon:
            if not args.objective:
                raise ScoutError("recon needs a question")
            target = (args.repo or repo_root).resolve()
            if not target.is_dir():
                raise ScoutError(f"recon target is not a directory: {target}")
            m = run_recon(args.objective, target, repo_root, cfg)
            t = m["timing"]
            print(f"\nrecon {m['id']}  status={m['status']}  "
                  f"[{m['provider']}/{m['model']}]")
            print(f"inference {t['inference_s']}s | {_usage_line(m['usage'])}")
            if m["act_error"]:
                print(f"error: {m['act_error']}", file=sys.stderr)
            return 0 if m["status"] == "recon-complete" else 1
        if not args.objective:
            raise ScoutError("need an objective (or --recon/--fanout with a question)")
        m = run_sortie(args.objective, repo_root, cfg)
    except ScoutError as e:
        print(f"scout: {e}", file=sys.stderr)
        return 1
    t = m["timing"]
    print(f"\nsortie {m['id']}  status={m['status']} ({m['exit_reason']})  "
          f"[{m['provider']}/{m['model']}]")
    print(f"setup {t['setup_s']}s | inference {t['inference_s']}s | "
          f"gate {t['gate_s']}s | teardown {t['teardown_s']}s | total {t['total_s']}s")
    print(f"diff: {m['diff']['files']} files "
          f"+{m['diff']['insertions']}/-{m['diff']['deletions']} | {_usage_line(m['usage'])}")
    if m["act_error"]:
        print(f"error: {m['act_error']}", file=sys.stderr)
    if m["branch"]:
        print(f"branch: {m['branch']}")
    return 0 if m["status"] == "clear" else 1


def _usage_line(usage: dict | None) -> str:
    if not usage:
        return "usage: n/a"
    return (f"tokens: {usage['total_tokens']} "
            f"(in {usage['input']} / out {usage['output']}) | "
            f"cost: ${usage['cost_usd']:.4f}")


def _print_fanout_digest(summary: dict) -> None:
    """Compact, human-scannable digest to stderr (stdout stays clean JSON)."""
    w = sys.stderr
    print(f"\n=== recon fan-out: {summary['sorties']} scouts, "
          f"${summary['total_cost_usd']:.4f} ===", file=w)
    for res in summary["results"]:
        jac = res["citation_jaccard"]
        agree = "n/a" if jac is None else f"{jac:.0%} citation overlap"
        print(f"\nQ: {res['question']}", file=w)
        print(f"   agreement: {agree}   "
              f"shared files: {', '.join(res['shared_files']) or '(none)'}", file=w)
        for s in res["scouts"]:
            tag = s["status"] if s["status"] == "recon-complete" else f"!{s['status']}"
            cost = f"${s['cost_usd']:.4f}" if s["cost_usd"] else "-"
            print(f"     [{tag:16}] {s['model']:34} "
                  f"{len(s['cited_files'])} files  {cost}", file=w)
        for flag in res["flags"]:
            print(f"   ⚠ {flag}", file=w)


if __name__ == "__main__":
    sys.exit(main())
