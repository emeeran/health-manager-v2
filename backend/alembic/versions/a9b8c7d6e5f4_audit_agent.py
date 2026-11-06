"""Audit agent: verification detail + member web fact-check consent.

``verifications.audit_json`` stores the claim-level audit (encrypted at
rest, like notes). ``family_members.web_factcheck_consent`` is the explicit
per-member opt-in for external fact-checking; default false so no query can
leave the box without a recorded decision.

Existence-guarded per the project's migration discipline (SQLite boots run
``upgrade head`` on every start).

Revision ID: a9b8c7d6e5f4
Revises: f2c3d4e5f6a7
Create Date: 2026-11-06

"""

import sqlalchemy as sa
from alembic import op

revision = "a9b8c7d6e5f4"
down_revision = "f2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "verifications", "audit_json"):
        op.add_column("verifications", sa.Column("audit_json", sa.Text(), nullable=True))
    if not _has_column(bind, "family_members", "web_factcheck_consent"):
        op.add_column(
            "family_members",
            sa.Column(
                "web_factcheck_consent",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "verifications", "audit_json"):
        op.drop_column("verifications", "audit_json")
    if _has_column(bind, "family_members", "web_factcheck_consent"):
        op.drop_column("family_members", "web_factcheck_consent")
