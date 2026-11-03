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
| Web generation | Implemented; not route-tested | Flask form renders generation results and status feedback; automated Flask test-client coverage is still needed. |
| Input validation | Implemented for core fields | CLI, web, and scheduler validate topic, selection values, file extensions, counts, and intervals. This is not comprehensive abuse protection. |
| Upload support | Limited | Files are stored locally and their names enter the prompt; contents are not processed. Extension checks do not inspect file contents. |
| Scheduling | Prototype | A background/in-process loop writes JSON files; there is no persistence, job status API, pause/resume, or restart recovery. |
| YouTube metadata | Implemented | Title, description, and tags are included in output; provider response parsing falls back when malformed. |
| Automated tests | Present | `python -m unittest discover -s tests -v`; provider integrations are mocked. No CI workflow is configured. |
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
- Tests cover CLI parsing and scheduler guards. The Flask route still needs automated test-client coverage.

## Known limitations

- The local generator is a template-based fallback, not an AI model.
- Uploaded media is not inspected or understood by the generator.
- Web schedules are daemon-thread jobs and disappear when the process exits.
- Provider failure fallback means a successful local result does not imply the external provider succeeded.
- There is no authentication or protection against repeated public requests; the web app is intended for local use.

## Functional conclusion

The core local use case is available and the Phase 1 critical paths have regression tests. The project remains a prototype: provider integrations need credentialed smoke tests, web request paths need route tests, and scheduling lacks durable lifecycle management.
