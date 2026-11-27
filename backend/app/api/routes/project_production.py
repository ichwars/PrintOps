from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import is_auth_enabled
from backend.app.core.permissions import Permission
from backend.app.models.project import Project
from backend.app.models.project_production import ProjectProductionOutput
from backend.app.models.user import User
from backend.app.schemas.project import ProjectProductionDestination
from backend.app.services import project_production
from backend.app.services.warehouse_articles import WarehouseError


async def update_production_output(
    db: AsyncSession,
    project: Project,
    user: User | None,
    destination: ProjectProductionDestination | None,
    *,
    completing: bool = False,
) -> ProjectProductionOutput | None:
    output = await db.get(ProjectProductionOutput, project.id)
    if destination is None and not (completing and output is not None):
        return output
    if user is None:
        permitted = not await is_auth_enabled(db)
    else:
        permitted = user.has_permission(Permission.INVENTORY_UPDATE.value)
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
    return output
