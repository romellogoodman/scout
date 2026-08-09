"""Baseline tests for the harness itself. These pass; they exist so the gate is
never vacuous — deleting the planted failing tests still leaves a suite behind."""

import ast
from pathlib import Path

import pytest

from scout import ScoutError, crude_diff_stats, crude_slug, load_config


def test_config_missing_file_is_an_error(tmp_path):
    with pytest.raises(ScoutError, match="refuses to run"):
        load_config(tmp_path)


def test_config_missing_gate_is_an_error(tmp_path):
    cfg = tmp_path / ".scout"
    cfg.mkdir()
    (cfg / "config.toml").write_text('[scout]\nmodel = "whatever"\n')
    with pytest.raises(ScoutError, match="no gate"):
        load_config(tmp_path)


def test_config_reads_gate_and_defaults(tmp_path):
    cfg = tmp_path / ".scout"
    cfg.mkdir()
    (cfg / "config.toml").write_text('[scout]\ngate = "pytest -q"\n')
    out = load_config(tmp_path)
    assert out["gate"] == "pytest -q"
    assert out["max_rounds"] == 24


def test_crude_slug_never_empty():
    assert crude_slug("!!!") == "sortie"
    assert crude_slug("Make Tests Pass") == "make-tests-pass"


def test_crude_diff_stats():
    line = " 3 files changed, 41 insertions(+), 7 deletions(-)"
    assert crude_diff_stats(line) == {"files": 3, "insertions": 41, "deletions": 7}
    assert crude_diff_stats("") == {"files": 0, "insertions": 0, "deletions": 0}


def test_the_harness_never_imports_its_cargo():
    """scoutlib is sortie-built cargo, not harness infrastructure — the machinery
    that judges sorties must not stand on their output (see the 2026-08-09 devlog
    entry of this name)."""
    tree = ast.parse((Path(__file__).parents[1] / "scout.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                       else [node.module or ""])
            offenders = [m for m in modules if m.split(".")[0] == "scoutlib"]
            assert not offenders, f"scout.py imports {offenders} at line {node.lineno}"
