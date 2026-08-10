# Task Log — group-review-gap-outcome

## Task 1 — Backend: gap endpoint + service + demo-reset  ✅ (2026-08-10)

Branch `feat/group-review-gap-outcome` (0 commits; work in the working tree). Start gate satisfied:
P4 merged as `705e61c`, branch based on the post-P4 `main`.

### Changes

| File | What |
|---|---|
| `backend/app/curation/service.py` | `VALID_SCHEMA_GAP_TYPES` whitelist; `record_group_gap()`; new `_group_possible_schema_gap()` helper (see Deviation 1) |
| `backend/app/schemas/curation.py` | `SchemaGapRequest` |
| `backend/app/api/routes_review.py` | `POST /admin/review/groups/{group_id}/gap` via `_as_api_error` |
| `scripts/reset_demo_review.py` | `_reset_schema_gaps()` — demo `schema_gap` items → `proposed`, one audit row per group |
| `backend/tests/integration/test_review_groups.py` | 6 new tests (all of condition 4) |

### Deviation 1 (in scope, required) — gate flag was not threaded

`record_group_gap` as drafted evaluated the gate on `_proposal_from_items(proposed)` alone. The
`needs_schema_extension` verdict comes from `possible_schema_gap`, which `list_groups` injects from
each item's `schema_check.group_possible_schema_gap` — `_proposal_from_items` does not carry it.
Measured on the seeded `group:demo_schema_gap`:

```
approve_group sees (no flag): pass
queue/UI + gap endpoint see : needs_schema_extension
```

So the D2 guard would have returned 409 for **every** genuine gap group — the feature could never
fire. Fixed by extracting `_group_possible_schema_gap(items)` from `list_groups` (behaviour
unchanged there) and applying it in `record_group_gap`. No third copy of the logic.

### Deviation 2 — `approve_group` had the same hole (fixed, owner-approved scope extension)

The same missing flag existed in `approve_group`: a group the queue and the UI show as
`needs_schema_extension` evaluated as `pass` inside `approve_group`, so the API **approved it and
wrote it to Neo4j** — the gate was enforced by a disabled frontend button only, contradicting the
enforcing-gate property asserted by `test_approve_refuses_when_schema_gate_fails` (H2).

The plan's stop conditions list "changes to approve/reject", so this was raised rather than
silently fixed; **owner approved folding it into this change (2026-08-10)**. Fix = the same helper
applied in `approve_group`, plus `test_approve_refuses_a_flagged_schema_gap_group`.

Proven to be a genuine regression test, not a tautology — run against the pre-fix code it fails:

```
tests/integration/test_review_groups.py::test_approve_refuses_a_flagged_schema_gap_group
E   Failed: DID NOT RAISE <class 'app.curation.service.CurationError'>
```

That failing run wrote the group into Neo4j (the bug), which the fixture teardown did not cover —
`_NODE_IDS` now includes the gap-group members so a future regression cleans up after itself.

### Guard order deviation (minor)

`reviewer` and `schema_gap_type` are validated before opening the connection, so a bad payload on an
unknown group returns 422 rather than the plan's 404. Cheaper (no DB round-trip) and tests assert the
actual order.

### Verification

Targeted, offline posture (`-e OPENAI_API_KEY=`):

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_review_groups.py -q
  → 20 passed in 32.99s  (13 pre-existing + 7 new)
```

Full suite, **online** (owner topped up the OpenAI account mid-task; real embeddings, not the
lexical fallback):

```
make seed  → success: 45 nodes, 84 edges, 5 documents, 9 chunks, 5 demo review groups
make test  → 170 passed in 273.40s   (P4 baseline 163 + 7 new; zero failures)
```

The documented `test_pipeline_run_is_idempotent` flake did **not** reproduce on this run (the volume
was re-seeded first).

```
ruff 0.15.21 check + format --check (LINT_PATHS) → All checks passed! / 99 files already formatted
mypy backend/app ingestion scripts               → Success: no issues found in 77 source files
```

End-to-end round trip on real seed data (acceptance #1, #6):

```
seed → queue lists group:demo_schema_gap, gate = needs_schema_extension
record_group_gap(..., 'permissive_effect') → {'status': 'schema_gap', ...}; group leaves the queue
make demo-reset → {'reset_schema_gap_groups': 1} → group back in the queue
```

Two pre-existing environment quirks, unrelated to this change and left alone:
`mypy` is not in the backend image (`make lint` runs it on the host, so it ran on the host), and
`scripts/wait_for_services.sh` polls port 8000, which `docker-compose.yml` does not expose — it times
out while the stack is in fact healthy; `make health` (via nginx on 8080) is the working check.

Committed as `ddaf281` (later rebased onto `main` @ `da2eed2`, after PR #14 repo/CI hardening).

## Task 2 — Frontend: 記為 gap  ✅ (2026-08-10)

- `frontend/app.js`: `GAP_OPTIONS` re-added (verbatim from `docs/schema-gap-policy.md`);
  `reviewActions` renders the gap `<select>` + 記為 gap button **only** for `needs_schema_extension`.
  All actions share a `buttons` array — disabled together on click (double-click cannot fire twice),
  re-enabled on failure (`approve` still respects the gate).
- `frontend/styles.css`: `.ex-gap-hint`, `.ex-gap-row`, `.ex-gap-select`.
  `.ex-gap-select` deliberately sets no `color`: the neighbouring `.sb-row select` uses
  `var(--text)`, which is **not defined** in `:root` — a pre-existing no-op, not fixed here.
- `frontend/index.html`: `?v=20260810-1` on both `app.js` and `styles.css`.

**Copy added beyond the plan.** The plan specified only a `<select>` + button. Shown the result, the
owner (the domain expert) found the bare dropdown meaningless — "是要他選擇最接近的一個？還是這是
llm 解析出來的內容？". Added: an instruction line above the select, and a gap-specific placeholder on
the reason textarea explaining that the free-text description is the substantive part (it lands
verbatim in the audit row). The taxonomy option text itself is unchanged.

Verified: `node --check` OK, plus the HTTP-level equivalents of the browser scenarios (409 on a pass
group with the documented message, 422 on a bogus type, 200 + queue removal on a real record,
re-armed by `make demo-reset`). **Browser pass completed by the owner — 4/4, every scenario
cross-checked in Postgres** (see `VERIFICATION_REPORT.md`). Scenario ② was re-designed mid-run: the
"stop the backend" recipe leaves no list to click on, so it became a two-tab stale-view test that
exercises the same failure path and additionally proves two racing reviewers cannot duplicate an
audit row.

## Task 3 — Docs + full verification  ✅ (2026-08-10)

- `docs/api_contract.md`: the endpoint, its four guards, the 6-value taxonomy, the
  single-transaction property, and an explicit note that there is no backlog view yet.
- `docs/schema-gap-policy.md`: its header claimed gaps are written to
  `data/sample/expert_demo/schema_gap_backlog.json` — never true of this path. Now documents the
  real landing place (`graph_change_logs` `action='schema_gap'`) and marks the JSON as legacy.
- `make test` → **170 passed in 283.77s**; ruff check + format clean; mypy clean (77 files);
  `node --check` OK.
- `VERIFICATION_REPORT.md` + `CHANGE_REPORT.md` produced.

### Raised for later (not implemented)

Structured gap expression (`節點 —(新關係)→ 節點`) and node dropdowns on the hand-made builder — see
`CHANGE_REPORT.md`.
