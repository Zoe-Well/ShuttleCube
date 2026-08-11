import argparse
from datetime import UTC, datetime, time
from getpass import getpass

from sqlalchemy import select

from shuttlecube.application.audit.writer import record_audit
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.infrastructure.database.session import SessionLocal
from shuttlecube.infrastructure.security.passwords import hash_password


def bootstrap_admin(username: str, display_name: str, password: str | None) -> None:
    secret = password or getpass("Password: ")
    if len(secret) < 8:
        raise SystemExit("password must contain at least 8 characters")
    with SessionLocal() as db:
        user = db.query(SystemUser).filter_by(username=username).one_or_none()
        if user:
            user.display_name = display_name
            user.password_hash = hash_password(secret)
        else:
            db.add(
                SystemUser(
                    username=username,
                    display_name=display_name,
                    password_hash=hash_password(secret),
                )
            )
        db.commit()


def bootstrap_venue(name: str = "ShuttleCube 羽毛球馆", court_count: int = 4) -> None:
    """Create the single venue and its numbered courts without duplicating existing data."""
    with SessionLocal() as db:
        venue = db.query(Venue).first()
        if venue is None:
            organization = db.query(Organization).first()
            if organization is None:
                raise SystemExit("organization not found; run database migrations first")
            venue = Venue(
                organization_id=organization.id,
                name=name,
                timezone="Asia/Shanghai",
                weekday_open_time=time(14, 0),
                weekday_close_time=time(22, 0),
                weekend_open_time=time(8, 0),
                weekend_close_time=time(22, 0),
            )
            db.add(venue)
            db.flush()
        for number in range(1, court_count + 1):
            code = str(number)
            if db.query(Court).filter_by(code=code).one_or_none() is None:
                db.add(Court(venue_id=venue.id, code=code, name=f"{number} 号场地"))
        db.commit()


def bootstrap_operations_owner(username: str, venue_id: str | None = None) -> None:
    """Activate the first operations owner without exposing a public bootstrap API."""
    with SessionLocal() as db:
        user = db.scalar(select(SystemUser).where(SystemUser.username == username))
        if user is None or not user.is_active:
            raise SystemExit("active user not found")
        statement = (
            select(VenueMembership, OrganizationMembership, Venue)
            .join(
                OrganizationMembership,
                OrganizationMembership.id == VenueMembership.organization_membership_id,
            )
            .join(Venue, Venue.id == VenueMembership.venue_id)
            .where(OrganizationMembership.user_id == user.id)
        )
        if venue_id:
            statement = statement.where(Venue.id == venue_id)
        rows = list(db.execute(statement).all())
        if not rows:
            raise SystemExit("operations membership not found")
        if len(rows) > 1:
            raise SystemExit("multiple venue memberships found; pass --venue-id")
        venue_membership, organization_membership, venue = rows[0]
        active_owner_id = db.scalar(
            select(VenueMembership.id)
            .join(
                OrganizationMembership,
                OrganizationMembership.id == VenueMembership.organization_membership_id,
            )
            .where(
                VenueMembership.venue_id == venue.id,
                VenueMembership.status == "active",
                VenueMembership.role_key == "owner",
                OrganizationMembership.status == "active",
            )
        )
        if active_owner_id and active_owner_id != venue_membership.id:
            raise SystemExit("an active operations owner already exists for this venue")
        before = {
            "organization_membership_status": organization_membership.status,
            "organization_role": organization_membership.organization_role,
            "venue_membership_status": venue_membership.status,
            "venue_role": venue_membership.role_key,
            "active_for_operations": venue.active_for_operations,
        }
        desired = {
            "organization_membership_status": "active",
            "organization_role": "owner",
            "venue_membership_status": "active",
            "venue_role": "owner",
            "active_for_operations": True,
        }
        if before == desired:
            return
        now = datetime.now(UTC)
        organization_membership.status = "active"
        organization_membership.organization_role = "owner"
        organization_membership.reviewed_by = user.id
        organization_membership.reviewed_at = now
        venue_membership.status = "active"
        venue_membership.role_key = "owner"
        venue.active_for_operations = True
        if not active_owner_id:
            venue.model_enabled = False
            venue.write_tools_enabled = False
        record_audit(
            db,
            actor_id=user.id,
            action="operations.owner_bootstrapped",
            entity_type="venue",
            entity_id=venue.id,
            request_id="cli-bootstrap-operations-owner",
            before=before,
            after=desired,
            reason="Initialize the first local operations owner",
            organization_id=venue.organization_id,
            venue_id=venue.id,
        )
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(prog="shuttlecube")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("bootstrap-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name")
    admin.add_argument("--password")
    venue = commands.add_parser("bootstrap-venue")
    venue.add_argument("--name", default="ShuttleCube 羽毛球馆")
    venue.add_argument("--court-count", type=int, default=4)
    operations_owner = commands.add_parser("bootstrap-operations-owner")
    operations_owner.add_argument("--username", required=True)
    operations_owner.add_argument("--venue-id")
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        bootstrap_admin(args.username, args.display_name or args.username, args.password)
    elif args.command == "bootstrap-venue":
        if args.court_count < 1:
            raise SystemExit("court-count must be positive")
        bootstrap_venue(args.name, args.court_count)
    elif args.command == "bootstrap-operations-owner":
        bootstrap_operations_owner(args.username, args.venue_id)
