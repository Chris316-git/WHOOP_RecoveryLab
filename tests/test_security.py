import pytest

from src.security import decrypt, encrypt, new_key


def test_round_trip_and_ciphertext_hides_plaintext():
    key = new_key()
    secret = '{"refresh_token": "abc123"}'
    token = encrypt(secret, key)
    assert "abc123" not in token
    assert decrypt(token, key) == secret


def test_wrong_key_is_a_clear_error():
    token = encrypt("x", new_key())
    with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY"):
        decrypt(token, new_key())
