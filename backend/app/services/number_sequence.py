from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.number_sequence import NumberSequence
from backend.app.services.order_errors import ResourceNotFoundError, VersionConflictError

_TOKEN_PATTERN = re.compile(r"\{[^{}]*\}")
_COUNTER_PATTERN = re.compile(r"\{(#{1,10})\}")
_NAMED_TOKENS = {"{PREFIX}", "{YYYY}", "{YY}"}
_MAX_RESERVATION_ATTEMPTS = 10


def _counter_token(pattern: str) -> str:
    counter_tokens: list[str] = []
    previous_end = 0

    for match in _TOKEN_PATTERN.finditer(pattern):
        literal = pattern[previous_end : match.start()]
        if "{" in literal or "}" in literal:
            raise ValueError("Number pattern contains malformed braces")

        token = match.group(0)
        if token in _NAMED_TOKENS:
            pass
        elif _COUNTER_PATTERN.fullmatch(token):
            counter_tokens.append(token)
        else:
            raise ValueError(f"Unsupported number pattern token: {token}")
        previous_end = match.end()

    trailing_literal = pattern[previous_end:]
    if "{" in trailing_literal or "}" in trailing_literal:
        raise ValueError("Number pattern contains malformed braces")
    if len(counter_tokens) != 1:
        raise ValueError("Number pattern must contain exactly one counter token")
    return counter_tokens[0]


def validate_number_pattern(pattern: str) -> None:
    _counter_token(pattern)


def _parse_yearly_period(current_period: str) -> int:
    if not re.fullmatch(r"[0-9]{4}", current_period):
        raise ValueError("Yearly sequence current_period must be a four-digit year from 0001 through 9999")

    current_year = int(current_period)
    if current_year == 0:
        raise ValueError("Yearly sequence current_period must be a four-digit year from 0001 through 9999")
    return current_year


def format_number(*, pattern: str, prefix: str, value: int, effective_date: date) -> str:
    validate_number_pattern(pattern)
    if value <= 0:
        raise ValueError("Number value must be positive")

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "{PREFIX}":
            return prefix
        if token == "{YYYY}":
            return f"{effective_date.year:04d}"
        if token == "{YY}":
            return f"{effective_date.year % 100:02d}"

        counter_width = len(token) - 2
        return f"{value:0{counter_width}d}"

    return _TOKEN_PATTERN.sub(replace_token, pattern)


async def reserve_number(
    session: AsyncSession,
    *,
    business_profile_id: int,
    key: str,
    effective_date: date,
) -> str:
    result = await session.execute(
        select(NumberSequence).where(
            NumberSequence.business_profile_id == business_profile_id,
            NumberSequence.key == key,
        )
    )
    sequence = result.scalar_one_or_none()
    if sequence is None:
        raise ResourceNotFoundError(
            f"Number sequence not found for business profile {business_profile_id} and key '{key}'"
        )

    for attempt in range(_MAX_RESERVATION_ATTEMPTS):
        if sequence.reset_policy == "yearly":
            period = f"{effective_date.year:04d}"
            if sequence.current_period is None:
                reserved_value = 1
            else:
                current_year = _parse_yearly_period(sequence.current_period)
                if effective_date.year < current_year:
                    raise ValueError(
                        f"Effective year {period} precedes current sequence period {sequence.current_period}"
                    )
                reserved_value = sequence.next_value if effective_date.year == current_year else 1
        else:
            period = sequence.current_period
            reserved_value = sequence.next_value

        statement = (
            update(NumberSequence)
            .where(NumberSequence.id == sequence.id, NumberSequence.version == sequence.version)
            .values(
                next_value=reserved_value + 1,
                current_period=period,
                version=NumberSequence.version + 1,
            )
            .returning(NumberSequence.id)
        )
        update_result = await session.execute(statement)
        if update_result.scalar_one_or_none() is not None:
            return format_number(
                pattern=sequence.pattern,
                prefix=sequence.prefix,
                value=reserved_value,
                effective_date=effective_date,
            )

        session.expire(sequence)
        if attempt < _MAX_RESERVATION_ATTEMPTS - 1:
            await session.refresh(sequence)

    raise VersionConflictError(
        f"Could not reserve number for business profile {business_profile_id} and key '{key}'"
    )
