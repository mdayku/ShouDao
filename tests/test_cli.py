"""Tests for ShouDao CLI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from shoudao.cli import main


def test_run_max_results_zero_means_unlimited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure --max-results 0 maps to unlimited in the pipeline call."""
    captured: dict[str, object] = {}

    def fake_run_pipeline(*, max_results: int | None, **_kwargs: Any) -> SimpleNamespace:
        captured["max_results"] = max_results
        return SimpleNamespace(leads=[], errors=[])

    monkeypatch.setattr("shoudao.pipeline.run_pipeline", fake_run_pipeline)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--prompt",
            "test prompt",
            "--max-results",
            "0",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["max_results"] is None


