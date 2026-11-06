"""Phase 7: TOTP columns, share links, conversations, messages.

Existence-guarded per migration discipline.

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-11-02

"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    user_cols = _columns(bind, "users")
    if "totp_secret" not in user_cols:
        op.add_column("users", sa.Column("totp_secret", sa.Text(), nullable=True))
    if "totp_enabled" not in user_cols:
        op.add_column(
            "users",
            sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "backup_codes" not in user_cols:
        op.add_column("users", sa.Column("backup_codes", sa.Text(), nullable=True))

    if not _has_table(bind, "share_links"):
        op.create_table(
            "share_links",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("token_hash", sa.String(64), unique=True, index=True),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "conversations"):
        op.create_table(
            "conversations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "household_id",
                sa.Uuid(),
                sa.ForeignKey("households.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("family_members.id"), nullable=True),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "messages"):
        op.create_table(
            "messages",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.Uuid(),
                sa.ForeignKey("conversations.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("verification_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("messages", "conversations", "share_links"):
        if _has_table(bind, table):
            op.drop_table(table)
    cols = _columns(bind, "users")
    for col in ("backup_codes", "totp_enabled", "totp_secret"):
        if col in cols:
            op.drop_column("users", col)
