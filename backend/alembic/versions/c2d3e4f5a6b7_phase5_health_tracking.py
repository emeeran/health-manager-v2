"""Phase 5: medication scheduling columns + reminders table.

Existence-guarded per migration discipline (SQLite boots rerun upgrade).

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-11-01

"""

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "medications")
    if "schedule_type" not in cols:
        op.add_column(
            "medications",
            sa.Column("schedule_type", sa.String(16), nullable=False, server_default="daily"),
        )
    if "schedule_json" not in cols:
        op.add_column("medications", sa.Column("schedule_json", sa.Text(), nullable=True))

    if not _has_table(bind, "reminders"):
        op.create_table(
            "reminders",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("family_members.id"), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("repeat", sa.String(16), nullable=False, server_default="none"),
            sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "reminders"):
        op.drop_table("reminders")
    cols = _columns(bind, "medications")
    if "schedule_json" in cols:
        op.drop_column("medications", "schedule_json")
    if "schedule_type" in cols:
        op.drop_column("medications", "schedule_type")
