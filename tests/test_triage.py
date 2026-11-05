"""Triaging an issue's attachments, offline.

The first minutes of every support thread are identical: find the attached
report, see which readings reach an entity, and check whether two sources
disagree about a reading's scale. These tests cover the parts that work without
the network: finding the attachments in an issue's markdown, and what the
report of one file says.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "triage.py"
_EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "devcodes"


def _load_tool() -> Any:
    """Load the tool the way a maintainer runs it, by path.

    At module import, not inside a test: ``pytest-homeassistant-custom-component``
    rebinds ``custom_components`` to its own testing config once fixtures run, so
    a module that imports the integration has to be loaded during collection.
    """
    spec = importlib.util.spec_from_file_location("dessmonitor_triage", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TRIAGE = _load_tool()


def _tool() -> Any:
    """Return the loaded tool."""
    return TRIAGE


ISSUE_BODY = """
Hi, here is the file.

[config_entry-dessmonitor-01ABC.json](https://github.com/user-attachments/files/34395866/config_entry-dessmonitor-01ABC.json)

And a screenshot:
![shot](https://github.com/user-attachments/assets/fe8b83aa-faff-4ebb-a1b8-61d9eef43fc0)

The same file again:
https://github.com/user-attachments/files/34395866/config_entry-dessmonitor-01ABC.json
"""


def test_the_json_attachments_are_found_once_each() -> None:
    """Screenshots are not reports, and a repeated link is one file."""
    tool = _tool()

    urls = list(dict.fromkeys(tool._ATTACHMENT.findall(ISSUE_BODY)))

    assert urls == [
        "https://github.com/user-attachments/files/34395866/"
        "config_entry-dessmonitor-01ABC.json"
    ]


def test_a_reporters_filename_cannot_escape_the_download_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The URL names the file, so the name is untrusted input."""
    tool = _tool()

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self, _size: int) -> bytes:
            return b"{}"

    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *_, **__: _Response())

    path = tool.download(
        "https://github.com/user-attachments/files/1/..%2F..%2Fescaped.json", tmp_path
    )

    assert path.parent == tmp_path


def test_an_oversized_attachment_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self, size: int) -> bytes:
            return b"x" * size

    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *_, **__: _Response())

    with pytest.raises(ValueError, match="safety limit"):
        tool.download("https://github.com/user-attachments/files/1/big.json", tmp_path)

    assert not list(tmp_path.iterdir())


def test_a_committed_download_reports_its_coverage(capsys: pytest.CaptureFixture) -> None:
    """Devcode 684's download resolves everything that carries a unit."""
    tool = _tool()

    findings = tool.triage(_EVIDENCE / "analysis_684.json")

    out = capsys.readouterr().out
    assert findings == 0
    assert "devcode 684 (registered, integration_diagnostics, checksum ok)" in out
    assert "0 unmapped reading(s) carry a unit" in out


def test_a_scale_disagreement_is_a_finding(capsys: pytest.CaptureFixture) -> None:
    """The check that found the PI18 energy counter (#53) runs here too."""
    tool = _tool()

    findings = tool.triage(_EVIDENCE / "analysis_2452.json")

    out = capsys.readouterr().out
    assert findings == 1
    assert "Energy Total: 10104399.0 locally against 10104.399" in out
    assert "declared settings by the profile" in out


def test_a_file_that_is_not_a_report_is_reported_plainly(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    tool = _tool()
    not_a_report = tmp_path / "notes.json"
    not_a_report.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    assert tool.triage(not_a_report) == 0
    assert tool.triage(broken) == 0

    out = capsys.readouterr().out
    assert "not a devcode analysis or diagnostics download" in out
    assert "not readable as JSON" in out
