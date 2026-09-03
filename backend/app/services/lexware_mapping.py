"""Normalize external master data without applying it to a local record."""

from decimal import Decimal, InvalidOperation

from backend.app.models.customer import Customer
from backend.app.schemas.customer import (
    CustomerAccountInput,
    CustomerAddressInput,
    CustomerContactInput,
    CustomerTaxIdentifierInput,
)
from backend.app.services.lexware_client import LexwareError

CONTACT_FIELDS = {"identity", "customer_number", "addresses", "contacts", "tax_identifiers"}
ARTICLE_FIELDS = {"name", "description", "sale_price", "tax_rate"}
IDENTITY_FIELDS = ("kind", "display_name", "company_name", "first_name", "last_name")


def contact_source(payload: dict) -> dict:
    company, person = payload.get("company") or {}, payload.get("person") or {}
    name = company.get("name") or " ".join(filter(None, (person.get("firstName"), person.get("lastName"))))
    identity = {
        "kind": "company" if company else "person",
        "display_name": name,
        "company_name": company.get("name") if company else None,
        "first_name": person.get("firstName") if not company else None,
        "last_name": person.get("lastName") if not company else None,
    }
    addresses = []
    for source_kind, local_kind in (("billing", "billing"), ("shipping", "delivery")):
        for index, item in enumerate((payload.get("addresses") or {}).get(source_kind) or []):
            addresses.append(
                {
                    "kind": local_kind,
                    "additional": item.get("supplement"),
                    "street": item.get("street"),
                    "postal_code": item.get("zip"),
                    "city": item.get("city"),
                    "country_code": item.get("countryCode"),
                    "is_default": index == 0,
                }
            )
    contacts = [
        {
            "salutation": item.get("salutation"),
            "first_name": item.get("firstName"),
            "last_name": item.get("lastName"),
            "email": item.get("emailAddress"),
            "phone": item.get("phoneNumber"),
        }
        for item in company.get("contactPersons") or []
    ]
    for source_field, local_field in (("emailAddresses", "email"), ("phoneNumbers", "phone")):
        for label, values in (payload.get(source_field) or {}).items():
            for value in values or []:
                if value and not any(item.get(local_field) == value for item in contacts):
                    contacts.append({local_field: value, "role": str(label)})
    for index, contact in enumerate(contacts):
        contact["is_primary"] = index == 0
    taxes = [
        {"kind": kind, "value": company[field], "validation_status": "unchecked"}
        for field, kind in (("vatRegistrationId", "vat"), ("taxNumber", "tax_number"))
        if company.get(field)
    ]
    number = ((payload.get("roles") or {}).get("customer") or {}).get("number")
    customer_number = str(number).strip() if type(number) in {int, str} else None
    return {
        "identity": identity,
        "customer_number": customer_number or None,
        "addresses": addresses,
        "contacts": contacts,
        "tax_identifiers": taxes,
    }


def article_source(payload: dict) -> dict:
    price = payload.get("price") or {}
    try:
        sale_price, tax_rate = Decimal(str(price["netPrice"])), Decimal(str(price["taxRate"]))
        if not sale_price.is_finite() or not tax_rate.is_finite() or sale_price < 0 or not 0 <= tax_rate <= 100:
            raise ValueError
    except (KeyError, ValueError, InvalidOperation):
        raise LexwareError("Article price or tax rate is not supported for import", 422) from None
    return {
        "name": payload.get("title"),
        "description": payload.get("description"),
        "sale_price": str(sale_price),
        "tax_rate": str(tax_rate),
        "external_type": payload.get("type"),
        "unit_name": payload.get("unitName"),
    }


def customer_data(customer: Customer) -> dict:
    data = {field: getattr(customer, field) for field in (*IDENTITY_FIELDS, "status", "preferred_locale", "notes")}
    data.update(
        {
            "accounts": [
                CustomerAccountInput.model_validate(row, from_attributes=True).model_dump(mode="json")
                for row in customer.accounts
            ],
            "contacts": [
                CustomerContactInput.model_validate(row, from_attributes=True).model_dump(mode="json")
                for row in customer.contacts
            ],
            "addresses": [
                CustomerAddressInput.model_validate(row, from_attributes=True).model_dump(mode="json")
                for row in customer.addresses
            ],
            "tax_identifiers": [
                CustomerTaxIdentifierInput.model_validate(row, from_attributes=True).model_dump(mode="json")
                for row in customer.tax_identifiers
            ],
            "tags": [tag.name for tag in customer.tags],
        }
    )
    return data


def customer_preview_data(customer: Customer, business_profile_id: int) -> dict:
    data = customer_data(customer)
    return {
        "identity": {key: data[key] for key in IDENTITY_FIELDS},
        "customer_number": next(
            account.number for account in customer.accounts if account.business_profile_id == business_profile_id
        ),
        **{key: data[key] for key in ("addresses", "contacts", "tax_identifiers")},
    }
