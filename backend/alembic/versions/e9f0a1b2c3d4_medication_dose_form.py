"""Medication dose_form field.

Presentation form (Tab/Cap/Inj/...) carried over from the v1 medication
table. Nullable — existing rows simply have no form recorded.
Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-11-04

"""

from alembic import op
import sqlalchemy as sa

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "medications", "dose_form"):
        op.add_column(
            "medications",
            sa.Column("dose_form", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "medications", "dose_form"):
        op.drop_column("medications", "dose_form")
