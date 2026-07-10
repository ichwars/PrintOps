from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import inspect, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import Update

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.number_sequence import format_number, reserve_number, validate_number_pattern
from backend.app.services.order_errors import ResourceNotFoundError, VersionConflictError


async def _create_sequence(
    session: AsyncSession,
    *,
    name: str = "Primary",
    prefix: str = "C",
    pattern: str = "{PREFIX}-{YYYY}-{####}",
    next_value: int = 1,
    reset_policy: str = "none",
    current_period: str | None = None,
    version: int = 1,
) -> tuple[int, NumberSequence]:
    profile = BusinessProfile(
        name=name,
        legal_name=f"{name} Ltd",
        country_code="IE",
        default_currency="EUR",
        timezone="Europe/Dublin",
        default_locale="en-IE",
        billing_mode="hybrid",
    )
    session.add(profile)
    await session.flush()

    sequence = NumberSequence(
        business_profile_id=profile.id,
        key="customer",
        prefix=prefix,
        pattern=pattern,
        next_value=next_value,
        reset_policy=reset_policy,
        current_period=current_period,
        version=version,
    )
    session.add(sequence)
    await session.commit()
    await session.refresh(sequence)
    return profile.id, sequence


def test_format_number_replaces_supported_tokens():
    assert (
        format_number(
            pattern="{PREFIX}-{YYYY}-{#####}",
            prefix="CUST",
            value=42,
            effective_date=date(2026, 7, 10),
        )
        == "CUST-2026-00042"
    )


def test_format_number_zero_pads_four_digit_year_for_early_dates():
    assert (
        format_number(
            pattern="{PREFIX}-{YYYY}-{YY}-{####}",
            prefix="C",
            value=1,
            effective_date=date(1, 1, 1),
        )
        == "C-0001-01-0001"
    )


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("{PREFIX}-{YYYY}-{#}", "INV-2026-7"),
        ("{PREFIX}-{YY}-{##########}", "INV-26-0000000007"),
    ],
)
def test_format_number_accepts_counter_width_boundaries(pattern, expected):
    assert format_number(pattern=pattern, prefix="INV", value=7, effective_date=date(2026, 7, 10)) == expected


@pytest.mark.parametrize(
    "pattern",
    [
        "{PREFIX}",
        "{PREFIX}-{YYYY}",
        "{PREFIX}-{UNKNOWN}-{####}",
        "{PREFIX}-{###########}",
        "{PREFIX}-{####}-{##}",
        "{PREFIX}-{}-{####}",
        "{PREFIX-{####}",
        "{PREFIX}}-{####}",
        "{{PREFIX}}-{####}",
    ],
)
def test_number_pattern_rejects_missing_unsupported_or_malformed_tokens(pattern):
    with pytest.raises(ValueError):
        validate_number_pattern(pattern)


@pytest.mark.parametrize("value", [0, -1])
def test_format_number_rejects_nonpositive_values(value):
    with pytest.raises(ValueError):
        format_number(
            pattern="{PREFIX}-{####}",
            prefix="C",
            value=value,
            effective_date=date(2026, 7, 10),
        )


def test_format_number_does_not_truncate_values_wider_than_counter():
    assert (
        format_number(
            pattern="{PREFIX}-{##}",
            prefix="C",
            value=123,
            effective_date=date(2026, 7, 10),
        )
        == "C-123"
    )


@pytest.mark.asyncio
async def test_yearly_sequence_resets_on_new_year_without_internal_commit(db_session, monkeypatch):
    profile_id, sequence = await _create_sequence(
        db_session,
        next_value=88,
        reset_policy="yearly",
        current_period="2025",
        version=4,
    )
    commit = AsyncMock(side_effect=AssertionError("reserve_number must not commit"))
    monkeypatch.setattr(db_session, "commit", commit)

    number = await reserve_number(
        db_session,
        business_profile_id=profile_id,
        key="customer",
        effective_date=date(2026, 1, 2),
    )

    assert number == "C-2026-0001"
    assert commit.await_count == 0
    await db_session.refresh(sequence)
    assert sequence.next_value == 2
    assert sequence.current_period == "2026"
    assert sequence.version == 5


