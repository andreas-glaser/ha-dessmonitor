#!/usr/bin/env python3
"""Answer the first question of a devcode issue from its attachments.

Every support thread opens the same way: read the issue, find the attached
diagnostics download or CLI analysis, see which readings reach an entity, and
check whether anything looks mis-scaled. Doing that by hand is four commands
and one step that is easy to skip - comparing a device's local reading against
the cloud's own figure for the same sensor, which is what found the PI18 energy
counter reading a thousand times too high (#53).

    .venv/bin/python tools/triage.py 53
    .venv/bin/python tools/triage.py https://github.com/andreas-glaser/ha-dessmonitor/issues/62
    .venv/bin/python tools/triage.py --file ~/Downloads/config_entry-dessmonitor-01ABC.json

It needs the ``gh`` CLI for the issue forms, authenticated as usual; ``--file``
needs nothing and works on a download already on disk. Attachments are written
to a fresh directory and only ever parsed as JSON: a download is a reporter's
file, which is untrusted input, so nothing in it is executed or imported.

Nothing is written into the repository. When a file is worth committing as
evidence, this prints the ``evidence_from_diagnostics`` command that does it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis_coverage import coverage  # noqa: E402
from custom_components.dessmonitor.support_report import (  # noqa: E402
    normalized_reports,
    scale_disagreements,
)

_DEFAULT_REPO = "andreas-glaser/ha-dessmonitor"
_ATTACHMENT = re.compile(
    r"https://github\.com/user-attachments/files/\d+/[^\s)\"'<>]+\.json"
)
_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
_FETCH_TIMEOUT_SECONDS = 30
# A generic client name: the reporter's and the maintainer's identities have no
# business in a request header.
_USER_AGENT = "ha-dessmonitor-triage"


def issue_text(repo: str, number: int) -> tuple[str, str]:
    """Return an issue's title and its body plus every comment body.

    The ``gh`` CLI's own issue view walks the classic-projects GraphQL fields
    and fails on this repository, so this asks the REST API directly.
    """
    issue = _gh_json(f"repos/{repo}/issues/{number}")
    comments = _gh_json(f"repos/{repo}/issues/{number}/comments")
    bodies = [issue.get("body") or ""]
    bodies += [comment.get("body") or "" for comment in comments]
    return str(issue.get("title") or ""), "\n\n".join(bodies)


def _gh_json(path: str) -> Any:
    """Run one authenticated REST call through the gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "api", path, "--paginate"],
            capture_output=True,
            text=True,
            timeout=_FETCH_TIMEOUT_SECONDS,
            check=True,
        )
    except FileNotFoundError as err:
        raise RuntimeError(
            "the gh CLI is not installed; pass --file with a downloaded report"
        ) from err
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"gh api {path} failed: {err.stderr.strip()}") from err
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"gh api {path} timed out") from err

    # --paginate concatenates JSON arrays as separate documents on one line.
    payloads = [
        json.loads(chunk) for chunk in re.split(r"(?<=\])(?=\[)", result.stdout.strip())
    ]
    if len(payloads) == 1:
        return payloads[0]
    merged: list[Any] = []
    for payload in payloads:
        merged.extend(payload)
    return merged


def download(url: str, directory: Path) -> Path:
    """Fetch one attachment into its own directory, bounded in size."""
    name = url.rsplit("/", 1)[-1]
    # The URL names the file, so the name is the reporter's: keep it inside the
    # directory we chose rather than trusting it as a path.
    path = directory / Path(name).name
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(  # noqa: S310 - https URL from the GitHub API
        request, timeout=_FETCH_TIMEOUT_SECONDS
    ) as response:
        payload = response.read(_MAX_ATTACHMENT_BYTES + 1)
    if len(payload) > _MAX_ATTACHMENT_BYTES:
        raise ValueError(f"{name} exceeds the 8 MB safety limit")
    path.write_bytes(payload)
    return path


def triage(path: Path) -> int:
    """Report what one attachment says about its devcodes.

    Returns the number of findings worth acting on: a reading that carries a
    unit and reaches no entity, or two sources that disagree about scale.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as err:
        print(f"  {path.name}: not readable as JSON ({err})")
        return 0

    try:
        records = normalized_reports(payload)
    except ValueError:
        print(f"  {path.name}: not a devcode analysis or diagnostics download")
        return 0

    findings = 0
    print(f"  {path.name}")
    for record in records:
        result = coverage(record)
        checksum = (
            "checksum ok"
            if record["checksum_valid"]
            else "CHECKSUM MISMATCH - ask for a fresh report"
        )
        print(
            f"    devcode {result.devcode} "
            f"({'registered' if result.registered else 'UNREGISTERED'}, "
            f"{record['source']}, {checksum})"
        )
        print(
            f"      resolves {len(result.resolved)} of {result.total} titles, "
            f"{len(result.unmapped_readings)} unmapped reading(s) carry a unit"
        )
        for title, unit in result.unmapped_readings:
            print(f"        {title}  [{unit}]")
            findings += 1
        if result.declared_settings:
            print(
                f"      {len(result.declared_settings)} title(s) declared "
                "settings by the profile"
            )

    for device in _device_reports(payload):
        for key, (local, cloud) in scale_disagreements(device).items():
            print(
                f"      ! {key}: {local} locally against {cloud} from the cloud. "
                "One of the two is scaled wrongly."
            )
            findings += 1
    return findings


def _device_reports(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the device reports of a diagnostics download, if it is one."""
    data = payload.get("data", payload)
    devices = data.get("devices") if isinstance(data, dict) else None
    return [device for device in devices or [] if isinstance(device, dict)]


def main() -> int:
    """Triage one issue's attachments, or one file already on disk."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "issue", nargs="?", help="Issue number or URL (omit when using --file)"
    )
    parser.add_argument(
        "--file",
        type=Path,
        action="append",
        default=[],
        help="A downloaded report to triage instead of fetching attachments",
    )
    parser.add_argument(
        "--repo", default=_DEFAULT_REPO, help=f"Repository (default: {_DEFAULT_REPO})"
    )
    args = parser.parse_args()

    if not args.issue and not args.file:
        parser.error("give an issue number or --file")

    paths: list[Path] = list(args.file)
    directory: str | None = None

    if args.issue:
        match = re.search(r"(\d+)\s*$", str(args.issue))
        if not match:
            parser.error(f"{args.issue!r} is not an issue number or URL")
        number = int(match.group(1))
        try:
            title, text = issue_text(args.repo, number)
        except RuntimeError as err:
            print(err, file=sys.stderr)
            return 2
        print(f"#{number} {title}")

        urls = list(dict.fromkeys(_ATTACHMENT.findall(text)))
        if not urls:
            print("  no JSON attachment found; ask for Download diagnostics")
            return 0

        # Untrusted input lands in its own empty directory, never in the repo.
        directory = tempfile.mkdtemp(prefix="dessmonitor-triage-")
        for url in urls:
            try:
                paths.append(download(url, Path(directory)))
            except (urllib.error.URLError, OSError, ValueError) as err:
                print(f"  {url}: {err}", file=sys.stderr)

    findings = 0
    for path in paths:
        findings += triage(path)

    if directory:
        print(f"  attachments saved under {directory}")
    if paths:
        print(
            "  to commit one as evidence: .venv/bin/python "
            "tools/evidence_from_diagnostics.py <file>"
        )
    print(f"  {findings} finding(s) worth acting on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
