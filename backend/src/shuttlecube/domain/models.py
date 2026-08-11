"""Import all current-release ORM models so metadata and Alembic see every table."""
# ruff: noqa: F401

from shuttlecube.application.idempotency import IdempotencyRecord
from shuttlecube.domain import operations as _operations_models
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import (
    AttendanceRecord,
    Enrollment,
    LessonUnitLedger,
    MakeupRecord,
)
from shuttlecube.domain.customers.models import Guardian, Student, StudentGuardian, WalkInCustomer
from shuttlecube.domain.events.models import EventParticipant, TemporaryEvent
from shuttlecube.domain.finance.models import Attachment, Expense, Payment, Receivable, Refund
from shuttlecube.domain.identity.coach import CoachProfile, CoachRate
from shuttlecube.domain.identity.models import SystemUser, UserSession
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.private_lessons.models import PrivateLesson, PrivateLessonPackage
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import CourtBlock, ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking, VenuePriceRule

__all__ = [name for name in globals() if not name.startswith("_")]
