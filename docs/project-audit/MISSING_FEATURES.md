# Missing Features and Incomplete Functionality

## Inventory

| ID | Feature / Module | Status | Priority | Impact |
| --- | --- | --- | --- | --- |
| MF-001 | OpenAI SDK compatibility | Broken | P0 | Critical |
| MF-002 | Hugging Face and Cohere auth integration | Broken | P0 | Critical |
| MF-003 | Input validation and error handling in web scheduler | Incomplete | P0 | Critical |
| MF-004 | Automated tests and CI | Missing | P1 | High |
| MF-005 | Persistent storage and job tracking | Missing | P1 | High |
| MF-006 | Authentication and authorization | Missing | P1 | High |
| MF-007 | Production deployment config | Missing | P1 | High |
| MF-008 | Real media analysis for uploads | Placeholder | P2 | Medium |
| MF-009 | Structured logging and monitoring | Missing | P2 | Medium |
| MF-010 | Operational security hardening | Missing | P1 | High |

## Details

### MF-001 — OpenAI SDK compatibility
The project relies on `openai.ChatCompletion.create`, which is not compatible with the modern OpenAI Python SDK. The feature is present in code, but it is functionally broken for current SDK versions.

### MF-002 — Provider auth integration for Hugging Face and Cohere
The code produces placeholder auth headers instead of using actual credentials. This means the provider integrations cannot send valid requests.

### MF-003 — Web input validation
The web endpoint accepts intervals and counts without robust handling for invalid values, exception capture, or user-facing validation. This is a reliability and usability issue.

### MF-004 — Automated tests and CI
There are no test files or project-level validation commands. This blocks confidence in future changes and makes regressions likely.

### MF-005 — Persistent storage and job tracking
Scheduled jobs are not persisted, and there is no system for resuming, monitoring, or retrying generation jobs. This limits reliability and operational control.

### MF-006 — Authentication and authorization
The project has no user management or permission model. This is acceptable for a local demo, but not for a genuine product or multi-user environment.

### MF-007 — Production deployment config
No Docker, health checks, deployment templates, environment layering, or runtime configuration management are present.

### MF-008 — Real media analysis
Uploaded image or video files are stored locally but are never processed or analyzed. The feature is currently a file upload UI with no substantive business value beyond naming the media in the prompt.

### MF-009 — Logging and monitoring
There are no operational logs, metrics, or sentry-like instrumentation. This makes production diagnosis difficult.

### MF-010 — Operational security hardening
No secret management, rate limiting, abuse protections, or secure configuration patterns are implemented.

## Recommended priority ordering
1. Fix API integrations and runtime compatibility
2. Add validation, logging, and safe error handling
3. Add tests and CI coverage
4. Add persistent scheduling and job state
5. Add deployment and env-hardening controls
6. Upgrade UX and media processing capabilities
