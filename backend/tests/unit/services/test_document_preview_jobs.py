from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.document_layout import DocumentLayoutConfiguration
from backend.app.services.document_preview_jobs import (
    DocumentPreviewJobService,
    PreviewJobError,
)


async def _scope(db_session) -> tuple[int, int]:
    profile = BusinessProfile(
        name="Preview profile",
        legal_name="Preview GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.flush()
    layout = DocumentLayoutConfiguration(
        business_profile_id=profile.id,
        scope_key="*|*",
        version=1,
        status="draft",
        template_key="classic",
        page_format="A4",
        orientation="portrait",
    )
    db_session.add(layout)
    await db_session.flush()
    return profile.id, layout.id


@pytest.mark.asyncio
async def test_preview_job_transitions_and_cache_hash(db_session, tmp_path):
    profile_id, layout_id = await _scope(db_session)
    service = DocumentPreviewJobService(storage_root=tmp_path, ttl_seconds=60)
    job, cache_hit = await service.enqueue(
        db_session,
        actor_id=None,
        business_profile_id=profile_id,
        configuration_id=layout_id,
        layout_lock_version=2,
        source_type="sample",
        source_reference="invoice-de-standard",
    )
    assert cache_hit is False
    claimed = await service.claim(db_session, job.public_id)
    ready = await service.complete(db_session, claimed, b"%PDF-1.7\nfixture")
    assert service.read_result(ready) == b"%PDF-1.7\nfixture"

    cached, cache_hit = await service.enqueue(
        db_session,
        actor_id=None,
        business_profile_id=profile_id,
        configuration_id=layout_id,
        layout_lock_version=2,
        source_type="sample",
        source_reference="invoice-de-standard",
    )
    assert cache_hit is True
    assert cached.id == ready.id


@pytest.mark.asyncio
async def test_preview_job_recovers_running_and_expires_results(db_session, tmp_path):
    profile_id, layout_id = await _scope(db_session)
    service = DocumentPreviewJobService(storage_root=tmp_path, ttl_seconds=1)
    job, _ = await service.enqueue(
        db_session,
        actor_id=None,
        business_profile_id=profile_id,
        configuration_id=layout_id,
        layout_lock_version=1,
        source_type="sample",
        source_reference="invoice-de-standard",
    )
    await service.claim(db_session, job.public_id)
    assert await service.recover_interrupted(db_session) == 1
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.findings == {"code": "PREVIEW_INTERRUPTED"}

    job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await service.expire(db_session) == 1
    assert job.status == "expired"


@pytest.mark.asyncio
async def test_preview_job_rejects_state_races_and_tampered_cache(db_session, tmp_path):
    profile_id, layout_id = await _scope(db_session)
    service = DocumentPreviewJobService(storage_root=tmp_path)
    job, _ = await service.enqueue(
        db_session,
        actor_id=None,
        business_profile_id=profile_id,
        configuration_id=layout_id,
        layout_lock_version=1,
        source_type="sample",
        source_reference="invoice-de-standard",
    )
    with pytest.raises(PreviewJobError, match="NOT_READY"):
        service.read_result(job)
    await service.claim(db_session, job.public_id)
    with pytest.raises(PreviewJobError, match="NOT_QUEUED"):
        await service.claim(db_session, job.public_id)
