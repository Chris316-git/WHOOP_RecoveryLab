"""Symmetric encryption for credentials stored in the database (Fernet: AES-128-CBC + HMAC).

Generate a key once with `make gen-key` and keep it in .env and in GitHub Secrets.
Losing the key means re-authorizing WHOOP and Google; leaking it exposes the tokens.
"""
from cryptography.fernet import Fernet, InvalidToken

from src import config


def new_key() -> str:
    return Fernet.generate_key().decode()


def _fernet(key: str | None = None) -> Fernet:
    return Fernet((key or config.require("TOKEN_ENCRYPTION_KEY")).encode())


def encrypt(plaintext: str, key: str | None = None) -> str:
    return _fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str | None = None) -> str:
    try:
        return _fernet(key).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Could not decrypt stored credentials: TOKEN_ENCRYPTION_KEY does not match.") from None
