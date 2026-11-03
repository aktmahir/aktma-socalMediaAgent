# Functional Audit

## Current status

The project provides a small local workflow for generating social media content. It supports CLI and server-rendered Flask interfaces, external AI adapters, local fallback generation, file-name-based media context, and periodic JSON output. Phase 1 stabilizes provider request handling and rejects common invalid input. External provider integrations are covered by mocks, not live API calls.

## Feature assessment

| Feature | Status | Evidence / limitation |
| --- | --- | --- |
| CLI generation | Implemented | `app.py` validates topic and schedule arguments, then calls the generator. |
| Platform-specific generation | Implemented | Platform descriptions and allowed CLI/web values are defined in the application. |
| OpenAI generation | Implemented; mock-tested | Uses the current SDK client API; live API access has not been tested. |
| Hugging Face generation | Implemented; mock-tested | Sends Bearer auth and handles HTTP/API error responses with logged local fallback. Actual model availability is external. |
| Cohere generation | Implemented; mock-tested | Uses the v2 Chat endpoint and parses text content; live API access has not been tested. |
| Local fallback | Implemented | Returns caption, hashtags, CTA, and YouTube metadata without an external provider. Output uses randomized templates. |
| Web generation and scheduling | Implemented; route-tested | Flask test-client coverage exercises valid generation, invalid schedule feedback, and creation of a persisted scheduled job. |
| Input validation | Implemented for core fields | CLI, web, and scheduler validate topic, selection values, file extensions/signatures, counts, and intervals. This is not comprehensive abuse protection. |
| Upload support | Limited | Uploads are restricted to 5 MB, checked against allowlisted signatures and selected media type, and stored with random names. Contents are not processed, and no malware scanner is provided. |
| Scheduling | Implemented for local use | SQLite persists job configuration, status, progress, next-run time, failures, and output payloads. CLI supports lifecycle operations and opt-in supervision; a Windows script can register current-user logon startup. Per-job expiring leases prevent concurrent workers within the same database; unexpected generator exceptions receive up to three attempts. |
| YouTube metadata | Implemented | Title, description, and tags are included in output; provider response parsing falls back when malformed. |
| Automated tests | Implemented; CI configured | `python -m unittest discover -s tests -v`; Flask and scheduler coverage is included. GitHub Actions runs tests across Python 3.10–3.12. Provider integrations remain mocked. |
| Production deployment | Missing | No production deployment, authentication, rate limiting, database, or operational readiness configuration. |

## Phase 1 changes and verification

### Provider adapters

- OpenAI uses `OpenAI(...).chat.completions.create(...)`; no legacy `ChatCompletion.create` path remains.
- Hugging Face and Cohere use the configured API key as a Bearer token.
- Cohere uses `https://api.cohere.com/v2/chat`, sends a user message and JSON response format, and parses the v2 message content blocks.
- Provider transport and error-payload failures are logged and fall back to local generation.
- Mock tests cover successful response parsing and fallback behavior. Credentials and live provider service behavior remain unverified.

### Input and scheduling

- Shared schedule interval and count parsers reject malformed, empty, zero/negative interval, and negative/empty count values as applicable.
- CLI errors are reported through argparse; the web form returns status feedback; scheduler direct calls reject invalid interval seconds and counts.
- Empty topics and unsupported web select choices are rejected rather than sent to generation.
- Tests cover CLI parsing, scheduler validation/persistence/recovery, and valid/invalid Flask test-client submissions.

## Known limitations

- The local generator is a template-based fallback, not an AI model.
- Uploaded media is not inspected or understood by the generator.
- Signature checks only identify expected file headers; they do not fully parse files or scan for malware.
- Web schedules use daemon-thread workers that stop when the process exits; the SQLite job remains and can be recovered with `--run-scheduled JOB_ID` or the opt-in `--supervise-scheduled` CLI command. Windows task registration is explicit and current-user scoped.
- Leases prevent concurrent workers for one job in a shared SQLite database; separate databases are not coordinated. Unexpected generator exceptions are retried; provider/model failures use local fallback without automatic provider retries and count as successful generation. `generation_source` is included in scheduled JSON and supervisor output.
- Provider failure fallback is surfaced as local output and does not imply the external provider succeeded.
- There is no authentication or protection against repeated public requests; the web app is intended for local use.

## Functional conclusion

The core local use case is available with automated web and scheduler lifecycle coverage. The project remains a prototype: provider integrations need credentialed smoke tests, Windows unattended recovery requires explicit task registration, and production safeguards remain incomplete.
