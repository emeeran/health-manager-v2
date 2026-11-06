"""Member family_medical_history field.

Separates family history from the member's own medical history
(onboarding form shows both, in that order). Nullable — existing rows
simply have no family history recorded.
Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-11-04

"""

from alembic import op
import sqlalchemy as sa

revision = "f1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "family_members", "family_medical_history"):
        op.add_column(
            "family_members",
            sa.Column("family_medical_history", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "family_members", "family_medical_history"):
        op.drop_column("family_members", "family_medical_history")
