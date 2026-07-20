"""Strict schema contracts for document configuration commands and effective values."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.schemas.document_configuration import PublishConfigurationCommand, SourcedValue


def test_publish_command_requires_positive_version_and_meaningful_reason():
    with pytest.raises(ValidationError):
        PublishConfigurationCommand(expected_version=0, effective_from=date.today(), reason="x")


def test_sourced_value_rejects_unknown_provenance():
    with pytest.raises(ValidationError):
        SourcedValue[int](value=14, source="guess", overridable=True)


def test_publish_command_strips_reason_whitespace():
    command = PublishConfigurationCommand(
        expected_version=1,
        effective_from=date.today(),
        reason="  Neue Zahlungsbedingungen  ",
    )

    assert command.reason == "Neue Zahlungsbedingungen"
