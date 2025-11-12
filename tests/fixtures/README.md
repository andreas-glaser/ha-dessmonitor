# Fixture Guidelines

- Keep fixtures anonymized (strip usernames, passwords, serial numbers, GPS coordinates).
- Prefer small, representative payloads over full API dumps—only include fields referenced by tests.
- Name JSON fixtures with the structure `devcode_<XXXX>_<scenario>.json` so they can be discovered easily.
- Document the origin or reference issue/PR in a code comment within the test that loads the fixture.

Example usage:

```python
from tests.common import load_json_fixture

payload = load_json_fixture("devcode_2376_realtime.json")
```
