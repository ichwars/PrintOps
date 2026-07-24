import pytest
from pydantic import ValidationError

from backend.app.schemas.document_configuration import PublishConfigurationRequest
from backend.app.services.einvoice.validator import pinned_rule_versions
from backend.app.services.tax_decision import TAX_RULES_2026_1


def test_publish_configuration_accepts_only_user_owned_fields() -> None:
    command = PublishConfigurationRequest.model_validate(
        {
            "expected_version": 3,
            "effective_from": "2026-08-01",
            "reason": "Updated invoice terms",
        }
    )

    assert command.expected_version == 3

    with pytest.raises(ValidationError):
        PublishConfigurationRequest.model_validate(
            {
                "expected_version": 3,
                "effective_from": "2026-08-01",
                "reason": "Updated invoice terms",
                "rule_versions": {"en16931": "untrusted-client-value"},
            }
        )


def test_publication_rule_versions_come_from_pinned_backend_rules() -> None:
    versions = {"tax": TAX_RULES_2026_1.version, **pinned_rule_versions()}

    assert versions == {
        "tax": "2026.1",
        "en16931": "1.3.16",
        "xrechnung": "3.0.2-2026-01-31",
        "zugferd": "2.5",
        "factur_x": "1.09",
    }
