# Connect Slack

Investigation reports can be posted to a Slack channel through an incoming
webhook. Each user configures their own destination; the webhook URL is
encrypted at rest and is never returned by the API. The environment variable
`SLACK_WEBHOOK_URL` is not used for delivery.

## Create an incoming webhook

1. In Slack, create or open an app and enable **Incoming Webhooks**.
2. Add a webhook for the channel that should receive investigation briefings.
3. Copy the webhook URL. Treat it as a credential: anyone who has it can post
   to your channel. Only `https://hooks.slack.com/services/...` URLs are
   accepted by the website.

## Configure the integration

1. Sign in to the DevOps Agent website and open **Settings → Integrations**.
2. Enter a display name and the incoming webhook URL.
3. Enable **Use this integration for investigation reports**.
4. Save the integration, then choose **Send test message** to verify delivery.
5. Confirm that a redacted test briefing appears in the Slack channel.

The integration is scoped to your account. Only investigations you own use it;
investigations created with the global Alertmanager token do not have a user
destination and are not posted to Slack.

## Behavior

- Destinations are resolved per investigation owner when the investigation
  finishes, so a disabled or deleted integration stops delivery immediately.
- Briefings are redacted and capped before posting. They include evidence IDs,
  ranked hypotheses when model analysis succeeded, and a read-only footer.
- A successful post sets `slack_posted_at` on the investigation. When no enabled
  integration exists, the briefing is logged locally and an audit event records
  that Slack delivery was skipped.
- Re-saving the integration replaces the stored URL. Deleting it removes the
  encrypted credential; existing reports are not changed.
