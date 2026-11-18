from fastapi import APIRouter, Depends, Response, status

from app.core.deps import PrincipalDep, SessionDep, SettingsDep, rate_limit
from app.modules.auth import service
from app.modules.auth.schemas import RequestCodeIn, UpdateProfileIn, UserOut, VerifyCodeIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-code", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(rate_limit("login", "rl_login_per_hour", 3600))])
async def request_code(body: RequestCodeIn, session: SessionDep, settings: SettingsDep) -> None:
    await service.request_code(session, settings, body.email)


@router.post("/verify", response_model=UserOut,
             dependencies=[Depends(rate_limit("login-verify", "rl_login_per_hour", 3600))])
async def verify(body: VerifyCodeIn, response: Response, session: SessionDep,
                 settings: SettingsDep) -> UserOut:
    user, token, exp = await service.verify_code(session, settings, body.email, body.code)
    response.set_cookie(
        settings.cookie_name, token, expires=exp, httponly=True, secure=settings.cookie_secure,
        samesite="lax", path="/",
    )
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: SettingsDep) -> None:
    response.delete_cookie(settings.cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def me(principal: PrincipalDep, session: SessionDep) -> UserOut:
    return UserOut.model_validate(await service.get_user(session, principal.user_id))


@router.patch("/me", response_model=UserOut)
async def update_me(body: UpdateProfileIn, principal: PrincipalDep,
                    session: SessionDep) -> UserOut:
    user = await service.get_user(session, principal.user_id)
    user.display_name = body.display_name
    await session.commit()
    return UserOut.model_validate(user)
