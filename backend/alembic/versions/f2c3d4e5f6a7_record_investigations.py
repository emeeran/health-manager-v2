"""Record investigations field.

Investigative studies (X-ray, CBC, …) captured on the new-record form as
their own field, separate from diagnosis/summary. Nullable — existing
rows simply have no investigations recorded.
Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: f2c3d4e5f6a7
Revises: f1b2c3d4e5f6
Create Date: 2026-11-04

"""

from alembic import op
import sqlalchemy as sa

revision = "f2c3d4e5f6a7"
down_revision = "f1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "health_records", "investigations"):
        op.add_column(
            "health_records",
            sa.Column("investigations", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "health_records", "investigations"):
        op.drop_column("health_records", "investigations")
