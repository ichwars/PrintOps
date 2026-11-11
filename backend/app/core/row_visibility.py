"""Apply resource permissions and printer scope through related API resources."""

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    OwnershipAccess,
    _required_apikey_scopes,
    _user_from_api_key,
    allowed_printer_ids_for_user,
    is_auth_enabled,
)
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.user import User


@dataclass(frozen=True, slots=True)
class RowVisibility:
    user: User | None
    api_key: APIKey | None
    anonymous_allowed: bool

    @property
    def has_caller(self) -> bool:
        return (
            self.user is not None
            or self.anonymous_allowed
            or (self.api_key is not None and self.api_key.user_id is None)
        )

    def _ownership(
        self, all_permission: Permission, own_permission: Permission, key_permission: Permission | None = None
    ) -> tuple[bool, int | None]:
        if not self.has_caller:
            return False, None
        if self.api_key is not None:
            scopes = _required_apikey_scopes((key_permission or all_permission).value)
            if not scopes or not all(getattr(self.api_key, scope, False) for scope in scopes):
                return False, None

        if self.user is None or self.user.has_permission(all_permission.value):
            return True, None
        if self.user.has_permission(own_permission.value):
            return False, self.user.id
        return False, None

    def can_access_owner(self, owner_id: int | None, all_permission: Permission, own_permission: Permission) -> bool:
        allows_all, allowed_owner = self._ownership(all_permission, own_permission)
        return allows_all or (allowed_owner is not None and owner_id == allowed_owner)

    def has_permission(self, permission: Permission) -> bool:
        return self.can_access_owner(None, permission, permission)

    @property
    def printer_ids(self) -> set[int] | None:
        user_scope = allowed_printer_ids_for_user(self.user)
        key_scope = self.api_key.printer_ids if self.api_key is not None else None
        if key_scope is None:
            return user_scope
        return set(key_scope) if user_scope is None else user_scope.intersection(key_scope)

    @property
    def can_use_model_target(self) -> bool:
        """The scheduler can retain the creator's grants, but not a narrower key's grants."""
        return self.api_key is None or (self.user is not None and self.api_key.printer_ids is None)

    def allows_printer(self, printer_id: int) -> bool:
        scope = self.printer_ids
        return self.has_caller and (scope is None or printer_id in scope)

    def criteria(
        self,
        owner_column,
        all_permission: Permission,
        own_permission: Permission,
        printer_column=None,
        *,
        key_permission: Permission | None = None,
    ):
        allows_all, allowed_owner = self._ownership(all_permission, own_permission, key_permission)
        if not allows_all and allowed_owner is None:
            return (false(),)
        conditions = [] if allows_all else [owner_column == allowed_owner]
        if printer_column is not None:
            conditions.extend(self.printer_criteria(printer_column))
        return tuple(conditions)

    def printer_criteria(self, printer_column):
        allowed = self.printer_ids
        if allowed is None:
            return ()
        assigned = printer_column.in_(allowed)
        if self.api_key is not None and self.api_key.printer_ids is not None:
            return (assigned,)
        return (or_(printer_column.is_(None), assigned),)


async def resolve_row_visibility(db: AsyncSession, user: User | None, api_key: APIKey | None) -> RowVisibility:
    if api_key is not None:
        return RowVisibility(await _user_from_api_key(db, api_key), api_key, False)
    return RowVisibility(user, None, user is None and not await is_auth_enabled(db))


async def resolve_printer_visibility(
    db: AsyncSession, access: OwnershipAccess, permission: Permission, printer_id: int | None = None
) -> RowVisibility:
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    if not visibility.has_permission(permission):
        raise HTTPException(403, f"Missing permission: {permission.value}")
    if printer_id is not None and not visibility.allows_printer(printer_id):
        raise HTTPException(404, "Printer not found")
    return visibility


def archive_read_access(visibility: RowVisibility) -> OwnershipAccess:
    can_read_all = visibility.has_permission(Permission.ARCHIVES_READ_ALL)
    return OwnershipAccess(visibility.user, can_read_all, visibility.api_key)


def archive_read_criteria(visibility: RowVisibility):
    from backend.app.services.archive_scope import archive_printer_conditions

    return (
        PrintArchive.deleted_at.is_(None),
        *visibility.criteria(PrintArchive.created_by_id, Permission.ARCHIVES_READ_ALL, Permission.ARCHIVES_READ_OWN),
        *archive_printer_conditions(archive_read_access(visibility), include_runs=True),
    )


async def visible_archive_names(
    db: AsyncSession, archive_ids: Iterable[int | None], visibility: RowVisibility
) -> dict[int, str | None]:
    ids = {archive_id for archive_id in archive_ids if archive_id is not None}
    if not ids:
        return {}
    rows = await db.execute(
        select(PrintArchive.id, PrintArchive.print_name).where(
            PrintArchive.id.in_(ids), *archive_read_criteria(visibility)
        )
    )
    return dict(rows.all())


def library_read_criteria(visibility: RowVisibility):
    return visibility.criteria(LibraryFile.created_by_id, Permission.LIBRARY_READ_ALL, Permission.LIBRARY_READ_OWN)


async def require_queue_creation(db: AsyncSession, user: User | None, api_key: APIKey | None) -> RowVisibility:
    visibility = await resolve_row_visibility(db, user, api_key)
    if not visibility.can_access_owner(None, Permission.QUEUE_CREATE, Permission.QUEUE_CREATE):
        raise HTTPException(403, "Missing permission: queue:create")
    return visibility


async def require_archive_source(db: AsyncSession, archive_id: int, visibility: RowVisibility) -> PrintArchive:
    archive = await db.scalar(
        select(PrintArchive).where(PrintArchive.id == archive_id, *archive_read_criteria(visibility))
    )
    if archive is None:
        raise HTTPException(404, "Archive not found")
    if not visibility.can_access_owner(
        archive.created_by_id, Permission.ARCHIVES_REPRINT_ALL, Permission.ARCHIVES_REPRINT_OWN
    ):
        raise HTTPException(403, "Permission archives:reprint_own or archives:reprint_all required")
    return archive


async def require_library_source(db: AsyncSession, file_id: int, visibility: RowVisibility) -> LibraryFile:
    library_file = await db.scalar(
        LibraryFile.active().where(LibraryFile.id == file_id, *library_read_criteria(visibility))
    )
    if library_file is None:
        raise HTTPException(404, "Library file not found")
    return library_file
