import base64

import pytest

from agent_server.persistence.secrets import mask_secret
from agent_server.secrets import SecretBox, SecretConfigurationError


def test_secret_box_round_trip_and_authenticated_context():
    box = SecretBox(b"k" * 32)
    ciphertext, nonce = box.encrypt("ghp_example", associated_data="user:github:token")

    assert box.decrypt(ciphertext, nonce, associated_data="user:github:token") == "ghp_example"
    with pytest.raises(Exception):
        box.decrypt(ciphertext, nonce, associated_data="other:github:token")


def test_secret_box_rejects_invalid_key():
    with pytest.raises(SecretConfigurationError):
        SecretBox(b"short")


def test_mask_secret_never_returns_full_value():
    assert mask_secret("ghp_1234567890abcd") == "ghp_****abcd"
    assert mask_secret("tiny") == "****"
