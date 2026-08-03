"""
Bambu Lab Cloud API Service

Handles authentication and profile management with Bambu Lab's cloud services.
"""

import asyncio
import base64
import hashlib
import json
import logging
import ssl
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

BAMBU_API_BASE = "https://api.bambulab.com"
BAMBU_API_BASE_CN = "https://api.bambulab.cn"
BAMBU_MQTT_HOST = "us.mqtt.bambulab.com"
BAMBU_MQTT_HOST_CN = "cn.mqtt.bambulab.cn"
BAMBU_MQTT_PORT = 8883
_VALIDATION_TTL_SECONDS = 300
_validation_cache: dict[str, tuple[float, bool]] = {}


def _validation_cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_jwt_payload(token: str) -> dict:
    """Best-effort decode for JWT-like Bambu access tokens.

    Some tokens are JWTs and contain the cloud user id needed for MQTT auth;
    manually pasted tokens are not guaranteed to have that shape, so callers
    must treat an empty dict as "not available" and fall back to the profile API.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def extract_cloud_user_id(data: dict | None) -> str | None:
    """Extract a Bambu Cloud user id from common API/JWT response shapes."""
    if not isinstance(data, dict):
        return None
    candidates = [
        data.get("user_id"),
        data.get("userId"),
        data.get("uid"),
        data.get("id"),
        data.get("sub"),
    ]
    nested = data.get("data")
    if isinstance(nested, dict):
        candidates.extend(
            [
                nested.get("user_id"),
                nested.get("userId"),
                nested.get("uid"),
                nested.get("id"),
                nested.get("sub"),
            ]
        )
    for value in candidates:
        if value is None:
            continue
        user_id = str(value).strip()
        if user_id:
            return user_id
    return None


def invalidate_validation_cache(token: str | None = None) -> None:
    """Drop cached token-validation verdicts."""
    if token is None:
        _validation_cache.clear()
    else:
        _validation_cache.pop(_validation_cache_key(token), None)


# Client identity sent to Bambu Lab's cloud services. We identify honestly as
# PrintOps — the URL in parens makes the source unambiguous so Bambu can
# distinguish our traffic from impersonators. This is the opposite of what the
# OrcaSlicer fork was called out for in the May 2026 Bambu Lab blog post
# ("Setting the record straight on cloud access and community"): we do not
# introduce ourselves as official Bambu Studio.
_USER_AGENT = "PrintOps/1.0 (+https://github.com/ichwars/PrintOps)"

# Cloudflare protection on Bambu Lab's edge intermittently returns interstitials /
# challenges instead of the JSON the API normally produces (issue #1575). The
# parse error that results is opaque — these helpers detect the CF markers so
# we can surface an actionable message instead of "Invalid response from Bambu Cloud".
_CF_INTERSTITIAL_USER_MESSAGE = (
    "Bambu Cloud is temporarily blocking automated requests from your network. "
    "This is a Cloudflare protection on Bambu Lab's side, not a PrintOps issue. "
    "Please wait a few minutes and try again. If it persists, signing in to "
    "bambulab.com once from a browser on the same network usually clears the "
    "challenge."
)


def _detect_cloudflare_challenge(response) -> str | None:
    """Return a user-actionable message when the response is a Cloudflare
    challenge / mitigation page instead of the JSON the API normally returns.

    Triggers on any of:
      - body contains "Just a moment..." (CF interactive challenge title)
      - body contains "challenges.cloudflare.com" (CF turnstile widget src)
      - HTTP 403 with a "cf-mitigated" response header (CF blocked)
      - HTTP 503 with a "cf-ray" response header (CF Under Attack mode)

    Returns None when the response doesn't look like a CF challenge — callers
    fall through to their existing error path.
    """
    try:
        body = response.text or ""
    except Exception:
        body = ""
    if "Just a moment..." in body or "challenges.cloudflare.com" in body:
        return _CF_INTERSTITIAL_USER_MESSAGE
    try:
        status = int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    headers = getattr(response, "headers", {}) or {}
    if status == 403 and "cf-mitigated" in headers:
        return _CF_INTERSTITIAL_USER_MESSAGE
    if status == 503 and "cf-ray" in headers:
        return _CF_INTERSTITIAL_USER_MESSAGE
    return None


# The `/v1/iot-service/api/slicer/setting` endpoint subtree — the plural GET
# for the list, the singular GET/DELETE for a specific preset by setting_id, and
# the POST for create — requires a `version` query parameter in the XX.YY.ZZ.WW
# format Bambu Studio releases use. Without it the API returns HTTP 400
# "field 'version' is not set"; non-matching formats like "printops-1.0" return
# HTTP 422 "Invalid input parameters". However, Bambu's server accepts ANY value
# within that format — it doesn't validate against a release manifest. We
# therefore use a neutral "1.0.0.0" placeholder that does not impersonate any
# real Bambu Studio release. Our client identity is in the User-Agent header.
_SLICER_API_VERSION = "1.0.0.0"


class BambuCloudError(Exception):
    """Base exception for Bambu Cloud errors."""

    pass


class BambuCloudAuthError(BambuCloudError):
    """Authentication related errors."""

    pass


_shared_http_client: httpx.AsyncClient | None = None


def set_shared_http_client(client: httpx.AsyncClient | None) -> None:
    """Register an app-scoped ``httpx.AsyncClient`` so per-request
    ``BambuCloudService`` instances can reuse its connection pool.

    Pass ``None`` during shutdown to unregister. The service only holds a
    reference (never closes a client it does not own), so region + token
    state still stays per-request — this only shares the transport pool.
    """
    global _shared_http_client
    _shared_http_client = client


class BambuCloudService:
    """Service for interacting with Bambu Lab Cloud API."""

    def __init__(
        self,
        region: str = "global",
        client: httpx.AsyncClient | None = None,
        on_auth_failure: Callable[[], Awaitable[None]] | None = None,
    ):
        self.base_url = BAMBU_API_BASE if region == "global" else BAMBU_API_BASE_CN
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expiry: datetime | None = None
        self._on_auth_failure = on_auth_failure
        # Prefer an explicitly-injected client (tests), else fall back to the
        # app-scoped shared client (production), and finally create our own so
        # scripts / tests that skip the lifespan still get a working service.
        if client is not None:
            self._client = client
            self._owns_client = False
        elif _shared_http_client is not None:
            self._client = _shared_http_client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(timeout=30.0)
            self._owns_client = True

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        if not self.access_token:
            return False
        return not (self.token_expiry and datetime.now(timezone.utc) > self.token_expiry)

    def _get_headers(self) -> dict:
        """Get headers for authenticated requests."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def login_request(self, email: str, password: str) -> dict:
        """
        Initiate login - this will trigger either email verification or TOTP prompt.

        Returns dict with login status, verification type, and tfaKey if needed.
        """
        try:
            response = await self._client.post(
                f"{self.base_url}/v1/user-service/user/login",
                headers={"Content-Type": "application/json"},
                json={
                    "account": email,
                    "password": password,
                },
            )

            try:
                data = response.json()
            except Exception as json_err:
                logger.error("Failed to parse login response: %s, body: %s", json_err, response.text[:500])
                cf_message = _detect_cloudflare_challenge(response)
                return {
                    "success": False,
                    "needs_verification": False,
                    "message": cf_message or "Invalid response from Bambu Cloud",
                }
            logger.debug(
                f"Login response: status={response.status_code}, loginType={data.get('loginType')}, hasTfaKey={'tfaKey' in data}"
            )

            if response.status_code == 200:
                login_type = data.get("loginType")
                tfa_key = data.get("tfaKey")

                # TOTP authentication required
                if login_type == "tfa" or (tfa_key and login_type != "verifyCode"):
                    return {
                        "success": False,
                        "needs_verification": True,
                        "verification_type": "totp",
                        "tfa_key": tfa_key,
                        "message": "Enter the code from your authenticator app",
                    }

                # Email verification required
                if login_type == "verifyCode":
                    return {
                        "success": False,
                        "needs_verification": True,
                        "verification_type": "email",
                        "tfa_key": None,
                        "message": "Verification code sent to email",
                    }

                # Direct login success (rare, usually needs 2FA)
                if "accessToken" in data:
                    self._set_tokens(data)
                    return {"success": True, "needs_verification": False, "message": "Login successful"}

            # Handle specific error codes
            error_msg = data.get("message") or data.get("error") or "Login failed"
            return {"success": False, "needs_verification": False, "message": error_msg}

        except Exception as e:
            logger.error("Login request failed: %s", e)
            raise BambuCloudAuthError(f"Login request failed: {e}")

    async def verify_code(self, email: str, code: str) -> dict:
        """
        Complete login with email verification code.
        """
        try:
            response = await self._client.post(
                f"{self.base_url}/v1/user-service/user/login",
                headers={"Content-Type": "application/json"},
                json={
                    "account": email,
                    "code": code,
                },
            )

            try:
                data = response.json()
            except Exception as json_err:
                logger.error("Failed to parse email-verify response: %s, body: %s", json_err, response.text[:500])
                cf_message = _detect_cloudflare_challenge(response)
                return {"success": False, "message": cf_message or "Invalid response from Bambu Cloud"}
            logger.debug("Email verify response: status=%s, hasToken=%s", response.status_code, "accessToken" in data)

            if response.status_code == 200 and "accessToken" in data:
                self._set_tokens(data)
                return {"success": True, "message": "Login successful"}

            return {"success": False, "message": data.get("message", "Verification failed")}

        except Exception as e:
            logger.error("Email verification failed: %s", e)
            raise BambuCloudAuthError(f"Verification failed: {e}")

    async def _fetch_csrf_token(self, web_origin: str, client: httpx.AsyncClient | None = None) -> str | None:
        """Seed Bambu's web-origin CSRF cookie and return its value."""
        csrf_client = client or self._client
        try:
            response = await csrf_client.get(
                f"{web_origin}/api/csrf",
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
        except Exception as e:
            logger.warning("Failed to fetch Bambu Cloud CSRF token: %s", e)
            return None
        try:
            token = csrf_client.cookies.get("bbl_csrf_token")
        except Exception:
            token = None
        if not token:
            logger.warning(
                "Bambu Cloud CSRF endpoint returned no bbl_csrf_token (status %s)",
                response.status_code,
            )
        return token

    def _new_csrf_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0, cookies=httpx.Cookies())

    def _should_reuse_client_for_csrf(self) -> bool:
        """Reuse injected/mocked clients so tests can capture both CSRF and TFA calls."""
        transport = getattr(self._client, "_transport", None)
        if isinstance(transport, httpx.MockTransport):
            return True
        return hasattr(getattr(self._client, "post", None), "assert_called")

    @asynccontextmanager
    async def _csrf_client_context(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._should_reuse_client_for_csrf():
            yield self._client
            return
        async with self._new_csrf_client() as csrf_client:
            yield csrf_client

    async def verify_totp(self, tfa_key: str, code: str) -> dict:
        """
        Complete login with TOTP code from authenticator app.

        Args:
            tfa_key: The tfaKey returned from initial login request
            code: 6-digit TOTP code from authenticator app
        """
        try:
            # TFA endpoint is on bambulab.com, NOT api.bambulab.com.
            # We previously sent a Chrome User-Agent plus Origin/Referer headers
            # under the assumption Cloudflare would block bot-identified
            # requests. Verified 2026-05-12 via curl that the endpoint accepts
            # honest "PrintOps/X.Y.Z" identification cleanly (HTTP 400 with the
            # expected application-level "Login failed" JSON, no Cloudflare
            # interstitial). Browser-impersonation removed to stay clearly on
            # the right side of Bambu Lab's "no falsified client identity" line.
            web_origin = "https://bambulab.cn" if "bambulab.cn" in self.base_url else "https://bambulab.com"
            tfa_url = f"{web_origin}/api/sign-in/tfa"

            async with self._csrf_client_context() as csrf_client:
                csrf_token = await self._fetch_csrf_token(web_origin, csrf_client)
                if not csrf_token:
                    return {
                        "success": False,
                        "message": (
                            "Could not obtain a security token from Bambu Cloud. "
                            "Check the server's internet access and try again."
                        ),
                    }

                response = await csrf_client.post(
                    tfa_url,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": _USER_AGENT,
                        "Accept": "application/json",
                        "x-bbl-csrf-token": csrf_token,
                    },
                    json={
                        "tfaKey": tfa_key,
                        "tfaCode": code,
                    },
                )

            logger.debug(
                f"TOTP verify response: status={response.status_code}, body={response.text[:200] if response.text else '(empty)'}"
            )

            # Handle empty response
            if not response.text or not response.text.strip():
                logger.warning("TOTP verification returned empty response (status %s)", response.status_code)
                return {"success": False, "message": "Bambu Cloud returned empty response. Please try again."}

            try:
                data = response.json()
            except Exception as json_err:
                logger.error("Failed to parse TOTP response: %s, body: %s", json_err, response.text[:500])
                cf_message = _detect_cloudflare_challenge(response)
                return {"success": False, "message": cf_message or "Invalid response from Bambu Cloud"}

            # Token might be in accessToken, token field, or cookies
            access_token = data.get("accessToken") or data.get("token")

            # Also check cookies for token
            if not access_token:
                for cookie in response.cookies:
                    if "token" in cookie.lower():
                        access_token = response.cookies.get(cookie)
                        break

            if response.status_code == 200 and access_token:
                self.access_token = access_token
                self.refresh_token = data.get("refreshToken")
                from datetime import datetime, timedelta, timezone

                self.token_expiry = datetime.now(timezone.utc) + timedelta(days=30)
                return {"success": True, "message": "Login successful"}

            # Provide helpful error message
            error_msg = data.get("message", "")
            csrf_error = data.get("error", "") if isinstance(data.get("error"), str) else ""
            if "csrf" in csrf_error.lower() or data.get("reason") in ("missing_cookie", "missing_header"):
                logger.error("Bambu Cloud rejected the TOTP request on CSRF grounds: %s", response.text[:200])
                return {
                    "success": False,
                    "message": (
                        "Bambu Cloud rejected the sign-in request before checking your code "
                        "(security-token error). Your code is fine; please try again."
                    ),
                }
            if "expired" in error_msg.lower():
                return {"success": False, "message": "TOTP session expired. Please try logging in again."}
            if not error_msg:
                error_msg = data.get("error") or f"TOTP verification failed (status {response.status_code})"

            return {"success": False, "message": error_msg}

        except Exception as e:
            logger.error("TOTP verification failed: %s", e)
            # Return error instead of raising - don't trigger 401/500
            return {"success": False, "message": f"TOTP verification error: {e}"}

    def _set_tokens(self, data: dict):
        """Set tokens from login response."""
        self.access_token = data.get("accessToken")
        self.refresh_token = data.get("refreshToken")
        # Token typically valid for ~3 months, but we'll refresh more often
        self.token_expiry = datetime.now(timezone.utc) + timedelta(days=30)

    def set_token(self, access_token: str):
        """Set access token directly (for stored tokens)."""
        self.access_token = access_token
        self.token_expiry = None

    def _mqtt_host(self) -> str:
        return BAMBU_MQTT_HOST_CN if self.base_url == BAMBU_API_BASE_CN else BAMBU_MQTT_HOST

    def _token_user_id(self) -> str | None:
        if not self.access_token:
            return None
        return extract_cloud_user_id(_decode_jwt_payload(self.access_token))

    async def get_mqtt_user_id(self) -> str | None:
        """Resolve the cloud user id required for Bambu Cloud MQTT auth."""
        token_user_id = self._token_user_id()
        if token_user_id:
            return token_user_id
        try:
            return extract_cloud_user_id(await self.get_user_profile())
        except BambuCloudError:
            raise
        except Exception as exc:
            raise BambuCloudError(f"Failed to resolve cloud MQTT user id: {exc}") from exc

    async def publish_mqtt_command(
        self,
        device_id: str,
        payload: dict,
        *,
        connect_timeout: float = 8.0,
        publish_timeout: float = 8.0,
    ) -> bool:
        """Publish one command to Bambu Cloud MQTT.

        This is intentionally single-shot: connect, publish with QoS 1, then
        disconnect. It keeps the first Cloud-control MVP small and avoids a
        long-lived cloud MQTT session until we have more confirmed command
        coverage.
        """
        if not self.is_authenticated or not self.access_token:
            raise BambuCloudAuthError("Not authenticated")
        device_id = device_id.strip()
        if not device_id:
            raise BambuCloudError("Missing device id")
        user_id = await self.get_mqtt_user_id()
        if not user_id:
            raise BambuCloudError("Could not resolve Bambu Cloud user id for MQTT auth")

        return await asyncio.to_thread(
            self._publish_mqtt_command_sync,
            user_id,
            device_id,
            payload,
            connect_timeout,
            publish_timeout,
        )

    def _publish_mqtt_command_sync(
        self,
        user_id: str,
        device_id: str,
        payload: dict,
        connect_timeout: float,
        publish_timeout: float,
    ) -> bool:
        import threading
        import uuid

        connected = threading.Event()
        published = threading.Event()
        errors: list[str] = []
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"printops_cloud_{device_id}_{uuid.uuid4().hex[:10]}",
            protocol=mqtt.MQTTv311,
        )

        def on_connect(_client, _userdata, _flags, reason_code, _properties=None):
            if int(reason_code) == 0:
                connected.set()
            else:
                errors.append(f"Cloud MQTT connect failed: {reason_code}")
                connected.set()

        def on_publish(_client, _userdata, _mid, _reason_code=None, _properties=None):
            published.set()

        client.on_connect = on_connect
        client.on_publish = on_publish
        client.username_pw_set(f"u_{user_id}", self.access_token)
        client.tls_set_context(ssl.create_default_context())

        try:
            client.connect(self._mqtt_host(), BAMBU_MQTT_PORT, keepalive=30)
            client.loop_start()
            if not connected.wait(connect_timeout):
                raise BambuCloudError("Timed out connecting to Bambu Cloud MQTT")
            if errors:
                raise BambuCloudError(errors[-1])

            info = client.publish(f"device/{device_id}/request", json.dumps(payload), qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise BambuCloudError(f"Cloud MQTT publish failed: {info.rc}")
            if not published.wait(publish_timeout):
                raise BambuCloudError("Timed out waiting for Bambu Cloud MQTT publish acknowledgement")
            return True
        except BambuCloudError:
            raise
        except Exception as exc:
            raise BambuCloudError(f"Cloud MQTT command failed: {exc}") from exc
        finally:
            try:
                client.disconnect()
            except Exception:
                pass
            try:
                client.loop_stop()
            except Exception:
                pass

    async def _notify_auth_failure(self) -> None:
        if self._on_auth_failure is None:
            return
        try:
            await self._on_auth_failure()
        except Exception:
            logger.exception("Bambu Cloud auth-failure callback failed")

    async def validate_token(self) -> bool | None:
        """Ask Bambu whether the stored token is still accepted.

        Returns True/False for an authoritative answer and None for transient
        reachability/server problems.
        """
        if not self.access_token:
            return False
        now = time.monotonic()
        cache_key = _validation_cache_key(self.access_token)
        cached = _validation_cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]
        try:
            response = await self._client.get(
                f"{self.base_url}/v1/design-user-service/my/preference",
                headers=self._get_headers(),
            )
        except httpx.RequestError:
            return None
        if response.status_code == 200:
            _validation_cache[cache_key] = (now + _VALIDATION_TTL_SECONDS, True)
            return True
        if response.status_code == 401:
            _validation_cache[cache_key] = (now + _VALIDATION_TTL_SECONDS, False)
            await self._notify_auth_failure()
            return False
        return None

    def logout(self):
        """Clear authentication state."""
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None

    async def get_user_profile(self) -> dict:
        """Get user profile information."""
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            response = await self._client.get(
                f"{self.base_url}/v1/design-user-service/my/preference", headers=self._get_headers()
            )

            if response.status_code == 200:
                return response.json()

            raise BambuCloudError(f"Failed to get profile: {response.status_code}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def get_slicer_settings(self, version: str = _SLICER_API_VERSION) -> dict:
        """
        Get all slicer settings (filament, printer, process presets).

        Args:
            version: Slicer version string. Bambu's API requires the XX.YY.ZZ.WW
                format but does not validate against a release manifest — we
                default to the neutral _SLICER_API_VERSION placeholder so we
                never claim to be a specific Bambu Studio build. Callers should
                normally use the default.
        """
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            response = await self._client.get(
                f"{self.base_url}/v1/iot-service/api/slicer/setting",
                headers=self._get_headers(),
                params={"version": version},
            )

            data = response.json()

            if response.status_code == 200:
                return data

            raise BambuCloudError(f"Failed to get settings: {response.status_code}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def get_setting_detail(self, setting_id: str) -> dict:
        """Get detailed information for a specific setting/preset."""
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            response = await self._client.get(
                f"{self.base_url}/v1/iot-service/api/slicer/setting/{setting_id}",
                headers=self._get_headers(),
                params={"version": _SLICER_API_VERSION},
            )

            if response.status_code == 200:
                return response.json()

            # Include body so a future contract change is self-diagnostic from logs.
            body = (response.text or "")[:200]
            raise BambuCloudError(f"Failed to get setting detail: {response.status_code} {body}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def create_setting(
        self, preset_type: str, name: str, base_id: str, setting: dict, version: str = "2.0.0.0"
    ) -> dict:
        """
        Create a new slicer preset/setting.

        Args:
            preset_type: Type of preset - "filament", "print", or "printer"
            name: Display name for the preset
            base_id: Base preset ID to inherit from (e.g., "GFSA00")
            setting: Dict of setting key-value pairs (only modified values from base)
            version: Version string for the preset (default: "2.0.0.0")

        Returns:
            Created preset data including the new setting_id
        """
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            # Add timestamp if not present
            import time

            if "updated_time" not in setting:
                setting["updated_time"] = str(int(time.time()))

            payload = {
                "type": preset_type,
                "name": name,
                "version": version,
                "base_id": base_id,
                "setting": setting,
            }

            response = await self._client.post(
                f"{self.base_url}/v1/iot-service/api/slicer/setting", headers=self._get_headers(), json=payload
            )

            data = response.json()

            if response.status_code in (200, 201):
                return data

            error_msg = data.get("message") or data.get("error") or f"HTTP {response.status_code}"
            raise BambuCloudError(f"Failed to create setting: {error_msg}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def update_setting(self, setting_id: str, name: str | None = None, setting: dict | None = None) -> dict:
        """
        Update an existing slicer preset/setting.

        Note: Bambu Cloud API doesn't support true updates. Instead, we:
        1. Fetch the current setting metadata (type, base_id, version)
        2. Use the provided settings as the new complete settings (NOT merged)
        3. Delete the old setting first (to avoid name conflicts)
        4. Create a new setting via POST

        Args:
            setting_id: ID of the preset to update
            name: New display name (optional)
            setting: Dict of setting key-value pairs - this REPLACES the old settings entirely

        Returns:
            Updated preset data with new setting_id
        """
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            # Fetch current setting to get metadata (type, base_id, version)
            current = await self.get_setting_detail(setting_id)
            preset_type = current.get("type", "filament")

            # Use provided settings directly (complete replacement, not merge)
            # This allows the frontend to edit the full settings JSON
            if setting is not None:
                updated_setting = setting.copy()
            else:
                updated_setting = current.get("setting", {}).copy()

            # Extract name from settings_id field in the JSON, or use provided name, or fall back to current
            # The settings_id field contains the name in quotes, e.g., '"My Preset Name"'
            settings_id_key = {
                "filament": "filament_settings_id",
                "print": "print_settings_id",
                "printer": "printer_settings_id",
            }.get(preset_type, "filament_settings_id")

            settings_id_value = updated_setting.get(settings_id_key, "")
            if settings_id_value:
                # Remove surrounding quotes if present (e.g., '"foo"' -> 'foo')
                updated_name = settings_id_value.strip('"')
            elif name is not None:
                updated_name = name
            else:
                updated_name = current.get("name", "Untitled")

            # Update the timestamp
            import time

            updated_setting["updated_time"] = str(int(time.time()))

            # Ensure settings_id field matches the name
            updated_setting[settings_id_key] = f'"{updated_name}"'

            # Delete the old setting FIRST to avoid name conflicts
            await self.delete_setting(setting_id)

            # Create new setting via POST
            payload = {
                "type": preset_type,
                "name": updated_name,
                "version": current.get("version", "2.0.0.0"),
                "base_id": current.get("base_id", ""),
                "setting": updated_setting,
            }

            response = await self._client.post(
                f"{self.base_url}/v1/iot-service/api/slicer/setting", headers=self._get_headers(), json=payload
            )

            data = response.json()

            if response.status_code == 200:
                return data

            error_msg = data.get("message") or data.get("error") or f"HTTP {response.status_code}"
            raise BambuCloudError(f"Failed to update setting: {error_msg}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def delete_setting(self, setting_id: str) -> dict:
        """
        Delete a slicer preset/setting.

        Args:
            setting_id: ID of the preset to delete

        Returns:
            Deletion confirmation
        """
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            response = await self._client.delete(
                f"{self.base_url}/v1/iot-service/api/slicer/setting/{setting_id}",
                headers=self._get_headers(),
                params={"version": _SLICER_API_VERSION},
            )

            if response.status_code in (200, 204):
                return {"success": True, "message": "Setting deleted"}

            data = response.json() if response.content else {}
            error_msg = data.get("message") or data.get("error") or f"HTTP {response.status_code}"
            raise BambuCloudError(f"Failed to delete setting: {error_msg}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def get_devices(self) -> dict:
        """Get list of bound devices."""
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            response = await self._client.get(
                f"{self.base_url}/v1/iot-service/api/user/bind", headers=self._get_headers()
            )

            if response.status_code == 200:
                return response.json()

            raise BambuCloudError(f"Failed to get devices: {response.status_code}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def get_firmware_version(self, device_id: str) -> dict:
        """
        Get firmware version info for a device.

        Returns dict with:
        - current_version: Installed firmware version
        - latest_version: Latest available firmware version
        - update_available: Boolean indicating if update is available
        - release_notes: Release notes for latest version
        """
        if not self.is_authenticated:
            raise BambuCloudAuthError("Not authenticated")

        try:
            response = await self._client.get(
                f"{self.base_url}/v1/iot-service/api/user/device/version",
                headers=self._get_headers(),
                params={"device_id": device_id},
            )

            if response.status_code == 200:
                data = response.json()
                # API wraps response in 'data' field
                return data.get("data", data)

            raise BambuCloudError(f"Failed to get firmware version: {response.status_code}")

        except httpx.RequestError as e:
            raise BambuCloudError(f"Request failed: {e}")

    async def close(self):
        """Close the HTTP client we own. No-op when sharing an app-scoped client."""
        if self._owns_client:
            await self._client.aclose()


# Previously this module exposed a process-wide ``_cloud_service`` singleton
# via ``get_cloud_service()`` / ``reset_cloud_service()``. That pattern leaked
# region and token state across users (a China-region login would pin the
# singleton to api.bambulab.cn until the next explicit reset), so the singleton
# has been removed. Callers should construct a per-request
# ``BambuCloudService(region=...)`` from the stored region and ``await
# cloud.close()`` it when done. See ``routes.cloud.build_authenticated_cloud``
# for the standard pattern.
