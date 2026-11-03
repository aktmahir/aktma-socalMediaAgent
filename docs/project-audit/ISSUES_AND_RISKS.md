# Issues and Risks

## Issue inventory

| ID | Severity | File(s) | Summary | Evidence |
| --- | --- | --- | --- | --- |
| ISS-001 | P0 | `social_media_agent/generator.py` | OpenAI path is using a deprecated SDK interface | `openai.ChatCompletion.create(...)` |
| ISS-002 | P0 | `social_media_agent/generator.py` | Hugging Face and Cohere auth headers are invalid | `"Authorization": f"******"` |
| ISS-003 | P0 | `social_media_agent/web.py`, `social_media_agent/scheduler.py` | invalid interval/input can break the app in production-like use | `parse_interval` raises `ValueError` and no catch is present |
| ISS-004 | P1 | entire repo | no automated tests or CI pipeline | repository scan shows no tests/files |
| ISS-005 | P1 | `social_media_agent/scheduler.py` | scheduler has no persistence or rescheduling state | while loop re-generates content without tracking status |
| ISS-006 | P1 | no auth layer | no user or service authentication | no login, session, or token system |
| ISS-007 | P1 | entire repo | no deployment or environment hardening | no Docker, no health checks, no production config |
| ISS-008 | P2 | `social_media_agent/web.py` | file upload flow is superficial and not real media-aware | files are stored only for naming and not processed |
| ISS-009 | P2 | entire repo | no operational logging or monitoring | no logs or metrics structures |
| ISS-010 | P2 | `social_media_agent/web.py` | debug mode enabled in local app starter | `app.run(debug=True, ...)` |

## Risk evaluation
### Critical risks
- Contract-breaking AI provider calls prevent the advertised feature from functioning as intended.
- Invalid user input can cause runtime exceptions that are not gracefully handled.
- Feature claims about AI provider support are not currently trustworthy.

### High risks
- no test suite means broken behavior is hard to detect
- no storage layer means scheduled tasks are not recoverable
- no deployment config means app cannot be produced safely for real use

### Medium risks
- file uploads are treated as simple filenames, not media assets
- there is no observability or telemetry
- debug mode is not suitable for live deployment exposure

## Mitigation priorities
1. repair provider SDK and auth logic
2. add real validation and error handling around user workflows
3. add automated test coverage for core generation logic
4. add persistence and queueing for periodic jobs
5. move from prototype to hardened runtime configuration
