from fastapi import APIRouter

from shuttlecube.api.v1 import (
    attachments,
    audit,
    classes,
    dashboard,
    data_transfer,
    directory,
    events,
    finance,
    operations,
    operations_settings,
    payroll,
    private_lessons,
    reports,
    schedule,
    session,
    setup,
    student_entitlements,
    venue_bookings,
)

router = APIRouter(prefix="/api/v1")
router.include_router(setup.router)
router.include_router(session.router)
router.include_router(directory.router)
router.include_router(student_entitlements.router)
router.include_router(schedule.router)
router.include_router(classes.router)
router.include_router(private_lessons.router)
router.include_router(venue_bookings.router)
router.include_router(events.router)
router.include_router(finance.router)
router.include_router(attachments.router)
router.include_router(payroll.router)
router.include_router(dashboard.router)
router.include_router(reports.router)
router.include_router(audit.router)
router.include_router(data_transfer.router)
router.include_router(operations.router)
router.include_router(operations_settings.router)
