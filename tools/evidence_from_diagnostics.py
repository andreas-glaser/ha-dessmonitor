#!/usr/bin/env python3
"""Turn a reporter's diagnostics download into a committed evidence file.

A download is accepted as evidence for a devcode, and it is better evidence
than a CLI analysis because it records a unit for every reading rather than for
the sampled ones (#60). Committing one by hand means deciding which of Home
Assistant's own sections to keep and hoping the per-device checksums survive,
which is a decision nobody should make twice. This makes it one command:

    .venv/bin/python tools/evidence_from_diagnostics.py ~/Downloads/config_entry-dessmonitor-01ABC.json

It keeps the integration's own sections verbatim - ``integration``,
``coordinator``, ``local`` and every ``devices`` entry, whose checksums cover
them - and drops the host metadata Home Assistant adds around them, which says
nothing about the devcode and names the instance: ``home_assistant``,
``custom_components``, ``integration_manifest``, ``issues``, ``setup_times``,
and the entry's own ``entry_data`` and ``entry_options``.

It then verifies every device checksum and refuses to write if one fails, so a
file edited after the download cannot be committed as evidence of anything.
One file is written per devcode, named the way ``tests/test_analysis_coverage``
globs for it, and an existing file is never overwritten without ``--force``.

The downloaded file is untrusted input: it is read as JSON and nothing in it is
executed or imported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.dessmonitor.support_report import (  # noqa: E402
    normalized_reports,
    scale_disagreements,
)

# The sections Home Assistant wraps a diagnostics hook's report in, plus the
# config entry's own values. None of them is evidence about a devcode, and the
# entry sections carry the account's configuration.
_HOST_SECTIONS = (
    "home_assistant",
    "custom_components",
    "integration_manifest",
    "issues",
    "setup_times",
)
_ENTRY_SECTIONS = ("entry_data", "entry_options")
_KEPT_SECTIONS = ("integration", "coordinator", "local", "devices")

_DEFAULT_OUTPUT_DIR = Path("docs/evidence/devcodes")
_MAX_INPUT_BYTES = 8 * 1024 * 1024


def read_download(path: Path) -> dict[str, Any]:
    """Load one bounded, regular diagnostics download."""
    if path.is_symlink():
        raise ValueError("the download must not be a symbolic link")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("the download must be a regular file")
    if resolved.stat().st_size > _MAX_INPUT_BYTES:
        raise ValueError("the download exceeds the 8 MB safety limit")
    with resolved.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("the download must contain a JSON object")
    return payload


def evidence_from(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the evidence sections of a download, in the shape it arrived in.

    The ``data`` envelope is kept, because that is how the coverage tooling and
    the test guard read a download and keeping it means the committed file is
    the file the reporter attached, minus what was never evidence.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(
            "this is not a diagnostics download: Home Assistant writes the "
            "report under a 'data' key"
        )
    # A device download carries one device's report under ``support_report``
    # rather than a list under ``devices``. It is the same report, with the
    # same checksum over it, so it is lifted into the shape the rest of this
    # tool and the coverage guard read instead of being refused for having come
    # from the other "Download diagnostics" button.
    if "devices" not in data and isinstance(data.get("support_report"), dict):
        data = {**data, "devices": [data["support_report"]]}
    if not isinstance(data.get("devices"), list) or not data["devices"]:
        raise ValueError("the download carries no devices to use as evidence")

    kept = {section: data[section] for section in _KEPT_SECTIONS if section in data}
    return {"data": kept}


def _devcodes(evidence: dict[str, Any]) -> list[Any]:
    """Return the devcode of each device in the evidence, in file order."""
    return [device.get("devcode") for device in evidence["data"]["devices"]]


def verify(evidence: dict[str, Any]) -> list[str]:
    """Return one problem per device whose report cannot be trusted as evidence."""
    problems: list[str] = []
    for record in normalized_reports(evidence):
        devcode = record["devcode"]
        if devcode is None:
            problems.append("a device report carries no devcode")
            continue
        if not record["checksum"]:
            problems.append(f"devcode {devcode} carries no checksum")
        elif not record["checksum_valid"]:
            problems.append(
                f"devcode {devcode} does not match its own checksum; ask for a "
                "fresh download rather than editing this one"
            )
        if not record["titles"]:
            problems.append(f"devcode {devcode} reports no readings")
    return problems


def _report_disagreements(evidence: dict[str, Any]) -> None:
    """Print a scale disagreement between a device's two sources, if any.

    A hybrid download measures the same reading locally and in the cloud, and
    an order of magnitude between the two is a unit mistake in a driver rather
    than evidence about a devcode (#53). Committing the file is still right -
    it records the bug - but the maintainer should know before the guard in
    ``tests/test_analysis_coverage`` tells them.
    """
    for device in evidence["data"]["devices"]:
        for key, (local, cloud) in scale_disagreements(device).items():
            print(
                f"  ! devcode {device.get('devcode')} reports {key} as {local} "
                f"locally and {cloud} from the cloud. One of the two is scaled "
                "wrongly; fix the driver, or record it in "
                "RECORDED_DISAGREEMENTS with the reason."
            )


def write_evidence(
    evidence: dict[str, Any], output_dir: Path, *, force: bool = False
) -> list[Path]:
    """Write one evidence file per devcode and return what was written."""
    written: list[Path] = []
    by_devcode: dict[Any, list[dict[str, Any]]] = {}
    for device in evidence["data"]["devices"]:
        by_devcode.setdefault(device.get("devcode"), []).append(device)

    for devcode, devices in sorted(by_devcode.items(), key=lambda item: str(item[0])):
        # The committed name is what tests/test_analysis_coverage globs for.
        path = output_dir / f"analysis_{devcode}.json"
        if path.exists() and not force:
            raise FileExistsError(
                f"{path} already exists; pass --force to replace the evidence "
                "for this devcode"
            )
        payload = {
            "data": {
                **{
                    section: evidence["data"][section]
                    for section in _KEPT_SECTIONS
                    if section in evidence["data"] and section != "devices"
                },
                "devices": devices,
            }
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        written.append(path)
    return written


def main() -> int:
    """Prepare evidence files from one diagnostics download."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("download", type=Path, help="The attached diagnostics JSON")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Where to write the evidence (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing evidence for a devcode this download covers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify and report without writing anything",
    )
    args = parser.parse_args()

    try:
        payload = read_download(args.download)
        evidence = evidence_from(payload)
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print(f"{args.download}: {err}", file=sys.stderr)
        return 2

    dropped = sorted(
        section
        for section in (*_HOST_SECTIONS, *_ENTRY_SECTIONS)
        if section in payload or section in payload.get("data", {})
    )
    print(f"{args.download}: devcodes {_devcodes(evidence)}")
    if dropped:
        print(f"  dropped {', '.join(dropped)}")

    problems = verify(evidence)
    if problems:
        for problem in problems:
            print(f"  ! {problem}", file=sys.stderr)
        return 1

    print("  every device report matches its own checksum")
    _report_disagreements(evidence)

    if args.dry_run:
        print("  dry run: nothing written")
        return 0

    try:
        written = write_evidence(evidence, args.output_dir, force=args.force)
    except (OSError, FileExistsError) as err:
        print(f"  ! {err}", file=sys.stderr)
        return 1

    for path in written:
        print(f"  wrote {path}")
    print(
        "  next: .venv/bin/python tools/analysis_coverage.py "
        + " ".join(str(path) for path in written)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
