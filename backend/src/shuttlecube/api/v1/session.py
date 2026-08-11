from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.application.commands.session import login, logout
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.identity.models import SystemUser, UserSession
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Session"])


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class SessionView(BaseModel):
    user_id: str
    username: str
    display_name: str
    csrf_token: str


@router.get("/session", response_model=SessionView)
def get_session(
    pair: Annotated[tuple[SystemUser, UserSession], Depends(current_session)],
) -> SessionView:
    user, session = pair
    return SessionView(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        csrf_token=session.csrf_token,
    )


@router.post("/session/login", response_model=SessionView)
def post_login(
    payload: LoginInput,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionView:
    user, tokens = login(db, settings, payload.username, payload.password)
    response.set_cookie(
        settings.session_cookie,
        tokens.session,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return SessionView(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        csrf_token=tokens.csrf,
    )


@router.post("/session/logout", status_code=204)
def post_logout(
    response: Response,
    pair: Annotated[tuple[SystemUser, UserSession], Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SystemUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    _, stored = pair
    logout(db, stored)
    response.delete_cookie(settings.session_cookie, path="/")