@pytest.mark.asyncio
async def test_yearly_sequence_stores_and_reuses_zero_padded_early_year_period(db_session):
    profile_id, sequence = await _create_sequence(
        db_session,
        next_value=88,
        reset_policy="yearly",
        current_period=None,
    )

    first_number = await reserve_number(
        db_session,
        business_profile_id=profile_id,
        key="customer",
        effective_date=date(1, 1, 1),
    )
    second_number = await reserve_number(
        db_session,
        business_profile_id=profile_id,
        key="customer",
        effective_date=date(1, 1, 2),
    )

    assert first_number == "C-0001-0001"
    assert second_number == "C-0001-0002"
    await db_session.refresh(sequence)
    assert sequence.current_period == "0001"
    assert sequence.next_value == 3


@pytest.mark.asyncio
async def test_yearly_sequence_rejects_an_effective_year_before_current_period(db_session):
    profile_id, sequence = await _create_sequence(
        db_session,
        next_value=88,
        reset_policy="yearly",
        current_period="2026",
        version=4,
    )

    with pytest.raises(ValueError, match="precedes current sequence period"):
        await reserve_number(
            db_session,
            business_profile_id=profile_id,
            key="customer",
            effective_date=date(2025, 12, 31),
        )

    await db_session.refresh(sequence)
    assert sequence.next_value == 88
    assert sequence.current_period == "2026"
    assert sequence.version == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("current_period", ["202A", "0000", "10000"])
async def test_yearly_sequence_rejects_malformed_current_period(db_session, current_period):
    profile_id, sequence = await _create_sequence(
        db_session,
        next_value=88,
        reset_policy="yearly",
        current_period=current_period,
        version=4,
    )

    with pytest.raises(ValueError, match="four-digit year"):
        await reserve_number(
            db_session,
            business_profile_id=profile_id,
            key="customer",
            effective_date=date(2026, 1, 1),
        )

    await db_session.refresh(sequence)
    assert sequence.next_value == 88
    assert sequence.current_period == current_period
    assert sequence.version == 4


@pytest.mark.asyncio
async def test_yearly_conflict_rejects_rewind_after_writer_advances_period(db_session, monkeypatch):
    profile_id, sequence = await _create_sequence(
        db_session,
        next_value=88,
        reset_policy="yearly",
        current_period="2025",
        version=1,
    )
    original_execute = db_session.execute
    cas_attempts = 0

    async def execute_after_writer_advances(statement, *args, **kwargs):
        nonlocal cas_attempts
        if isinstance(statement, Update):
            cas_attempts += 1
            if cas_attempts == 1:
                await original_execute(
                    update(NumberSequence)
                    .where(NumberSequence.id == sequence.id, NumberSequence.version == 1)
                    .values(next_value=2, current_period="2027", version=2)
                )
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute_after_writer_advances)

    with pytest.raises(ValueError, match="precedes current sequence period"):
        await reserve_number(
            db_session,
            business_profile_id=profile_id,
            key="customer",
            effective_date=date(2026, 1, 1),
        )

    assert cas_attempts == 1
    await db_session.refresh(sequence)
    assert sequence.next_value == 2
    assert sequence.current_period == "2027"
    assert sequence.version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reset_policy", "current_period", "expected_period"),
    [("yearly", "2026", "2026"), ("none", "2025", "2025")],
)
async def test_sequence_without_period_reset_reserves_existing_next_value(
    db_session,
    reset_policy,
    current_period,
    expected_period,
):
    profile_id, sequence = await _create_sequence(
        db_session,
        next_value=12,
        reset_policy=reset_policy,
        current_period=current_period,
        version=7,
    )

    number = await reserve_number(
        db_session,
        business_profile_id=profile_id,
        key="customer",
        effective_date=date(2026, 7, 10),
    )

    assert number == "C-2026-0012"
    await db_session.refresh(sequence)
    assert sequence.next_value == 13
    assert sequence.current_period == expected_period
    assert sequence.version == 8


@pytest.mark.asyncio
async def test_missing_sequence_raises_resource_not_found(db_session):
    with pytest.raises(ResourceNotFoundError):
        await reserve_number(
            db_session,
            business_profile_id=404,
            key="customer",
            effective_date=date(2026, 7, 10),
        )


