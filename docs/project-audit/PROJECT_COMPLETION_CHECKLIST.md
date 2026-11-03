# Project Completion Checklist

## Must-have business functionality
- [ ] local generation works without any external AI provider
- [ ] the selected platform produces an appropriate style of caption
- [ ] CLI generation works for text, image, and video scenarios
- [ ] web UI generation works and shows result details
- [ ] scheduled posts can be created and tracked reliably
- [ ] YouTube metadata generation behaves correctly when applicable

## Must-have technical requirements
- [ ] all external provider integrations are functional and tested
- [ ] environment variables and API keys are validated before runtime calls
- [ ] invalid input is caught and reported without crashes
- [ ] scheduler state is persisted and can be inspected
- [ ] logs and error reporting exist for operator visibility
- [ ] application startup is no longer configured for debug mode in production

## Quality and security requirements
- [ ] secret management is in place
- [ ] no hard-coded secret-like placeholders remain in runtime code
- [ ] input validation covers all public-facing forms and CLI arguments
- [ ] upload handling validates both extension and content safety
- [ ] access control is enforced if the app is exposed to multiple users
- [ ] dependency versions are pinned or managed through a lockfile

## Testing and validation requirements
- [ ] critical generation pathways have automated tests
- [ ] invalid input scenarios are covered
- [ ] scheduler lifecycle behavior is verified
- [ ] web endpoints or routes are smoke-tested
- [ ] production build or runtime start command is verified in a clean environment

## Operational readiness
- [ ] deployment documentation exists
- [ ] environment-specific configuration is separated and documented
- [ ] health checks or readiness checks are available
- [ ] backup strategy is documented for generated content and schedules if applicable
- [ ] known limitations are explicitly documented

## Completion gate
The project should only be treated as complete when all P0 and P1 items are resolved and critical user journeys have been validated end-to-end.
