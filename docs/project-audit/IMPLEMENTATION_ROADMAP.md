# Implementation Roadmap

## Phase 1 — Critical Fixes and Stabilization

### ROAD-01 — OpenAI SDK compatibility
- **Status:** Implemented; mock-tested.
- **Description:** Use the current OpenAI Python SDK client interface.
- **Module:** `social_media_agent/generator.py`
- **Acceptance:** No legacy `ChatCompletion.create` path remains; mocked success and failure tests verify response handling and local fallback.
- **Remaining verification:** Live request with valid credentials and a currently accessible model.

### ROAD-02 — Hugging Face and Cohere request construction
- **Status:** Implemented; mock-tested.
- **Description:** Use configured Bearer tokens, current request/response shapes, and visible fallback logging.
- **Modules:** `social_media_agent/generator.py`
- **Acceptance:** Mock tests verify authentication, response parsing, HTTP failure handling, and API error payload fallback. Cohere uses v2 Chat and JSON response format.
- **Remaining verification:** Live credentialed requests and provider-side model availability. Hugging Face availability depends on the configured model and currently available inference service.

### ROAD-03 — User input and scheduler validation
- **Status:** Core checks implemented; CLI/scheduler tests added; web route tests outstanding.
- **Description:** Reject malformed topics, options, intervals, counts, and unsupported upload extensions, and guard scheduler direct calls.
- **Modules:** `app.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py`
- **Acceptance:** CLI reports invalid arguments with parser errors; web form returns status feedback; scheduler rejects invalid interval seconds and negative counts.
- **Remaining verification:** Flask test-client tests for valid and invalid form submissions.

## Phase 2 — Core Feature Completion

### ROAD-04 — Automated tests and CI
- **Status:** Partially implemented.
- **Description:** Expand regression coverage to the scheduler and generator and run it automatically.
- **Modules:** `tests/`, CI configuration.
- **Current state:** `unittest` regression tests cover local fallback, OpenAI/Hugging Face/Cohere mocks, provider failures, and schedule validation.
- **Remaining:** Scheduler output-file lifecycle tests, Flask route coverage, and a CI workflow.

### ROAD-05 — Persistent scheduling
- **Status:** Not started.
- **Description:** Add durable job records, lifecycle state, and recovery.
- **Acceptance:** Jobs can be inspected, paused/resumed, and recovered after restart.

### ROAD-06 — Authentication and authorization
- **Status:** Not started; required only if shared deployment is in scope.
- **Description:** Protect user-facing routes and separate user/job ownership.
- **Acceptance:** Enforced identity and permissions with route-level tests.

## Phase 3 — Integration and Data Reliability

### ROAD-07 — Media upload processing
- **Status:** Not started.
- **Description:** Define safe storage and actual media-aware processing; current implementation only saves files and passes filenames to prompts.

### ROAD-08 — Operational logging and monitoring
- **Status:** Partially implemented.
- **Description:** Provider failures are logged. Add structured request/job context, scheduler logs, metrics, and operational error reporting.

## Phase 4 — UX and Product Completeness

### ROAD-09 — Web feedback and state
- **Status:** Basic status feedback is present; deeper state and route tests remain.
- **Description:** Ensure validation errors, generation results, and scheduling status are clear and consistently styled.

## Phase 5 — Production Readiness

### ROAD-10 — Deployment and security hardening
- **Status:** Not started.
- **Description:** Add production server configuration, environment separation, health checks, and protections appropriate to the exposure model. Flask debug mode is disabled and the local runner binds to localhost, but this is not a production deployment setup.

## Phase completion criteria

- **Phase 1:** Provider adapters and basic input/schedule checks are implemented and mock-tested; live provider and web route validation remain.
- **Phase 2:** Core behavior has broad test coverage and scheduled jobs have durable state.
- **Phase 3:** Upload/data handling and operational controls are reliable.
- **Phase 4:** The UI presents clear, tested workflows.
- **Phase 5:** Deployment and security controls are verified for the target environment.

## Recommended next actions

1. Add Flask test-client tests covering valid and invalid submissions.
2. Run credentialed smoke tests for OpenAI, Hugging Face, and Cohere using supported models.
3. Decide if persistence and shared deployment are required before building job state or authentication.
4. Add CI and production safeguards before external exposure.