@pytest.mark.asyncio
async def test_optimistic_conflict_refreshes_and_reserves_the_next_unique_value(db_session, monkeypatch):
    profile_id, sequence = await _create_sequence(
        db_session,
        pattern="{PREFIX}-{####}",
        next_value=5,
        version=1,
    )
    original_execute = db_session.execute
    cas_attempts = 0

    async def execute_with_one_conflict(statement, *args, **kwargs):
        nonlocal cas_attempts
        if isinstance(statement, Update):
            cas_attempts += 1
            if cas_attempts == 1:
                await original_execute(
                    update(NumberSequence)
                    .where(NumberSequence.id == sequence.id, NumberSequence.version == 1)
                    .values(next_value=6, version=2)
                )
        return await original_execute(statement, *args, **kwargs)

    commit = AsyncMock(side_effect=AssertionError("reserve_number must not commit"))
    monkeypatch.setattr(db_session, "execute", execute_with_one_conflict)
    monkeypatch.setattr(db_session, "commit", commit)

    competing_number = format_number(
        pattern=sequence.pattern,
        prefix=sequence.prefix,
        value=5,
        effective_date=date(2026, 7, 10),
    )
    reserved_number = await reserve_number(
        db_session,
        business_profile_id=profile_id,
        key="customer",
        effective_date=date(2026, 7, 10),
    )

    assert {competing_number, reserved_number} == {"C-0005", "C-0006"}
    assert cas_attempts == 2
    assert commit.await_count == 0
    await db_session.refresh(sequence)
    assert sequence.next_value == 7
    assert sequence.version == 3


@pytest.mark.asyncio
async def test_optimistic_conflict_raises_after_ten_attempts_without_rollback(db_session, monkeypatch):
    profile_id, sequence = await _create_sequence(db_session)
    unrelated_profile = BusinessProfile(
        name="Unrelated",
        legal_name="Unrelated Ltd",
        country_code="IE",
        default_currency="EUR",
        timezone="Europe/Dublin",
        default_locale="en-IE",
        billing_mode="internal",
    )
    db_session.add(unrelated_profile)
    original_execute = db_session.execute
    cas_attempts = 0

    async def execute_with_conflicts(statement, *args, **kwargs):
        nonlocal cas_attempts
        if isinstance(statement, Update):
            cas_attempts += 1
            current_next_value = sequence.next_value
            current_version = sequence.version
            await original_execute(
                update(NumberSequence)
                .where(NumberSequence.id == sequence.id, NumberSequence.version == current_version)
                .values(next_value=current_next_value + 100, version=current_version + 1)
            )
        return await original_execute(statement, *args, **kwargs)

    commit = AsyncMock(side_effect=AssertionError("reserve_number must not commit"))
    rollback = AsyncMock(side_effect=AssertionError("reserve_number must not roll back caller work"))
    monkeypatch.setattr(db_session, "execute", execute_with_conflicts)
    monkeypatch.setattr(db_session, "commit", commit)
    monkeypatch.setattr(db_session, "rollback", rollback)

    with pytest.raises(VersionConflictError):
        await reserve_number(
            db_session,
            business_profile_id=profile_id,
            key="customer",
            effective_date=date(2026, 7, 10),
        )

    assert cas_attempts == 10
    assert commit.await_count == 0
    assert rollback.await_count == 0
    assert unrelated_profile in db_session
    assert unrelated_profile.id is not None
    assert inspect(sequence).expired
    await db_session.refresh(sequence)
    assert sequence.next_value == 1001
    assert sequence.next_value != 902
    assert sequence.version == 11


@pytest.mark.asyncio
async def test_sequential_reservations_across_sessions_are_unique(test_engine):
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions() as setup:
        profile_id, _sequence = await _create_sequence(
            setup,
            name="Sequential",
            prefix="CUS",
            pattern="{PREFIX}-{#####}",
        )

    async def reserve_one() -> str:
        async with sessions() as session:
            value = await reserve_number(
                session,
                business_profile_id=profile_id,
                key="customer",
                effective_date=date(2026, 7, 10),
            )
            await session.commit()
            return value

    values = [await reserve_one() for _ in range(10)]

    assert values == [f"CUS-{value:05d}" for value in range(1, 11)]
    assert len(values) == len(set(values)) == 10
