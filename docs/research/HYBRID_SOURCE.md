# Hybrid snapshot, diagnostics and entity-identity research

Baseline: v2.5.0, `5b90b75057c0bef8e677918413a0f63104a0ea48`.

## Confirmed race

The successful refresh path captured local data before awaiting cloud I/O and
merged with that old snapshot afterward. Regression tests pause the cloud
request, change local availability, then release the request. Both local arrival
and disconnection must be reflected in the returned snapshot. Re-reading local
data after the await fixes those cases.

An earlier physical installation displayed persistent Cloud, but the cause of
that historical symptom is unproven. A later instrumented startup showed local
ready before a 30-second initial cloud timeout finished, followed by correct
Local publication. This does not establish that the race caused the old symptom.

## Read-only diagnostics

The download compares current snapshots, recomputed source choice, entity binding,
listeners, native/state values, enabled flags and installed-code hashes. Runtime
collection uses allowlisted fields and hashed identifiers, without device/API
refreshes. File hashes are computed only when downloading diagnostics.
Address verification is tri-state: true/false require explicit boolean metadata;
missing or malformed metadata yields null. Redaction/no-network tests cover this.

Data Source entities from other entries can appear as hashed context with their
ownership flag. Hashes use 12 hex characters and support correlation, not a claim
of irreversible anonymity for short/predictable identifiers.

## Reload and dashboard concern

`tests/test_mode_entity_identity.py` uses real HA config-entry/platform reloads,
entity/device registry and an automation, with network startup stubbed.
Cloud → Prefer local → Cloud → Prefer local preserves shared entity IDs,
registry/device IDs and a user-renamed sensor. A pre-existing entity-ID
state-triggered automation executes after the reloads.

Local-only readings can be unavailable in Cloud and return under the same ID.
Events during a reload are not replayed. A separate Local-only entry can use a
different serial/identity path. This is not a browser-level test of custom cards,
and the user's specific earlier broken-widget symptom remains unresolved.

Diagnostics and identity coverage are bundled with the source-selection fix
for review convenience. They can be separated if a minimal race-only change is
preferred. This branch does not depend on the protocol-4 decoder.
