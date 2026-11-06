"""Phase 4 AI: member cloud-AI consent + verifications table.

Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-11-01

"""

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return inspector.has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "family_members", "cloud_ai_consent"):
        op.add_column(
            "family_members",
            sa.Column("cloud_ai_consent", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    if not _has_table(bind, "verifications"):
        op.create_table(
            "verifications",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("family_members.id"), nullable=False),
            sa.Column("subject_type", sa.String(32), nullable=False, index=True),
            sa.Column("subject_id", sa.Uuid(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, index=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("verifier_name", sa.String(64), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "verifications"):
        op.drop_table("verifications")
    if _has_column(bind, "family_members", "cloud_ai_consent"):
        op.drop_column("family_members", "cloud_ai_consent")
