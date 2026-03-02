# Epic 3 Validation Evidence — Gate-Based Runbook

This file is the operational evidence template for Epic 3 validation.
It follows the mandatory 3-gate policy:

1. Gate 1 — Isolated tests in `tests/`
2. Gate 2 — Mocked integration E2E with real WS + real audio path
3. Gate 3 — Short human pilot sessions with objective checklist

---

## 1) Environment Preconditions

- Run from: `A:/hackaton-google/tests`
- Python environment active and dependencies installed
- For quota-consuming tests (`slow`), ensure API key/project permissions are configured

Suggested setup:

```bash
cd A:/hackaton-google/tests
uv run pytest --version
```

---

## 2) Commands by Gate

## Gate 1 — Isolated Validation (required)

Core Epic 3 isolated suite:

```bash
uv run pytest -q test_epic3_orchestration.py test_epic3_frontend_validation_simulation.py
```

Existing media baseline tests (non-slow):

```bash
uv run pytest -q -m "not slow"
```

Optional direct media checks:

```bash
uv run pytest -q test_imagen_generation.py
uv run pytest -q test_video_generation.py -m slow
```

## Gate 2 — Mocked Integration E2E (required before concept acceptance)

Reference story: `validation-integration-mocked-story.md`

Run the mocked integration suite:

```bash
uv run pytest -q test_epic3_integration_mocked.py
```

Expected focus:
- real `ws/live` connection
- real audio runtime path
- mocked media service delays (5s image / 30s video)
- ordering/fallback assertions

## Gate 3 Preflight — Pilot Mock Validation (automated)

Validates the `PilotMockGeminiLiveStream` through the real bridge before human sessions:

```bash
uv run pytest -q test_pilot_mock_stream.py -v
```

Expected: **8 passed** (tone generation, event ordering, audio continuity, large payloads, metrics, clean close)

## Gate 3 — Human Pilot Sessions (required before concept acceptance)

Full plan: `docs/hands-on/tracer_bullet_day4/validation-epic3/tests_pilot_human.md`

Start backend in pilot mode, then run real sessions:

```bash
$env:ANIMISM_LIVE_MODE = "pilot"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
```

Mandatory minimum:
- at least 3 sessions
- each session must pass all objective criteria

---

## 3) Approval Matrix by Gate

Use `PASS`, `FAIL`, or `PENDING`.

| Gate | Scope | Evidence Source | Status | Date | Owner | Notes |
|---|---|---|---|---|---|---|
| Gate 1 | Isolated tests (`tests/`) | pytest output + generated artifacts in `tests/output/` | PASS | 2026-03-02 | Copilot/Matheus | `7 passed` on Epic 3 isolated suite |
| Gate 2 | Mocked integration E2E (real WS + audio, mocked media) | integration test logs + timing/ordering assertions | PASS | 2026-03-02 | Copilot/Matheus | `9 passed` on Gate 2 suite (`test_epic3_integration_mocked.py`) — real bridge, zero errors |
| Gate 3 preflight | Pilot mock through real bridge (automated) | pytest output | PASS | 2026-03-02 | Copilot/Matheus | `8 passed` on `test_pilot_mock_stream.py` — validated before human sessions |
| Gate 3 | Human pilot sessions (>=3) | session checklists + operator notes | IN PROGRESS | 2026-03-02 | Matheus + Amelia | Session 1: PASS (49.32s, 0 errors). Sessions 2 and 3: PENDING |

---

## 4) Human Pilot Session Checklist (Gate 3)

Repeat this block for each session.

### Session Template

- Session ID:
- Date/Operator:
- Duration:
- No dead air observed: `PASS | FAIL`
- Correct fallback when delay `>30s`: `PASS | FAIL | N/A`
- No audible underflow artifacts: `PASS | FAIL`
- Narrative continuity during pending media: `PASS | FAIL`
- Final result: `PASS | FAIL`
- Notes / edge cases:

### Session 1 (completed)

- Session ID: `b709dc38-9755-4643-abb8-818b50dc243a`
- Date/Operator: 2026-03-02 / Matheus
- Duration: 49.32s
- No dead air observed: `PASS` — 517 tone responses over 49s
- Correct fallback when delay `>30s`: `N/A` — frontend doesn't log media events; backend `downstream_text_count: 5` confirms forwarding
- No audible underflow artifacts: `PASS`
- Narrative continuity during pending media: `PASS` — tones continued across all scenario phases
- Final result: `PASS`
- Notes: Audio = repetitive tone (expected — mock uses sine wave, not AI speech). Setup latency 277ms. `errors: 0`. Full analysis in `docs/hands-on/tracer_bullet_day4/validation-epic3/tests_pilot_human.md`.

### Session 2 (pending)

*(To be filled — Amelia)*

### Session 3 (pending)

*(To be filled — Amelia)*

---

## 5) Concept Acceptance Rule (Hard Gate)

Declare **"concept met"** only when:

- Gate 2 is `PASS`, and
- Gate 3 has at least 3 sessions, all with final result `PASS`.

If either condition is missing, concept status remains: `NOT YET MET`.

