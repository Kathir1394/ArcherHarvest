"""
Kite Connect OAuth authentication manager.
Handles login URL generation, callback processing, and session lifecycle.
Supports multiple API keys for parallel rate-limit scaling.
"""

import logging
from datetime import datetime
from kiteconnect import KiteConnect
from config import config

log = logging.getLogger(__name__)

# Connection pool config for HTTP keep-alive (eliminates TCP+TLS overhead)
POOL_CONFIG = {"pool_connections": 20, "pool_maxsize": 20, "max_retries": 1}


class AuthManager:
    def __init__(self):
        self.kite = KiteConnect(
            api_key=config.KITE_API_KEY,
            pool=POOL_CONFIG,
        )
        self.access_token: str | None = None
        self.user_id: str | None = None
        self.login_time: datetime | None = None
        self._authenticated = False
        self._extra_kites: list[KiteConnect] = []

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated and self.access_token is not None

    def get_login_url(self) -> str:
        return self.kite.login_url()

    def handle_callback(self, request_token: str) -> dict:
        """
        Exchange the request_token from OAuth redirect for an access_token.
        Returns user profile dict on success; raises on failure.
        Also initializes extra Kite clients if multi-key is configured.
        """
        try:
            session = self.kite.generate_session(
                request_token, api_secret=config.KITE_API_SECRET
            )
            self.access_token = session["access_token"]
            self.user_id = session.get("user_id", "unknown")
            self.login_time = datetime.now()
            self.kite.set_access_token(self.access_token)
            self._authenticated = True

            self._init_extra_kites()

            log.info(
                "Authenticated as %s (%d API key(s) active)",
                self.user_id,
                1 + len(self._extra_kites),
            )
            return {
                "user_id": self.user_id,
                "login_time": self.login_time.isoformat(),
                "status": "authenticated",
                "api_keys_active": 1 + len(self._extra_kites),
            }
        except Exception as exc:
            self._authenticated = False
            self.access_token = None
            log.error("Auth failed: %s", exc)
            raise

    def _init_extra_kites(self):
        """
        If multiple KITE_API_KEY values are configured (comma-separated),
        create additional KiteConnect instances each with their own
        connection pool. Each key gets its own 3 req/s quota.
        NOTE: All keys must share the same access_token from the
        same Zerodha user account.
        """
        self._extra_kites.clear()
        keys = config.KITE_API_KEYS
        secrets = config.KITE_API_SECRETS

        if len(keys) <= 1:
            return

        for i in range(1, len(keys)):
            try:
                extra = KiteConnect(api_key=keys[i], pool=POOL_CONFIG)
                extra.set_access_token(self.access_token)
                self._extra_kites.append(extra)
                log.info("Extra API key #%d (%s...) initialized", i + 1, keys[i][:6])
            except Exception as exc:
                log.warning("Failed to init extra key #%d: %s", i + 1, exc)

    def get_all_kites(self) -> list[KiteConnect]:
        """Return list of all active KiteConnect clients (primary + extras)."""
        return [self.kite] + self._extra_kites

    def get_status(self) -> dict:
        return {
            "authenticated": self.is_authenticated,
            "user_id": self.user_id,
            "login_time": self.login_time.isoformat() if self.login_time else None,
            "api_keys_active": 1 + len(self._extra_kites),
        }

    def logout(self):
        try:
            if self.access_token:
                self.kite.invalidate_access_token(self.access_token)
        except Exception:
            pass
        self.access_token = None
        self.user_id = None
        self.login_time = None
        self._authenticated = False
        self._extra_kites.clear()
        self.kite = KiteConnect(api_key=config.KITE_API_KEY, pool=POOL_CONFIG)
        log.info("Logged out")


auth_manager = AuthManager()
