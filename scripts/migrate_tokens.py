"""Copy local credentials (.tokens/) into the encrypted oauth_tokens table.

Run once before switching to TOKEN_STORE=db (needed for the scheduled cloud job):

    make migrate-tokens
"""
import _bootstrap  # noqa: F401

from src import config
from src.db.credentials import DbCredentialStore


def main() -> None:
    config.require("TOKEN_ENCRYPTION_KEY")
    moved = 0
    for provider, directory in (("whoop", config.WHOOP_TOKEN_DIR), ("google", config.GOOGLE_TOKEN_DIR)):
        store = DbCredentialStore(provider)
        for path in sorted(directory.glob("*.json")) if directory.exists() else []:
            store.save_json(path.stem, path.read_text())
            print(f"{provider}: stored credentials for user {path.stem}")
            moved += 1
    if not moved:
        raise SystemExit("Nothing to migrate: no files in .tokens/. Connect WHOOP and Google first.")
    print("\nDone. Now set TOKEN_STORE=db in .env so local runs and the cloud job share one store.")
    print("The files in .tokens/ can then be deleted.")


if __name__ == "__main__":
    main()
