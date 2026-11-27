from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, _check_apikey_permissions, is_auth_enabled
from backend.app.core.permissions import Permission
from backend.app.models.project import Project
from backend.app.models.project_production import ProjectProductionOutput
from backend.app.schemas.project import ProjectProductionDestination
from backend.app.services import project_production
from backend.app.services.warehouse_articles import WarehouseError


def production_destination(output: ProjectProductionOutput | None) -> ProjectProductionDestination | None:
    if output is None:
        return None
    return ProjectProductionDestination.model_validate(output)


async def update_production_output(
    db: AsyncSession,
    project: Project,
    access: OwnershipAccess,
    destination: ProjectProductionDestination | None,
    *,
    completing: bool = False,
) -> ProjectProductionDestination | None:
    output = await db.get(ProjectProductionOutput, project.id)
    if destination is None and not (completing and output is not None):
        return production_destination(output)
    user = access.user
    if access.api_key is not None:
        _check_apikey_permissions(access.api_key, [Permission.INVENTORY_UPDATE.value])
    else:
        permitted = user.has_permission(Permission.INVENTORY_UPDATE.value) if user else not await is_auth_enabled(db)
        if not permitted:
            raise HTTPException(status_code=403, detail="inventory:update is required for production stock")
    try:
        if destination is not None:
            if project.is_template:
                raise WarehouseError("production_template", "Projektvorlagen können keinen Wareneingang buchen.", 422)
            output = await project_production.save_destination(db, project.id, destination)
        if completing and output is not None:
            await project_production.book_confirmed_output(db, output, actor_id=user.id if user else None)
    except WarehouseError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    return production_destination(output)
