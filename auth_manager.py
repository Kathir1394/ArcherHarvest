"""
Kite Connect OAuth authentication manager.
Handles login URL generation, callback processing, and session lifecycle.
"""

import logging
from datetime import datetime
from kiteconnect import KiteConnect
from config import config

log = logging.getLogger(__name__)


class AuthManager:
    def __init__(self):
        self.kite = KiteConnect(api_key=config.KITE_API_KEY)
        self.access_token: str | None = None
        self.user_id: str | None = None
        self.login_time: datetime | None = None
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated and self.access_token is not None

    def get_login_url(self) -> str:
        return self.kite.login_url()

    def handle_callback(self, request_token: str) -> dict:
        """
        Exchange the request_token from OAuth redirect for an access_token.
        Returns user profile dict on success; raises on failure.
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
            log.info("Authenticated as %s", self.user_id)
            return {
                "user_id": self.user_id,
                "login_time": self.login_time.isoformat(),
                "status": "authenticated",
            }
        except Exception as exc:
            self._authenticated = False
            self.access_token = None
            log.error("Auth failed: %s", exc)
            raise

    def get_status(self) -> dict:
        return {
            "authenticated": self.is_authenticated,
            "user_id": self.user_id,
            "login_time": self.login_time.isoformat() if self.login_time else None,
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
        self.kite = KiteConnect(api_key=config.KITE_API_KEY)
        log.info("Logged out")


auth_manager = AuthManager()
