"""Phase 8 household admin: memberships, invitations, audit, secrets,
notifications + per-household AI config.

Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe). Backfills one
admin household_members row per existing household (the primary user).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-02

"""

from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "household_members"):
        op.create_table(
            "household_members",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "household_id",
                sa.Uuid(),
                sa.ForeignKey("households.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("role", sa.String(16), nullable=False, server_default="member"),
            sa.Column("invited_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", name="uq_household_members_user"),
        )

    if not _has_table(bind, "household_invitations"):
        op.create_table(
            "household_invitations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "household_id",
                sa.Uuid(),
                sa.ForeignKey("households.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("role", sa.String(16), nullable=False, server_default="member"),
            sa.Column("invited_by", sa.Uuid(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "security_audit"):
        op.create_table(
            "security_audit",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("household_id", sa.Uuid(), nullable=True, index=True),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("action", sa.String(64), nullable=False, index=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("ip", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "app_secrets"):
        op.create_table(
            "app_secrets",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("value_encrypted", sa.Text(), nullable=False),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "household_id",
                sa.Uuid(),
                sa.ForeignKey("households.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("title_encrypted", sa.String(500), nullable=False),
            sa.Column("body_encrypted", sa.Text(), nullable=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_column(bind, "households", "settings_json"):
        op.add_column("households", sa.Column("settings_json", sa.Text(), nullable=True))

    _backfill_memberships(bind)


def _backfill_memberships(bind) -> None:
    """One admin membership per household that has none for its primary user.

    ORM-based so UUID storage matches the model exactly (SQLite hex).
    """
    from sqlalchemy import orm, select

    import app.models  # noqa: F401

    session = orm.Session(bind=bind)
    try:
        pairs = session.execute(
            select(app.models.Household.id, app.models.Household.primary_user_id)
        ).all()
        existing = set(session.execute(select(app.models.HouseholdMember.user_id)).scalars())
        for household_id, user_id in pairs:
            if user_id in existing:
                continue
            session.add(
                app.models.HouseholdMember(
                    household_id=household_id,
                    user_id=user_id,
                    role=app.models.HouseholdRole.ADMIN.value,
                )
            )
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    for table in (
        "notifications",
        "app_secrets",
        "security_audit",
        "household_invitations",
        "household_members",
    ):
        if _has_table(op.get_bind(), table):
            op.drop_table(table)
    if _has_column(op.get_bind(), "households", "settings_json"):
        op.drop_column("households", "settings_json")
