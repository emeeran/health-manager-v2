"""Deferred parity: push subscriptions + insights (reports).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-02

"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "push_subscriptions"):
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("endpoint", sa.String(500), unique=True),
            sa.Column("p256dh", sa.String(200), nullable=False),
            sa.Column("auth", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_pushed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _has_table(bind, "insights"):
        op.create_table(
            "insights",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("kind", sa.String(32), nullable=False, index=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("sources_json", sa.Text(), nullable=True),
            sa.Column("verification_id", sa.Uuid(), nullable=True),
            sa.Column("provider_used", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("insights", "push_subscriptions"):
        if _has_table(bind, table):
            op.drop_table(table)
