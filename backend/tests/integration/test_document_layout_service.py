"""Lifecycle, inheritance, locking and audit integration coverage."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.document_layout import DocumentLayoutAuditReceipt
from backend.app.schemas.document_layout import (
    CloneLayoutRequest,
    CreateLayoutRequest,
    LayoutScope,
    PatchLayoutRequest,
    PublishLayoutRequest,
    TypographyRulesPatch,
    WithdrawLayoutRequest,
)
from backend.app.services.document_layouts import (
    LayoutConflictError,
    LayoutStateError,
    activate_due_layouts,
    check_readiness,
    clone_layout,
    create_draft,
    patch_draft,
    publish_layout,
    resolve_effective_layout,
    withdraw_scheduled_layout,
)


async def _profile(session, name: str = "Layout GmbH") -> BusinessProfile:
    profile = BusinessProfile(
        name=name,
        legal_name=name,
        country_code="DE",
        default_currency="EUR",
        default_locale="de",
    )
    session.add(profile)
    await session.flush()
    return profile


@pytest.mark.asyncio
async def test_draft_autosave_conflict_publish_immutability_and_clone(db_session):
    profile = await _profile(db_session)
    draft = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id),
            reason="Initiales Standardlayout",
        ),
        actor_id=None,
    )
    draft = await patch_draft(
        db_session,
        draft.id,
        PatchLayoutRequest(
            expected_lock_version=1,
            edit_session_id="session-123",
            typography=TypographyRulesPatch(accent_color="#111111"),
        ),
        actor_id=None,
    )
    draft = await patch_draft(
        db_session,
        draft.id,
        PatchLayoutRequest(
            expected_lock_version=2,
            edit_session_id="session-123",
            typography=TypographyRulesPatch(text_color="#222222"),
        ),
        actor_id=None,
    )
    assert draft.lock_version == 3
    with pytest.raises(LayoutConflictError):
        await patch_draft(
            db_session,
            draft.id,
            PatchLayoutRequest(
                expected_lock_version=2,
                edit_session_id="other-session",
                typography=TypographyRulesPatch(accent_color="#333333"),
            ),
            actor_id=None,
        )

    receipts = (
        await db_session.scalars(
            select(DocumentLayoutAuditReceipt).where(
                DocumentLayoutAuditReceipt.configuration_id == draft.id
            )
        )
    ).all()
    autosaves = [receipt for receipt in receipts if receipt.event_type == "autosave"]
    assert len(autosaves) == 1
    assert autosaves[0].changed_field_paths == [
        "typography.accent_color",
        "typography.text_color",
    ]
    assert autosaves[0].evidence == {"writes": 2}

    published = await publish_layout(
        db_session,
        draft.id,
        PublishLayoutRequest(expected_lock_version=3, reason="Fachlich geprüft"),
        actor_id=None,
    )
    assert published.status == "active"
    with pytest.raises(LayoutStateError):
        await patch_draft(
            db_session,
            published.id,
            PatchLayoutRequest(
                expected_lock_version=4,
                edit_session_id="after-publish",
                typography=TypographyRulesPatch(accent_color="#444444"),
            ),
            actor_id=None,
        )
    clone = await clone_layout(
        db_session,
        CloneLayoutRequest(source_layout_id=published.id, reason="Neue Gestaltungsrunde"),
        actor_id=None,
    )
    assert clone.status == "draft"
    assert clone.version == 2


@pytest.mark.asyncio
async def test_specific_override_can_be_cleared_back_to_profile_source(db_session):
    profile = await _profile(db_session)
    base = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id),
            reason="Profilstandard",
        ),
        actor_id=None,
    )
    base = await patch_draft(
        db_session,
        base.id,
        PatchLayoutRequest(
            expected_lock_version=1,
            edit_session_id="profile-edit",
            typography=TypographyRulesPatch(accent_color="#111111"),
        ),
        actor_id=None,
    )
    await publish_layout(
        db_session,
        base.id,
        PublishLayoutRequest(expected_lock_version=2, reason="Profil freigegeben"),
        actor_id=None,
    )
    typed = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id, document_type="invoice"),
            reason="Rechnungsspezifisch",
        ),
        actor_id=None,
    )
    typed = await patch_draft(
        db_session,
        typed.id,
        PatchLayoutRequest(
            expected_lock_version=1,
            edit_session_id="invoice-edit",
            typography=TypographyRulesPatch(accent_color="#222222"),
        ),
        actor_id=None,
    )
    resolved = await resolve_effective_layout(
        db_session,
        business_profile_id=profile.id,
        document_type="invoice",
        draft_layout_id=typed.id,
    )
    assert resolved.effective.typography.accent_color == "#222222"
    assert resolved.sourced.typography.sources.accent_color.level == "document_type"

    typed = await patch_draft(
        db_session,
        typed.id,
        PatchLayoutRequest(
            expected_lock_version=2,
            edit_session_id="invoice-edit",
            typography=TypographyRulesPatch(accent_color=None),
        ),
        actor_id=None,
    )
    resolved = await resolve_effective_layout(
        db_session,
        business_profile_id=profile.id,
        document_type="invoice",
        draft_layout_id=typed.id,
    )
    assert resolved.effective.typography.accent_color == "#111111"
    assert resolved.sourced.typography.sources.accent_color.level == "profile"
    assert resolved.sourced.typography.sources.accent_color.configuration_id == base.id

    typed = await patch_draft(
        db_session,
        typed.id,
        PatchLayoutRequest(
            expected_lock_version=3,
            edit_session_id="invoice-publish",
            typography=TypographyRulesPatch(accent_color="#333333"),
        ),
        actor_id=None,
    )
    typed = await publish_layout(
        db_session,
        typed.id,
        PublishLayoutRequest(expected_lock_version=4, reason="Rechnung freigegeben"),
        actor_id=None,
    )
    localized = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(
                business_profile_id=profile.id,
                document_type="invoice",
                language="en",
            ),
            reason="English invoice",
        ),
        actor_id=None,
    )
    localized = await patch_draft(
        db_session,
        localized.id,
        PatchLayoutRequest(
            expected_lock_version=1,
            edit_session_id="language-edit",
            typography=TypographyRulesPatch(accent_color="#444444"),
        ),
        actor_id=None,
    )
    resolved = await resolve_effective_layout(
        db_session,
        business_profile_id=profile.id,
        document_type="invoice",
        language="en",
        draft_layout_id=localized.id,
    )
    assert resolved.effective.typography.accent_color == "#444444"
    assert resolved.sourced.typography.sources.accent_color.level == "language"
    assert resolved.sourced.typography.sources.accent_color.configuration_id == localized.id


@pytest.mark.asyncio
async def test_scheduled_layout_can_be_withdrawn_or_activated_and_supersedes(db_session):
    profile = await _profile(db_session)
    first = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id), reason="Erste Version"
        ),
        actor_id=None,
    )
    first = await publish_layout(
        db_session,
        first.id,
        PublishLayoutRequest(expected_lock_version=1, reason="Erste Freigabe"),
        actor_id=None,
    )
    scheduled = await clone_layout(
        db_session,
        CloneLayoutRequest(source_layout_id=first.id, reason="Geplante Version"),
        actor_id=None,
    )
    due = datetime.now(UTC) + timedelta(days=1)
    scheduled = await publish_layout(
        db_session,
        scheduled.id,
        PublishLayoutRequest(
            expected_lock_version=1, reason="Zum Stichtag", effective_from=due
        ),
        actor_id=None,
    )
    assert scheduled.status == "scheduled"
    withdrawn = await withdraw_scheduled_layout(
        db_session,
        scheduled.id,
        WithdrawLayoutRequest(reason="Termin entfällt"),
        actor_id=None,
    )
    assert withdrawn.status == "withdrawn"

    replacement = await clone_layout(
        db_session,
        CloneLayoutRequest(source_layout_id=first.id, reason="Ersatzversion"),
        actor_id=None,
    )
    replacement = await publish_layout(
        db_session,
        replacement.id,
        PublishLayoutRequest(
            expected_lock_version=1, reason="Neuer Termin", effective_from=due
        ),
        actor_id=None,
    )
    assert await activate_due_layouts(db_session, now=due + timedelta(seconds=1)) == (
        replacement.id,
    )
    first_id = first.id
    replacement_id = replacement.id
    model_type = type(first)
    db_session.expire(first)
    assert (await db_session.get(model_type, first_id)).status == "superseded"
    assert (await db_session.get(model_type, replacement_id)).status == "active"


@pytest.mark.asyncio
async def test_readiness_blocks_missing_profile_default(db_session):
    profile = await _profile(db_session)
    report = await check_readiness(db_session, business_profile_id=profile.id)
    assert report.ready is False
    assert [finding.code for finding in report.findings] == ["profile_default_missing"]
