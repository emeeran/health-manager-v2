"""Member current-medications field.

Free-text list of medicines the member is currently on, refreshed from
the prescription prompt / merge endpoint. Existence-guarded per upstream
migration discipline (SQLite boots run `upgrade head` on every start;
guards make reruns safe).

Revision ID: d8e9f0a1b2c3
Revises: c8d9e0f1a2b3
Create Date: 2026-11-03

"""

from alembic import op
import sqlalchemy as sa

revision = "d8e9f0a1b2c3"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "family_members", "current_medications"):
        op.add_column(
            "family_members",
            sa.Column("current_medications", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "family_members", "current_medications"):
        op.drop_column("family_members", "current_medications")
