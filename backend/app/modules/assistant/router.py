from fastapi import APIRouter, Depends

from app.core.deps import PrincipalDep, SessionDep, SettingsDep, rate_limit
from app.modules.assistant import service
from app.modules.assistant.schemas import ChatIn, ChatOut

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=ChatOut,
             dependencies=[Depends(rate_limit("assistant", "rl_assistant_per_minute", 60))])
async def chat(body: ChatIn, principal: PrincipalDep, session: SessionDep,
               settings: SettingsDep) -> ChatOut:
    """Describe a lost item in natural language; get structured fields + ranked matches."""
    return await service.chat(session, settings, principal, body)
