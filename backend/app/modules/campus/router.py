from fastapi import APIRouter

from app.core.deps import PrincipalDep, SessionDep
from app.modules.campus import service
from app.modules.campus.schemas import CampusOut

router = APIRouter(prefix="/campus", tags=["campus"])


@router.get("", response_model=CampusOut)
async def my_campus(principal: PrincipalDep, session: SessionDep) -> CampusOut:
    return await service.campus_overview(session, principal.campus_id)
