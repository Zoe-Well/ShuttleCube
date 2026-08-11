from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationScopeMixin:
    """Temporary nullable ownership used during the staged Scope migration."""

    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True
    )


class VenueScopeMixin(OrganizationScopeMixin):
    venue_id: Mapped[str | None] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"), nullable=True, index=True
    )
