# User-managed integrations for report delivery

Status: accepted

Incident investigation briefings were delivered to a single Slack incoming
webhook read from `SLACK_WEBHOOK_URL` by the worker process. This tied every
user's reports to one process-wide destination and made the browser UI unable
to express whether delivery was configured or enabled.

## Decision

Slack is now a user-owned integration. Credentials are stored in an
`integrations` table as AES-256-GCM ciphertext using the existing `SecretBox`
and `ENCRYPTION_KEY`. The worker resolves the destination from the
investigation's owner immediately before delivery, through a small resolver
interface. Reports are posted only when an enabled integration exists.

The environment variable is deliberately no longer a delivery source:
`SlackPoster` requires an explicit URL. Investigations owned by `system` do not
post to Slack.

## Consequences

- Integrations are scoped to users and cannot leak across accounts.
- Adding another destination provider requires a new provider value and a
  resolver, not changes to the investigation runner.
- `ENCRYPTION_KEY` is required for Slack integrations to work; without it the
  API reports secret storage as unavailable and the worker logs a warning.
- Enabling or deleting an integration affects only future report delivery;
  already stored reports and audit records are unchanged.
