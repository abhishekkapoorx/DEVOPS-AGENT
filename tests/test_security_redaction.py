from agent_protocol import redact_secrets


def test_secret_fields_are_redacted_recursively_without_exposing_keyed_values():
    assert redact_secrets(
        {
            "credentials": {"password": "plain-value", "api_key": "plain-key"},
            "message": "Authorization: Bearer abc.def.ghi",
            "label": "safe",
        }
    ) == {
        "credentials": {"password": "[REDACTED]", "api_key": "[REDACTED]"},
        "message": "Authorization: Bearer [REDACTED]",
        "label": "safe",
    }
