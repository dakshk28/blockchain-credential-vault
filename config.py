import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


DEFAULT_SECRET = "development-only-change-me"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql+psycopg://acv:acv@localhost:5432/credential_vault")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
    UPLOAD_DIRECTORY = Path(os.environ.get("UPLOAD_DIRECTORY", BASE_DIR / "instance" / "private_uploads"))
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL") or "memory://"
    OBJECT_STORAGE_MODE = os.environ.get("OBJECT_STORAGE_MODE", "local")
    REDIS_URL = os.environ.get("REDIS_URL", "")
    SIGNING_SECRET = os.environ.get("SIGNING_SECRET", SECRET_KEY)
    BLOCKCHAIN_ANCHOR_PROVIDER = os.environ.get("BLOCKCHAIN_ANCHOR_PROVIDER", "local")
    # Ed25519 signing key: PEM text in SIGNING_PRIVATE_KEY, or a PEM file (auto-created in development only).
    SIGNING_PRIVATE_KEY = os.environ.get("SIGNING_PRIVATE_KEY", "")
    SIGNING_KEY_FILE = Path(os.environ.get("SIGNING_KEY_FILE", BASE_DIR / "instance" / "ed25519_signing_key.pem"))
    SIGNING_KEY_AUTOGENERATE = False
    # Ethereum anchoring (BLOCKCHAIN_ANCHOR_PROVIDER=ethereum), e.g. Polygon Amoy or a local Anvil node.
    ETH_RPC_URL = os.environ.get("ETH_RPC_URL", "")
    ETH_PRIVATE_KEY = os.environ.get("ETH_PRIVATE_KEY", "")
    ETH_CONTRACT_ADDRESS = os.environ.get("ETH_CONTRACT_ADDRESS", "")
    ETH_CHAIN_ID = int(os.environ["ETH_CHAIN_ID"]) if os.environ.get("ETH_CHAIN_ID") else None
    ETH_NETWORK_NAME = os.environ.get("ETH_NETWORK_NAME", "")
    ETH_EXPLORER_TX_URL = os.environ.get("ETH_EXPLORER_TX_URL", "")  # e.g. https://amoy.polygonscan.com/tx/{tx}
    LOGIN_LOCKOUT_THRESHOLD = int(os.environ.get("LOGIN_LOCKOUT_THRESHOLD", 5))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", 15))
    # Optional antivirus hook, e.g. "clamdscan --no-summary -"; the PDF is piped to stdin and exit code 0 means clean.
    MALWARE_SCAN_COMMAND = os.environ.get("MALWARE_SCAN_COMMAND", "")
    PAGE_SIZE = 20
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "console")
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "Academic Credential Vault <no-reply@credential-vault.local>")
    PASSWORD_RESET_MAX_AGE = 3600
    EMAIL_VERIFY_MAX_AGE = 3 * 24 * 3600


class DevelopmentConfig(Config):
    DEBUG = True
    SIGNING_KEY_AUTOGENERATE = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    UPLOAD_DIRECTORY = BASE_DIR / "instance" / "test_uploads"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SIGNING_KEY_FILE = BASE_DIR / "instance" / "test_uploads" / "test_signing_key.pem"
    SIGNING_KEY_AUTOGENERATE = True
    BLOCKCHAIN_ANCHOR_PROVIDER = "local"
    MAIL_BACKEND = "memory"
    SERVER_NAME = "localhost"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True

    @staticmethod
    def validate(config):
        """Refuse to start in production with placeholder secrets."""
        weak = [name for name in ("SECRET_KEY", "SIGNING_SECRET") if config[name] in (DEFAULT_SECRET, "", None) or len(config[name]) < 32]
        if weak:
            raise RuntimeError(f"Set strong (32+ character) values for {', '.join(weak)} before running in production.")
        if not config.get("SIGNING_PRIVATE_KEY") and not Path(config.get("SIGNING_KEY_FILE") or "/nonexistent").exists():
            raise RuntimeError("Provide the Ed25519 signing key (SIGNING_PRIVATE_KEY or SIGNING_KEY_FILE) before running in production.")


CONFIG_BY_NAME = {"development": DevelopmentConfig, "test": TestConfig, "production": ProductionConfig}
