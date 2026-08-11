from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.api.v1.session import SessionView
from shuttlecube.application.commands.session import login
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.infrastructure.database.session import get_db
from shuttlecube.infrastructure.security.passwords import hash_password

router = APIRouter(tags=["Setup"])


class SetupStatus(BaseModel):
    required: bool
    desktop_mode: bool


class SetupInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    venue_name: str = Field(min_length=1, max_length=120)
    court_count: int = Field(default=4, ge=1, le=50)
    username: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


@router.get("/setup/status", response_model=SetupStatus)
def setup_status(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SetupStatus:
    return SetupStatus(
        required=settings.desktop_mode and db.query(SystemUser).count() == 0,
        desktop_mode=settings.desktop_mode,
    )


@router.post("/setup", response_model=SessionView, status_code=201)
def perform_setup(
    payload: SetupInput,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionView:
    if not settings.desktop_mode:
        raise BusinessError(409, "desktop_only", "首次启动向导仅在单机桌面版中可用")
    if db.query(SystemUser).count() != 0:
        raise BusinessError(409, "setup_completed", "系统已经完成初始化")
    user = SystemUser(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    venue = Venue(
        name=payload.venue_name,
        timezone=settings.timezone,
        weekday_open_time=time(14),
        weekday_close_time=time(22),
        weekend_open_time=time(8),
        weekend_close_time=time(22),
    )
    db.add_all([user, venue])
    db.flush()
    db.add_all(
        [
            Court(venue_id=venue.id, code=str(number), name=f"{number} 号场地")
            for number in range(1, payload.court_count + 1)
        ]
    )
    db.commit()
    _, tokens = login(db, settings, user.username, payload.password)
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
