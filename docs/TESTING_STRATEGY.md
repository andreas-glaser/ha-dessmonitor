# DessMonitor Test Guide

This guide explains how the DessMonitor tests are organized, how to run them locally or in CI, and what is expected when you add new coverage. Treat it as the single place to learn “how testing works” in this repo.

---

## 1. Quick Start

```bash
# 1. Create/activate your venv (example)
python3 -m venv .venv && source .venv/bin/activate

# 2. Install runtime + dev deps
pip install -r requirements.txt

# 3. Install the test stack
pip install -r requirements_test.txt

# 4. Run everything
make test        # same command CI uses
```

Helpful variations:

- `pytest tests/unit` – fastest feedback for pure functions.
- `pytest tests/components/dessmonitor/test_sensor_entities.py -k devcode_6422`.
- `pytest --maxfail=1 --durations=10` – match CI flags locally.

---

## 2. Tooling & Requirements

| Layer | Primary tooling | Notes |
|-------|-----------------|-------|
| Test runner | `pytest`, `pytest-asyncio` | Async tests default to `mode=auto` (`pytest.ini`). |
| Home Assistant harness | `pytest-homeassistant-custom-component` | Provides the HA test core + `MockConfigEntry`. |
| HTTP / API mocking | `aresponses` | Intercepts async HTTP calls from the DessMonitor API client. |
| Time travel | `freezegun` | Stabilizes timestamps for accumulating counters. |
| Coverage | `pytest-cov` (optional) | Run with `pytest --cov=custom_components/dessmonitor`. |

All of the above are pinned inside `requirements_test.txt` so local runs and CI stay in sync. Use `PIP_EXTRA_INDEX_URL=https://wheels.home-assistant.io/mypy-dev/` when installing if your environment cannot resolve HA wheels automatically (CI already does this).

---

## 3. Suite Layout

```
tests/
├── conftest.py                  # event loop policy, global fixtures
├── common.py                    # load_json_fixture, dummy Store, auth helpers
├── fixtures/                    # sanitized payloads
│   ├── devcode_2361_realtime.json
│   └── devcode_2376_summary.json
├── unit/                        # pure Python logic
│   ├── test_device_registry.py
│   └── test_utils.py
└── components/dessmonitor/      # HA integration tests
    ├── conftest.py              # MockConfigEntry, API patching
    ├── test_config_flow.py
    ├── test_init.py
    └── test_sensor_entities.py
```

---

## 4. What Each Layer Covers

### Unit & Pure Functions
- Targets: `custom_components/dessmonitor/device_support/*`, `utils.py`, value transforms, UUID/signature helpers.
- Style: synchronous pytest tests, no HA harness required.
- Goal: when a mapping table changes, failures point exactly at the transformation.

### API Client
- Targets: `DessMonitorAPI` (auth handshake, token caching, retries, masking utilities).
- Tools: `pytest.mark.asyncio` + `aresponses` to fake the DessMonitor HTTP endpoints.
- Expectations: validate both happy-path (200) and error handling (timeouts, malformed payloads).

### Home Assistant Integration
- Targets: setup/unload flows, entity registry, sensor metadata, diagnostics.
- Tools: `pytest-homeassistant-custom-component`, `MockConfigEntry`, fixture payloads to drive the data coordinator.
- Expectations: assert entities created, device info, unique IDs, operating mode enums, and that unload cleans up.

### Regression Fixtures
- Purpose: capture anonymized CLI exports per devcode (`devcode_<XXXX>_<scenario>.json` under `tests/fixtures/`).
- Usage: both HA and unit tests read them via `tests.common.load_json_fixture`.
- Requirement: strip usernames/passwords/serials; document fixture origin in the test that consumes it.

### CLI / Tooling (optional but encouraged)
- Targets: `tools/cli/dessmonitor_cli.py`.
- Method: monkeypatch the API class to return canned payloads and assert command output/exit codes.

---

## 5. Adding or Updating Tests

1. **Collect Data**
   - Run `python3 tools/cli/dessmonitor_cli.py analyze --device-sn ... --output my_payload.json`.
   - Sanitize the file (no emails, serials, tokens) and drop it in `tests/fixtures/devcode_<XXXX>_<scenario>.json`.

2. **Extend Device Coverage**
   - Update or create tests under `tests/unit/` if you added new transforms or enums.
   - For new sensor mappings, add/extend HA tests under `tests/components/dessmonitor/`.

3. **Leverage Shared Helpers**
   - Use `load_json_fixture("devcode_6422_realtime.json")`.
   - Reuse `make_mock_entry` / `patch_dessmonitor_api` helpers provided by the HA `conftest.py`.

4. **Run Focused Tests**
   ```bash
   pytest tests/unit/test_device_registry.py -k 6422
   pytest tests/components/dessmonitor/test_sensor_entities.py -k inverter_temperature
   ```

5. **Update Docs/Changelog When Needed**
   - Mention new fixtures or coverage in `CHANGELOG.md` if user-facing.
   - Keep `docs/TESTING_STRATEGY.md` in sync if you change the process.

---

## 6. Commands & Configuration

- `make test` – installs test deps (if needed) and executes `pytest`.
- `make test-docker` (if defined) – consistent run inside the project’s Docker image.
- `pytest.ini` – sets HA log level, asyncio mode, and registers markers such as `integration` or `cli`.
- `requirements_test.txt` – single source of truth for the pytest stack; update pins here and sync CI.

---

## 7. Continuous Integration

The GitHub Actions workflow `.github/workflows/tests.yaml` runs after linting:

1. Setup Python 3.12 (or the HA-supported version noted in `pyproject.toml`).
2. Install dependencies using `pip install -r requirements.txt -r requirements_test.txt`.
3. Execute `pytest --durations=10 --maxfail=1`.
4. Upload coverage artifacts when the optional `COVERAGE` flag is enabled.

To debug CI failures locally, replicate the exact command printed in the workflow logs—usually a straight copy of the line above.

---

## 8. Troubleshooting

- **`ImportError: cannot import name 'homeassistant'`**: ensure test requirements are installed inside the active venv.
- **`aiohttp.client_exceptions.ClientConnectorError` in tests**: confirm the API client is patched/mocked; missing `aresponses` yields real HTTP attempts.
- **Fixture not found**: run `python -m pytest -vv` to see the full path; remember fixture names are relative to `tests/fixtures/`.
- **Async warnings**: verify `pytest.ini` still sets `asyncio_mode = auto` and that tests use `pytest.mark.asyncio`.

Keep tests deterministic (frozen time, stable fixture data) so contributors can reproduce failures quickly on any machine.
