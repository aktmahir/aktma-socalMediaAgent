# Implementation Roadmap

## Phase 1 — Critical Fixes and Stabilization

### Task ID: ROAD-01
- Description: Repair OpenAI SDK compatibility in `social_media_agent/generator.py`.
- Related issues: ISS-001
- Modules: `social_media_agent/generator.py`
- Expected outcome: OpenAI generation works with current SDK versions and returns valid post payloads.
- Dependencies: None
- Priority: P0
- Complexity: Medium
- Acceptance criteria: generating a post with a valid API key succeeds; no deprecated API calls remain.
- Verification: run a smoke test with mocked or live API credentials.

### Task ID: ROAD-02
- Description: Fix Hugging Face and Cohere request construction and authentication.
- Related issues: ISS-002
- Modules: `social_media_agent/generator.py`
- Expected outcome: actual API keys are used, auth headers are valid, and provider errors are handled gracefully.
- Dependencies: ROAD-01
- Priority: P0
- Complexity: Medium
- Acceptance criteria: each provider honors env credentials and returns JSON content; HTTP failures are surfaced clearly.
- Verification: hit each provider endpoint with a test key or mock response.

### Task ID: ROAD-03
- Description: Harden user input handling and scheduler validation.
- Related issues: ISS-003
- Modules: `social_media_agent/web.py`, `social_media_agent/scheduler.py`, `app.py`
- Expected outcome: invalid intervals, empty counts, or malformed inputs are rejected with meaningful messages instead of crashes.
- Dependencies: ROAD-02
- Priority: P0
- Complexity: Low
- Acceptance criteria: invalid schedule entries return validation errors or warnings; no uncaught exceptions.
- Verification: UI and CLI tests for invalid input cases.

## Phase 2 — Core Feature Completion

### Task ID: ROAD-04
- Description: Build a minimal automated test suite for the generator and scheduler.
- Related issues: ISS-004
- Modules: repository root and test folder
- Expected outcome: basic unit tests cover generator fallback, hashtag creation, and scheduler output file generation.
- Dependencies: ROAD-03
- Priority: P1
- Complexity: Medium
- Acceptance criteria: tests run in CI and fail on regressions.
- Verification: `pytest` or equivalent suite run in CI.

### Task ID: ROAD-05
- Description: Add persistence and job state tracking for scheduled posts.
- Related issues: ISS-005
- Modules: `social_media_agent/scheduler.py`; new persistence layer if needed
- Expected outcome: scheduled jobs have status, tracking, and recoverability.
- Dependencies: ROAD-04
- Priority: P1
- Complexity: High
- Acceptance criteria: scheduler can be paused, resumed, and inspected; state is retained between app restarts.
- Verification: simulate scheduling lifecycle and confirm persisted job records.

### Task ID: ROAD-06
- Description: Add authentication and authorization layers for a multi-user or shared environment.
- Related issues: ISS-006
- Modules: new auth module, web app session layer
- Expected outcome: access control is enforced and credentials are not exposed through shared app state.
- Dependencies: ROAD-05
- Priority: P1
- Complexity: High
- Acceptance criteria: protected routes or tasks require identity and enforce permissions.
- Verification: manual auth flow check and route-level tests.

## Phase 3 — Integration and Data Reliability

### Task ID: ROAD-07
- Description: Improve media upload processing beyond filename passes-through.
- Related issues: ISS-008
- Modules: `social_media_agent/web.py`, upload handling logic
- Expected outcome: file validation, storage strategy, and media-aware prompt generation are defined.
- Dependencies: ROAD-06
- Priority: P2
- Complexity: Medium
- Acceptance criteria: uploaded files are validated, stored safely, and optionally used meaningfully in generation.
- Verification: upload different media types and check saved files and prompt behavior.

### Task ID: ROAD-08
- Description: Add structured logging, monitoring, and error reporting.
- Related issues: ISS-009
- Modules: application runtime and config
- Expected outcome: logs capture request context, provider failures, and scheduler events.
- Dependencies: ROAD-05
- Priority: P2
- Complexity: Medium
- Acceptance criteria: logs include relevant identifiers and operational context; failures are visible to operators.
- Verification: trigger generation and scheduler failures and inspect logs.

## Phase 4 — UX and Product Completeness

### Task ID: ROAD-09
- Description: Improve web UI feedback, user guidance, and state management.
- Related issues: ISS-003, ISS-008
- Modules: `social_media_agent/templates/index.html`, `social_media_agent/web.py`
- Expected outcome: status feedback is clear, errors are visible, and successful flows are easy to understand.
- Dependencies: ROAD-03
- Priority: P2
- Complexity: Low
- Acceptance criteria: users can understand the generation result, scheduler status, and error states without reading code.
- Verification: manual browser-based validation.

## Phase 5 — Production Readiness

### Task ID: ROAD-10
- Description: Add deployment configuration and security hardening.
- Related issues: ISS-007, ISS-010
- Modules: Docker, environment templates, runtime config
- Expected outcome: project has safe runtime settings, env separation, and deployment documentation.
- Dependencies: ROAD-08, ROAD-09
- Priority: P1
- Complexity: Medium
- Acceptance criteria: app can be started in a controlled environment with production-safe configuration and no debug exposure.
- Verification: run app in a test environment and check startup logs and config behavior.

## Completion criteria by phase
- Phase 1: provider integrations are stable and validated
- Phase 2: generated content and scheduler workflows are covered by tests and state management
- Phase 3: data reliability and operational safeguards are in place
- Phase 4: UI and UX are coherent for end users
- Phase 5: deployment readiness and security controls are verified

## Overall roadmap order
1. fix provider integrations
2. validate inputs and scheduler stability
3. add tests and persistence
4. improve UX and media processing
5. add operations and deployment hardening
