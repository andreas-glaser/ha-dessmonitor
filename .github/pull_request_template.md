# What this changes

<!-- One or two sentences. Link the issue it answers: "Closes #NN". -->

## Evidence

<!--
Delete this section if the change touches no devcode profile.

A new or changed devcode profile needs the reporter's diagnostics download
committed under docs/evidence/devcodes/. That file is what guards the profile:
tests/test_analysis_coverage.py reads it and fails when a reading that carries
a unit stops resolving. Without it nothing defends the mapping, which is how
devcode 6514 shipped resolving its state of charge and nothing else and dropped
58 of its 76 titles until two reporters noticed, eight months apart.

    .venv/bin/python tools/evidence_from_diagnostics.py <the download>

Either "Download diagnostics" button produces a usable file - the integration
entry's or the inverter's own device page.
-->

- [ ] The diagnostics download is committed under `docs/evidence/devcodes/`
- [ ] `.venv/bin/python tools/analysis_coverage.py <the evidence file>` output
      is pasted below

<!-- Paste the coverage output here. -->

## What an existing installation sees

<!--
Over 13,000 installations run this integration and none of them can be tested
from here, so say which of these it is:

- Additive only: a new sensor key, a new devcode profile, a new declaration.
  Nothing an installation already publishes changes.
- It moves, renames, or changes the unit, state class, category or options of
  an entity that already exists. Then it needs its own CHANGELOG entry and an
  upgrade note saying what an owner will see.
-->

## Verification

<!--
What you ran and what it printed. `make test` and `make lint` both pass before
a merge. If something cannot be verified by the test suite - local mode against
real hardware, a cloud write - say so plainly rather than describing it as
verified.
-->
