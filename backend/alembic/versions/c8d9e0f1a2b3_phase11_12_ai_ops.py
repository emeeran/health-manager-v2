"""Phase 11+12: AI tools suite + ops jobs — health_alerts,
preventive_dismissals, local_drugs tables (+ bundled Jan Aushadhi seed CSV).

Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-11-02

"""

from alembic import op
import sqlalchemy as sa

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "health_alerts"):
        op.create_table(
            "health_alerts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "record_id",
                sa.Uuid(),
                sa.ForeignKey("health_records.id"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "alert_type",
                sa.String(32),
                nullable=False,
                server_default="lab_anomaly",
            ),
            sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column(
                "acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )

    if not _has_table(bind, "preventive_dismissals"):
        op.create_table(
            "preventive_dismissals",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("rec_key", sa.String(200), nullable=False),
            sa.Column(
                "dismissed_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.Column("note", sa.Text(), nullable=True),
            sa.UniqueConstraint("member_id", "rec_key", name="uq_preventive_member_key"),
        )

    if not _has_table(bind, "local_drugs"):
        # NOTE: constraints/indexes are declared inline — SQLite has no
        # ALTER TABLE ADD CONSTRAINT (alembic raises NotImplementedError),
        # and this block runs exactly on incremental upgrades where the
        # table is genuinely missing.
        op.create_table(
            "local_drugs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("product_id", sa.String(64), nullable=False),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("name_normalized", sa.String(300), nullable=False),
            sa.Column("manufacturer", sa.String(200), nullable=True),
            sa.Column("composition", sa.String(500), nullable=True),
            sa.Column("ingredients", sa.Text(), nullable=True),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("product_form", sa.String(60), nullable=True),
            sa.Column("package", sa.String(120), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("product_id", name="uq_local_drugs_product_id"),
        )
        op.create_index("ix_local_drugs_product_id", "local_drugs", ["product_id"])
        op.create_index("ix_local_drugs_name_norm", "local_drugs", ["name_normalized"])

    # No destructive downgrade: shipped migrations are never edited and the
    # additive tables are harmless if left behind.


def downgrade() -> None:
    pass
