# Release Candidates

Release candidates let users test the next DessMonitor version through HACS
without offering it as the normal stable update.

## Version and branch policy

- Use `vX.Y.Z-rc.N`, for example `v2.3.0-rc.1`.
- Start `release/X.Y.Z` from the tested `origin/dev` commit.
- Keep `main` on the latest stable release until the final version is ready.
- Never move or reuse an RC tag. Publish `rc.2` if another candidate is needed.
- Set `VERSION`, `custom_components/dessmonitor/manifest.json`, and the
  `VERSION` constant in `custom_components/dessmonitor/const.py` to the same
  version without the leading `v`.
- Add an exact `## [X.Y.Z-rc.N]` entry to `CHANGELOG.md`.

Home Assistant requires a custom integration version recognized by
AwesomeVersion. This RC format is valid SemVer. The release workflow accepts
only stable `X.Y.Z` versions and this RC format.

## Prepare and publish an RC

Replace the example version in these commands:

```bash
git fetch origin
git switch -c release/2.3.0 origin/dev

# Update VERSION, manifest.json, const.py, and CHANGELOG.md to 2.3.0-rc.1.

make format
.venv/bin/pytest -q
make check
git diff --check

git add VERSION CHANGELOG.md custom_components/dessmonitor/manifest.json \
  custom_components/dessmonitor/const.py
git commit -m "chore: prepare v2.3.0-rc.1"
git push -u origin release/2.3.0
```

Wait for Tests, Hassfest, and HACS Validation to pass on the release branch.
Then create and push an annotated tag from that exact commit:

```bash
git tag -a v2.3.0-rc.1 -m "Release candidate v2.3.0-rc.1"
git push origin v2.3.0-rc.1
```

The Release workflow validates the tag and changelog, builds the ZIP files,
and publishes a GitHub prerelease. Confirm that:

1. The GitHub release is marked **Pre-release**, not **Latest**.
2. Both ZIP assets exist.
3. `manifest.json` inside `ha-dessmonitor.zip` has the RC version.

Do not merge the RC-only version commit into `main`. Continue fixes on the
release branch.

## How HACS handles the RC

HACS uses GitHub releases for this repository because `hacs.json` enables ZIP
releases and names `ha-dessmonitor.zip` as the installable asset.

- With the repository Pre-release switch off, HACS excludes prereleases from
  update checks and the version selector. A user who does nothing stays on the
  stable release.
- Turning on the switch makes prereleases available and preferred by the HACS
  update entity. Testers can then select the RC manually.
- HACS lists eligible releases and the default branch in its version selector.
- Installing or changing an integration version requires a Home Assistant
  restart.

### Install the RC manually in HACS

1. Create a Home Assistant backup.
2. Open **Settings > Devices & services > Entities**, include disabled
   entities, and enable the DessMonitor **Pre-release** switch entity.
3. Turn on that switch.
4. Open **HACS**, find **DessMonitor**, and select **Update information** from
   its three-dot menu.
5. Select **Redownload** from the same menu. Use **Download** for a first
   installation.
6. Expand **Need a different version?**, select `vX.Y.Z-rc.N`, and download it.
7. Restart Home Assistant and test the release notes.

The tester may turn the Pre-release switch off after installation to stop
future RCs from being preferred. This does not remove the installed RC.

To return to stable, repeat **Redownload**, select the latest stable version,
and restart Home Assistant. Restore the backup if a release note specifically
requires it.

## Finish the stable release

After testing, change the version to `X.Y.Z`, consolidate the changelog, run
the full checks, and follow the stable release process in
[GIT_GUIDE.md](GIT_GUIDE.md). The stable tag is created only after the release
branch reaches `main`. Merge the final release state back into `dev`.

## Upstream references

- [Home Assistant integration manifest version](https://developers.home-assistant.io/docs/creating_integration_manifest/#version)
- [HACS downloading a specific version](https://www.hacs.xyz/docs/use/repositories/dashboard/#downloading-a-specific-version-of-a-repository)
- [HACS prerelease update switch](https://www.hacs.xyz/docs/use/entities/switch/)
- [HACS integration release selection](https://www.hacs.xyz/docs/publish/integration/#github-releases-optional)
