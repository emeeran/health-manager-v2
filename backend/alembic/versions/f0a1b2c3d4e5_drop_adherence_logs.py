"""Drop adherence_logs — pill tracking removed.

The pillbox is display-only now (today's schedule comes from
dosing.expand_day at read time), so dose logs, the missed-dose sweep,
and adherence scoring are gone with the table.

Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-11-04

"""

from alembic import op
import sqlalchemy as sa

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "adherence_logs"):
        op.drop_table("adherence_logs")


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "adherence_logs"):
        op.create_table(
            "adherence_logs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
            ),
            sa.Column(
                "medication_id",
                sa.Uuid(),
                sa.ForeignKey("medications.id"),
                nullable=False,
            ),
            sa.Column("medicine_key", sa.String(length=200), nullable=False),
            sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("action_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("slot", sa.String(length=16), nullable=True),
            sa.Column("logged_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("medication_id", "scheduled_time", name="uq_adherence_dose"),
        )
        op.create_index("ix_adherence_logs_member_id", "adherence_logs", ["member_id"])
        op.create_index("ix_adherence_logs_medication_id", "adherence_logs", ["medication_id"])
