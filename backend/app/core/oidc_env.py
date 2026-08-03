"""Read the single OIDC provider defined by PRINTOPS_OIDC_* env vars.

Declarative deployments cannot click through the settings UI, so one provider
can be configured entirely from the environment. The same Pydantic schema used
by the API validates the env config; startup config cannot bypass UI checks.
"""

from __future__ import annotations

import contextlib
import logging
import os

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_REQUIRED = (
    "PRINTOPS_OIDC_NAME",
    "PRINTOPS_OIDC_ISSUER_URL",
    "PRINTOPS_OIDC_CLIENT_ID",
    "PRINTOPS_OIDC_CLIENT_SECRET",
)

_TRUTHY = {"true", "1", "yes"}
_FALSY = {"false", "0", "no"}


class EnvOIDCConfigError(Exception):
    """A non-secret PRINTOPS_OIDC_* value could not be interpreted."""


def env_bool(key: str, default: bool, *, strict: bool = True) -> bool:
    """Parse a boolean env var. Absent or blank means the supplied default."""
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return default
    norm = value.strip().lower()
    if norm in _TRUTHY:
        return True
    if norm in _FALSY:
        return False
    if strict:
        raise EnvOIDCConfigError(f"{key}={value!r} is not a recognized boolean (use true/1/yes or false/0/no)")
    return default


def read_env_oidc_config() -> dict | None:
    """Return provider fields from the environment, or None when incomplete."""
    required = {key: (os.environ.get(key) or "").strip() for key in _REQUIRED}
    if not all(required.values()):
        return None

    return {
        "name": required["PRINTOPS_OIDC_NAME"],
        "issuer_url": required["PRINTOPS_OIDC_ISSUER_URL"],
        "client_id": required["PRINTOPS_OIDC_CLIENT_ID"],
        "client_secret": required["PRINTOPS_OIDC_CLIENT_SECRET"],
        "scopes": (os.environ.get("PRINTOPS_OIDC_SCOPES") or "").strip() or "openid email profile",
        "is_enabled": env_bool("PRINTOPS_OIDC_ENABLED", True),
        "allow_private_network": env_bool("PRINTOPS_OIDC_ALLOW_PRIVATE_NETWORK", False),
        "auto_create_users": env_bool("PRINTOPS_OIDC_AUTO_CREATE_USERS", False),
        "auto_link_existing_accounts": env_bool("PRINTOPS_OIDC_AUTO_LINK_EXISTING", False),
        "email_claim": (os.environ.get("PRINTOPS_OIDC_EMAIL_CLAIM") or "").strip() or "email",
        "require_email_verified": env_bool("PRINTOPS_OIDC_REQUIRE_EMAIL_VERIFIED", True),
        "icon_url": (os.environ.get("PRINTOPS_OIDC_ICON_URL") or "").strip() or None,
        "is_autologin": env_bool("PRINTOPS_OIDC_AUTOLOGIN", False),
        "default_group": (os.environ.get("PRINTOPS_OIDC_DEFAULT_GROUP") or "").strip() or None,
    }


_APPLIED_FIELDS = (
    "name",
    "issuer_url",
    "client_id",
    "scopes",
    "is_enabled",
    "allow_private_network",
    "auto_create_users",
    "auto_link_existing_accounts",
    "email_claim",
    "require_email_verified",
    "icon_url",
    "is_autologin",
    "default_group_id",
)


async def apply_env_oidc_provider(db: AsyncSession) -> None:
    """Upsert the env-managed provider, or release it when config is gone.

    Startup must survive OIDC env mistakes, so this function logs and returns
    instead of raising. Secret values are deliberately kept out of log messages.
    """
    try:
        await _apply_env_oidc_provider(db)
    except Exception as exc:  # noqa: BLE001
        logger.error("PRINTOPS_OIDC_* could not be applied: %s", type(exc).__name__)
        with contextlib.suppress(Exception):
            await db.rollback()


async def _apply_env_oidc_provider(db: AsyncSession) -> None:
    from backend.app.models.group import Group
    from backend.app.models.oidc_provider import OIDCProvider
    from backend.app.schemas.auth import OIDCProviderCreate
    from backend.app.services.oidc_icon import fetch_icon

    try:
        config = read_env_oidc_config()
    except EnvOIDCConfigError as exc:
        logger.error("PRINTOPS_OIDC_* config rejected, provider not applied: %s", exc)
        return

    if config is None:
        released_rows = (
            (await db.execute(select(OIDCProvider).where(OIDCProvider.is_env_managed.is_(True)))).scalars().all()
        )
        for released in released_rows:
            released.is_enabled = False
            released.is_env_managed = False
            released.is_autologin = False
            logger.info(
                "PRINTOPS_OIDC_* is unset -- provider %r disabled and released to the UI.",
                released.name,
            )
        if released_rows:
            await db.commit()
        return

    existing = (await db.execute(select(OIDCProvider).where(OIDCProvider.name == config["name"]))).scalar_one_or_none()

    group_name = config.pop("default_group", None)
    if group_name is not None:
        group = (await db.execute(select(Group).where(Group.name == group_name))).scalar_one_or_none()
        if group is None:
            logger.error(
                "PRINTOPS_OIDC_DEFAULT_GROUP=%r matches no group, provider not applied (%s).",
                group_name,
                "previous config left running" if existing is not None else "no provider created",
            )
            return
        config["default_group_id"] = group.id

    try:
        validated = OIDCProviderCreate(**config)
    except ValidationError as exc:
        logger.error(
            "PRINTOPS_OIDC_* config rejected, provider not applied: %s",
            exc.errors(include_input=False),
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.error("PRINTOPS_OIDC_* config could not be applied: %s", type(exc).__name__)
        return

    adopted_ui_provider = existing is not None and not existing.is_env_managed

    if existing is None:
        existing = OIDCProvider(is_env_managed=True)
        db.add(existing)
    previous_icon_url = existing.icon_url
    previous_icon_content_type = existing.icon_content_type
    for field in _APPLIED_FIELDS:
        setattr(existing, field, getattr(validated, field))
    existing.client_secret = validated.client_secret
    existing.is_env_managed = True

    if validated.icon_url is None:
        existing.icon_data = None
        existing.icon_content_type = None
        existing.icon_etag = None
    elif validated.icon_url != previous_icon_url or previous_icon_content_type is None:
        try:
            existing.icon_data, existing.icon_content_type, existing.icon_etag = await fetch_icon(validated.icon_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PRINTOPS_OIDC_ICON_URL for provider %r could not be fetched (%s); keeping provider without cached icon.",
                validated.name,
                type(exc).__name__,
            )
            existing.icon_data = None
            existing.icon_content_type = None
            existing.icon_etag = None

    await db.flush()

    await db.execute(
        update(OIDCProvider)
        .where(OIDCProvider.id != existing.id, OIDCProvider.is_env_managed.is_(True))
        .values(is_env_managed=False, is_enabled=False, is_autologin=False)
    )

    if existing.is_autologin:
        await db.execute(
            update(OIDCProvider)
            .where(OIDCProvider.id != existing.id, OIDCProvider.is_autologin.is_(True))
            .values(is_autologin=False)
        )
    await db.commit()

    if adopted_ui_provider:
        logger.warning(
            "Env-managed OIDC provider %r adopted an existing UI-created provider of the same name; "
            "its issuer, client and secret are now managed by PRINTOPS_OIDC_*.",
            existing.name,
        )
    else:
        logger.info("Env-managed OIDC provider %r applied.", existing.name)
