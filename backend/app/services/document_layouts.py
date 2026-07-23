"""Typed inheritance and lifecycle service for commercial-document layouts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models import document_layout as orm
from backend.app.models.business_profile import BusinessProfile
from backend.app.schemas import document_layout as dto
from backend.app.services.document_audit import append_or_merge_layout_edit_session
from backend.app.services.document_layout_catalog import (
    RENDERER_VERSION,
    TEMPLATE_VERSIONS,
    VALIDATOR_VERSION,
)
from backend.app.services.document_layout_defaults import SYSTEM_DEFAULT, TEMPLATE_DEFAULTS


class LayoutNotFoundError(LookupError):
    pass


class LayoutConflictError(RuntimeError):
    pass


class LayoutStateError(RuntimeError):
    pass


class LayoutReadinessError(RuntimeError):
    def __init__(self, report: dto.LayoutReadinessReport) -> None:
        self.report = report
        super().__init__("layout is not ready for publication")


@dataclass(frozen=True)
class ResolvedLayout:
    effective: dto.EffectiveDocumentLayout
    sourced: dto.SourcedDocumentLayout
    effective_sha256: str
    configuration_ids: tuple[int, ...]


@dataclass(frozen=True)
class _RuleBinding:
    relationship: str
    model: type
    schema_prefix: str


RULE_BINDINGS: dict[str, _RuleBinding] = {
    "page": _RuleBinding("page_rules", orm.LayoutPageRules, "Page"),
    "typography": _RuleBinding("typography_rules", orm.LayoutTypographyRules, "Typography"),
    "header": _RuleBinding("header_rules", orm.LayoutHeaderRules, "Header"),
    "title": _RuleBinding("title_rules", orm.LayoutTitleRules, "Title"),
    "positions": _RuleBinding("position_rules", orm.LayoutPositionRules, "Position"),
    "totals": _RuleBinding("totals_rules", orm.LayoutTotalsRules, "Totals"),
    "technical": _RuleBinding("technical_rules", orm.LayoutTechnicalRules, "Technical"),
    "notes": _RuleBinding("notes_rules", orm.LayoutNotesRules, "Notes"),
    "footer": _RuleBinding("footer_rules", orm.LayoutFooterRules, "Footer"),
}
_CONFIG_PAGE_FIELDS = frozenset({"template_key", "page_format", "orientation"})


def _patch_targets() -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for section, binding in RULE_BINDINGS.items():
        patch_model = getattr(dto, f"{binding.schema_prefix}RulesPatch")
        for field in patch_model.model_fields:
            target = "configuration" if section == "page" and field in _CONFIG_PAGE_FIELDS else binding.relationship
            result[f"{section}.{field}"] = (target, field)
    return result


PATCH_TARGETS = _patch_targets()


def canonical_effective_sha256(layout: dto.EffectiveDocumentLayout) -> str:
    payload = json.dumps(
        layout.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _scope_key(document_type: str | None, language: str | None) -> str:
    return f"{document_type or '*'}|{language or '*'}"


def _layout_options() -> tuple:
    return tuple(
        selectinload(getattr(orm.DocumentLayoutConfiguration, binding.relationship))
        for binding in RULE_BINDINGS.values()
    ) + (
        selectinload(orm.DocumentLayoutConfiguration.asset_links).selectinload(
            orm.DocumentLayoutAssetLink.asset
        ),
    )


def _layout_query() -> Select:
    return select(orm.DocumentLayoutConfiguration).options(*_layout_options())


async def get_layout(
    session: AsyncSession, layout_id: int, *, for_update: bool = False
) -> orm.DocumentLayoutConfiguration:
    statement = _layout_query().where(orm.DocumentLayoutConfiguration.id == layout_id)
    if for_update:
        statement = statement.with_for_update()
    layout = await session.scalar(statement)
    if layout is None:
        raise LayoutNotFoundError(f"layout {layout_id} was not found")
    return layout


def _section_values(layout: orm.DocumentLayoutConfiguration, section: str) -> dict[str, Any]:
    binding = RULE_BINDINGS[section]
    target = getattr(layout, binding.relationship)
    if target is None:
        raise LayoutStateError(f"layout {layout.id} has no {section} rules")
    values = {
        column.name: getattr(target, column.name)
        for column in binding.model.__table__.columns
        if column.name != "configuration_id"
    }
    if section == "page":
        values.update(
            template_key=layout.template_key,
            page_format=layout.page_format,
            orientation=layout.orientation,
        )
    return values


def _attach_template_rules(
    layout: orm.DocumentLayoutConfiguration, template: dto.EffectiveDocumentLayout
) -> None:
    for section, binding in RULE_BINDINGS.items():
        values = getattr(template, section).model_dump()
        if section == "page":
            values = {key: value for key, value in values.items() if key not in _CONFIG_PAGE_FIELDS}
        setattr(layout, binding.relationship, binding.model(**values))


def _override_fields(layout: orm.DocumentLayoutConfiguration) -> set[str]:
    return set((layout.validation_report or {}).get("override_fields", []))


def _source_level(layout: orm.DocumentLayoutConfiguration) -> str:
    if layout.language is not None:
        return "language"
    if layout.document_type is not None:
        return "document_type"
    return "profile"


async def _append_lifecycle_receipt(
    session: AsyncSession,
    *,
    layout: orm.DocumentLayoutConfiguration,
    event_type: str,
    actor_id: int | None,
    reason: str,
    evidence: dict | None = None,
) -> orm.DocumentLayoutAuditReceipt:
    now = datetime.now(UTC)
    receipt = orm.DocumentLayoutAuditReceipt(
        configuration_id=layout.id,
        event_type=event_type,
        reason=reason.strip(),
        changed_field_paths=[],
        actor_id=actor_id,
        before_lock_version=layout.lock_version,
        after_lock_version=layout.lock_version,
        first_seen_at=now,
        last_seen_at=now,
        evidence=evidence or {},
    )
    session.add(receipt)
    return receipt


async def create_draft(
    session: AsyncSession,
    command: dto.CreateLayoutRequest,
    *,
    actor_id: int | None,
) -> orm.DocumentLayoutConfiguration:
    scope = command.scope
    if await session.get(BusinessProfile, scope.business_profile_id) is None:
        raise LayoutNotFoundError(f"business profile {scope.business_profile_id} was not found")
    scope_key = _scope_key(scope.document_type, scope.language)
    current_version = await session.scalar(
        select(func.max(orm.DocumentLayoutConfiguration.version)).where(
            orm.DocumentLayoutConfiguration.business_profile_id == scope.business_profile_id,
            orm.DocumentLayoutConfiguration.scope_key == scope_key,
        )
    )
    template = TEMPLATE_DEFAULTS[command.template_key]
    overrides = []
    if scope.document_type is not None and "template_key" in command.model_fields_set:
        overrides.append("page.template_key")
    layout = orm.DocumentLayoutConfiguration(
        business_profile_id=scope.business_profile_id,
        document_type=scope.document_type,
        language=scope.language,
        scope_key=scope_key,
        version=(current_version or 0) + 1,
        status="draft",
        template_key=command.template_key,
        page_format=template.page.page_format,
        orientation=template.page.orientation,
        lock_version=1,
        change_reason=command.reason,
        created_by_id=actor_id,
        validation_status="pending",
        validation_report={"override_fields": overrides},
    )
    _attach_template_rules(layout, template)
    session.add(layout)
    await session.flush()
    await _append_lifecycle_receipt(
        session,
        layout=layout,
        event_type="created",
        actor_id=actor_id,
        reason=command.reason,
    )
    await session.flush()
    return layout


async def clone_layout(
    session: AsyncSession,
    command: dto.CloneLayoutRequest,
    *,
    actor_id: int | None,
) -> orm.DocumentLayoutConfiguration:
    source = await get_layout(session, command.source_layout_id, for_update=True)
    if not command.reason.strip():
        raise ValueError("a clone reason is required")
    current_version = await session.scalar(
        select(func.max(orm.DocumentLayoutConfiguration.version)).where(
            orm.DocumentLayoutConfiguration.business_profile_id == source.business_profile_id,
            orm.DocumentLayoutConfiguration.scope_key == source.scope_key,
        )
    )
    clone = orm.DocumentLayoutConfiguration(
        business_profile_id=source.business_profile_id,
        document_type=source.document_type,
        language=source.language,
        scope_key=source.scope_key,
        version=(current_version or 0) + 1,
        status="draft",
        template_key=source.template_key,
        page_format=source.page_format,
        orientation=source.orientation,
        lock_version=1,
        change_reason=command.reason,
        created_by_id=actor_id,
        validation_status="pending",
        validation_report={"override_fields": sorted(_override_fields(source))},
    )
    for section, binding in RULE_BINDINGS.items():
        values = _section_values(source, section)
        values = {key: value for key, value in values.items() if key not in _CONFIG_PAGE_FIELDS}
        setattr(clone, binding.relationship, binding.model(**values))
    clone.asset_links = [
        orm.DocumentLayoutAssetLink(asset_id=link.asset_id, role=link.role)
        for link in source.asset_links
    ]
    session.add(clone)
    await session.flush()
    await _append_lifecycle_receipt(
        session,
        layout=clone,
        event_type="cloned",
        actor_id=actor_id,
        reason=command.reason,
        evidence={"source_layout_id": source.id},
    )
    await session.flush()
    return clone


async def patch_draft(
    session: AsyncSession,
    layout_id: int,
    command: dto.PatchLayoutRequest,
    *,
    actor_id: int | None,
) -> orm.DocumentLayoutConfiguration:
    layout = await get_layout(session, layout_id)
    if layout.status != "draft":
        raise LayoutStateError("only draft layouts can be edited")
    mutations: list[tuple[str, str, Any, str]] = []
    override_fields = _override_fields(layout)
    for section in RULE_BINDINGS:
        patch_section = getattr(command, section)
        if patch_section is None:
            continue
        for field in patch_section.model_fields_set:
            path = f"{section}.{field}"
            target, attribute = PATCH_TARGETS[path]
            value = getattr(patch_section, field)
            if value is None:
                if layout.document_type is None:
                    raise ValueError(f"profile default field {path} cannot be cleared")
                override_fields.discard(path)
                continue
            override_fields.add(path)
            mutations.append((target, attribute, value, path))
    changed_paths = sorted(
        {
            f"{section}.{field}"
            for section in RULE_BINDINGS
            if (patch_section := getattr(command, section)) is not None
            for field in patch_section.model_fields_set
        }
    )
    if not changed_paths:
        return layout
    config_values: dict[str, Any] = {
        "lock_version": command.expected_lock_version + 1,
        "validation_status": "pending",
        "validation_report": {"override_fields": sorted(override_fields)},
    }
    for target, attribute, value, _path in mutations:
        if target == "configuration":
            config_values[attribute] = value
    result = await session.execute(
        update(orm.DocumentLayoutConfiguration)
        .where(
            orm.DocumentLayoutConfiguration.id == layout_id,
            orm.DocumentLayoutConfiguration.status == "draft",
            orm.DocumentLayoutConfiguration.lock_version == command.expected_lock_version,
        )
        .values(**config_values)
    )
    if result.rowcount != 1:
        raise LayoutConflictError("layout was changed by another editor")
    for target, attribute, value, _path in mutations:
        if target == "configuration":
            continue
        rule = getattr(layout, target)
        rule._allow_layout_lifecycle_mutation = True
        setattr(rule, attribute, value)
    await session.flush()
    await append_or_merge_layout_edit_session(
        session,
        layout=layout,
        edit_session_id=command.edit_session_id,
        actor_id=actor_id,
        changed_field_paths=changed_paths,
        before_lock_version=command.expected_lock_version,
        after_lock_version=command.expected_lock_version + 1,
    )
    await session.flush()
    session.expire(layout)
    return await get_layout(session, layout_id)


async def _active_for_scope(
    session: AsyncSession,
    *,
    business_profile_id: int,
    document_type: str | None,
    language: str | None,
    now: datetime,
) -> orm.DocumentLayoutConfiguration | None:
    return await session.scalar(
        _layout_query()
        .where(
            orm.DocumentLayoutConfiguration.business_profile_id == business_profile_id,
            orm.DocumentLayoutConfiguration.scope_key == _scope_key(document_type, language),
            orm.DocumentLayoutConfiguration.status == "active",
            orm.DocumentLayoutConfiguration.effective_from <= now,
        )
        .order_by(orm.DocumentLayoutConfiguration.version.desc())
        .limit(1)
    )


async def resolve_effective_layout(
    session: AsyncSession,
    *,
    business_profile_id: int,
    document_type: str | None = None,
    language: str | None = None,
    draft_layout_id: int | None = None,
    now: datetime | None = None,
) -> ResolvedLayout:
    if language is not None and document_type is None:
        raise ValueError("language requires document_type")
    now = now or datetime.now(UTC)
    layers: list[orm.DocumentLayoutConfiguration] = []
    for scope_type, scope_language in (
        (None, None),
        (document_type, None) if document_type else (None, None),
        (document_type, language) if language else (None, None),
    ):
        if (scope_type, scope_language) == (None, None) and layers:
            continue
        layer = await _active_for_scope(
            session,
            business_profile_id=business_profile_id,
            document_type=scope_type,
            language=scope_language,
            now=now,
        )
        if layer is not None:
            layers.append(layer)
    draft = await get_layout(session, draft_layout_id) if draft_layout_id is not None else None
    if draft is not None:
        if draft.business_profile_id != business_profile_id:
            raise ValueError("draft belongs to another business profile")
        layers = [layer for layer in layers if layer.scope_key != draft.scope_key]
        layers.append(draft)
        layers.sort(key=lambda item: (item.document_type is not None, item.language is not None))

    effective_data = SYSTEM_DEFAULT.model_dump()
    source_data: dict[str, dict[str, dto.ValueSource]] = {}
    system_source = dto.ValueSource(level="system")
    for section in RULE_BINDINGS:
        source_data[section] = dict.fromkeys(effective_data[section], system_source)
    for layer in layers:
        level = _source_level(layer)
        source = dto.ValueSource(
            level=level,
            configuration_id=layer.id,
            version=layer.version,
        )
        overrides = _override_fields(layer)
        for section in RULE_BINDINGS:
            for field, value in _section_values(layer, section).items():
                path = f"{section}.{field}"
                if level == "profile" or path in overrides:
                    effective_data[section][field] = value
                    source_data[section][field] = source
    effective_data["template_version"] = TEMPLATE_VERSIONS[
        effective_data["page"]["template_key"]
    ]
    effective_data["renderer_version"] = RENDERER_VERSION
    effective_data["validator_version"] = VALIDATOR_VERSION
    effective = dto.EffectiveDocumentLayout.model_validate(effective_data)
    sourced_sections: dict[str, Any] = {}
    for section, binding in RULE_BINDINGS.items():
        sources_type = getattr(dto, f"{binding.schema_prefix}RulesSources")
        value_type = getattr(dto, f"{binding.schema_prefix}RulesSourcedValue")
        sourced_sections[section] = value_type(
            value=getattr(effective, section),
            sources=sources_type(**source_data[section]),
        )
    sourced = dto.SourcedDocumentLayout(effective=effective, **sourced_sections)
    return ResolvedLayout(
        effective=effective,
        sourced=sourced,
        effective_sha256=canonical_effective_sha256(effective),
        configuration_ids=tuple(layer.id for layer in layers),
    )


async def check_readiness(
    session: AsyncSession,
    *,
    business_profile_id: int,
    document_type: str | None = None,
    language: str | None = None,
    draft_layout_id: int | None = None,
) -> dto.LayoutReadinessReport:
    findings: list[dto.LayoutFinding] = []
    draft = await get_layout(session, draft_layout_id) if draft_layout_id is not None else None
    active_profile_defaults = (
        await session.scalars(
            _layout_query().where(
                orm.DocumentLayoutConfiguration.business_profile_id == business_profile_id,
                orm.DocumentLayoutConfiguration.scope_key == _scope_key(None, None),
                orm.DocumentLayoutConfiguration.status == "active",
            )
        )
    ).all()
    if len(active_profile_defaults) > 1:
        findings.append(
            dto.LayoutFinding(
                code="profile_default_ambiguous",
                severity="blocker",
                field_path=None,
                message_key="documents.layout.readiness.profile_default_ambiguous",
                message="Für das Unternehmensprofil sind mehrere Standardlayouts aktiv.",
                correction_hint="Nur eine Profilstandard-Version aktiv lassen.",
            )
        )
    current_profile_default = await _active_for_scope(
        session,
        business_profile_id=business_profile_id,
        document_type=None,
        language=None,
        now=datetime.now(UTC),
    )
    if current_profile_default is None and not (
        draft is not None and draft.document_type is None and draft.language is None
    ):
        findings.append(
            dto.LayoutFinding(
                code="profile_default_missing",
                severity="blocker",
                field_path=None,
                message_key="documents.layout.readiness.profile_default_missing",
                message="Für das Unternehmensprofil fehlt ein aktives Standardlayout.",
                correction_hint="Ein Profilstandard-Layout prüfen und freigeben.",
            )
        )
    try:
        await resolve_effective_layout(
            session,
            business_profile_id=business_profile_id,
            document_type=document_type,
            language=language,
            draft_layout_id=draft_layout_id,
        )
    except (ValueError, LayoutStateError) as exc:
        findings.append(
            dto.LayoutFinding(
                code="layout_resolution_failed",
                severity="blocker",
                field_path=None,
                message_key="documents.layout.readiness.resolution_failed",
                message=str(exc),
                correction_hint="Die markierten Layoutwerte korrigieren.",
            )
        )
    if draft is not None:
        for link in draft.asset_links:
            if link.asset.preflight_status != "valid":
                findings.append(
                    dto.LayoutFinding(
                        code="asset_preflight_incomplete",
                        severity="blocker",
                        field_path=f"assets.{link.role}",
                        message_key="documents.layout.readiness.asset_preflight_incomplete",
                        message=f"Asset {link.role} hat die Vorprüfung nicht bestanden.",
                        correction_hint="Asset ersetzen oder erneut vorprüfen.",
                    )
                )
    return dto.LayoutReadinessReport(
        ready=not any(finding.severity == "blocker" for finding in findings),
        findings=tuple(findings),
        renderer_version=RENDERER_VERSION,
        validator_version=VALIDATOR_VERSION,
    )


# Stable domain vocabulary used by the API and background activation job.
clone_version = clone_layout
resolve_effective = resolve_effective_layout


async def publish_layout(
    session: AsyncSession,
    layout_id: int,
    command: dto.PublishLayoutRequest,
    *,
    actor_id: int | None,
    now: datetime | None = None,
) -> orm.DocumentLayoutConfiguration:
    now = now or datetime.now(UTC)
    layout = await get_layout(session, layout_id, for_update=True)
    if layout.status != "draft":
        raise LayoutStateError("only draft layouts can be published")
    report = await check_readiness(
        session,
        business_profile_id=layout.business_profile_id,
        document_type=layout.document_type,
        language=layout.language,
        draft_layout_id=layout.id,
    )
    if not report.ready:
        raise LayoutReadinessError(report)
    resolved = await resolve_effective_layout(
        session,
        business_profile_id=layout.business_profile_id,
        document_type=layout.document_type,
        language=layout.language,
        draft_layout_id=layout.id,
        now=now,
    )
    effective_from = command.effective_from or now
    next_status = "scheduled" if effective_from > now else "active"
    persisted_report = report.model_dump(mode="json")
    persisted_report["override_fields"] = sorted(_override_fields(layout))
    if next_status == "active":
        await session.execute(
            update(orm.DocumentLayoutConfiguration)
            .where(
                orm.DocumentLayoutConfiguration.business_profile_id == layout.business_profile_id,
                orm.DocumentLayoutConfiguration.scope_key == layout.scope_key,
                orm.DocumentLayoutConfiguration.status == "active",
            )
            .values(status="superseded")
        )
    result = await session.execute(
        update(orm.DocumentLayoutConfiguration)
        .where(
            orm.DocumentLayoutConfiguration.id == layout.id,
            orm.DocumentLayoutConfiguration.status == "draft",
            orm.DocumentLayoutConfiguration.lock_version == command.expected_lock_version,
        )
        .values(
            status=next_status,
            effective_from=effective_from,
            change_reason=command.reason,
            published_by_id=actor_id,
            published_at=now,
            renderer_version=RENDERER_VERSION,
            validator_version=VALIDATOR_VERSION,
            validation_status="valid",
            validation_report=persisted_report,
            lock_version=command.expected_lock_version + 1,
        )
    )
    if result.rowcount != 1:
        raise LayoutConflictError("layout was changed by another editor")
    asset_receipts = {
        link.role: {"asset_id": link.asset_id, "sha256": link.asset.sha256}
        for link in layout.asset_links
    }
    session.add(
        orm.DocumentLayoutPublication(
            configuration_id=layout.id,
            effective_sha256=resolved.effective_sha256,
            asset_receipts=asset_receipts,
            renderer_version=RENDERER_VERSION,
            validator_version=VALIDATOR_VERSION,
            validation_status="valid",
            validation_report=report.model_dump(mode="json"),
            published_by_id=actor_id,
        )
    )
    await _append_lifecycle_receipt(
        session,
        layout=layout,
        event_type="scheduled" if next_status == "scheduled" else "published",
        actor_id=actor_id,
        reason=command.reason,
        evidence={"effective_sha256": resolved.effective_sha256},
    )
    await session.flush()
    session.expire(layout)
    return await get_layout(session, layout_id)


async def activate_due_layouts(
    session: AsyncSession, *, now: datetime | None = None
) -> tuple[int, ...]:
    now = now or datetime.now(UTC)
    scheduled = (
        await session.scalars(
            _layout_query()
            .where(
                orm.DocumentLayoutConfiguration.status == "scheduled",
                orm.DocumentLayoutConfiguration.effective_from <= now,
            )
            .order_by(orm.DocumentLayoutConfiguration.effective_from)
            .with_for_update()
        )
    ).all()
    activated: list[int] = []
    for layout in scheduled:
        await session.execute(
            update(orm.DocumentLayoutConfiguration)
            .where(
                orm.DocumentLayoutConfiguration.business_profile_id == layout.business_profile_id,
                orm.DocumentLayoutConfiguration.scope_key == layout.scope_key,
                orm.DocumentLayoutConfiguration.status == "active",
            )
            .values(status="superseded")
        )
        await session.execute(
            update(orm.DocumentLayoutConfiguration)
            .where(
                orm.DocumentLayoutConfiguration.id == layout.id,
                orm.DocumentLayoutConfiguration.status == "scheduled",
            )
            .values(status="active")
        )
        activated.append(layout.id)
    return tuple(activated)


async def withdraw_scheduled_layout(
    session: AsyncSession,
    layout_id: int,
    command: dto.WithdrawLayoutRequest,
    *,
    actor_id: int | None,
) -> orm.DocumentLayoutConfiguration:
    layout = await get_layout(session, layout_id, for_update=True)
    if layout.status != "scheduled":
        raise LayoutStateError("only scheduled layouts can be withdrawn")
    await session.execute(
        update(orm.DocumentLayoutConfiguration)
        .where(
            orm.DocumentLayoutConfiguration.id == layout.id,
            orm.DocumentLayoutConfiguration.status == "scheduled",
        )
        .values(status="withdrawn", change_reason=command.reason)
    )
    await _append_lifecycle_receipt(
        session,
        layout=layout,
        event_type="withdrawn",
        actor_id=actor_id,
        reason=command.reason,
    )
    await session.flush()
    session.expire(layout)
    return await get_layout(session, layout_id)


publish = publish_layout
activate_due_versions = activate_due_layouts
withdraw = withdraw_scheduled_layout
