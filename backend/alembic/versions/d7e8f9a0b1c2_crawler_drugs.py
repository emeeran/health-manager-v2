"""Crawler drugs table (1mg / Apollo pharmacy catalog).

Factual pharmacy listings synced from the external crawler checkpoint DB.
Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: d7e8f9a0b1c2
Revises: a9b8c7d6e5f4
Create Date: 2026-11-07

"""

from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None

_TABLE = "crawler_drugs"


def _has_table(bind) -> bool:
    return _TABLE in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("url", sa.String(400), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("brand_name", sa.String(300), nullable=False),
        sa.Column("name_normalized", sa.String(300), nullable=False),
        sa.Column("generic_name", sa.String(300), nullable=True),
        sa.Column("manufacturer", sa.String(200), nullable=True),
        sa.Column("pack_size", sa.String(120), nullable=True),
        sa.Column("dosage_form", sa.String(60), nullable=True),
        sa.Column("price_mrp", sa.Float(), nullable=True),
        sa.Column("price_selling", sa.Float(), nullable=True),
        sa.Column("uses", sa.Text(), nullable=True),
        sa.Column("side_effects", sa.Text(), nullable=True),
        sa.Column("therapeutic_class", sa.String(100), nullable=True),
        sa.Column("prescription_required", sa.String(10), nullable=True),
        sa.Column("category_path", sa.String(400), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_crawler_drugs_url", _TABLE, ["url"], unique=True)
    op.create_index("ix_crawler_drugs_source", _TABLE, ["source"])
    op.create_index("ix_crawler_drugs_name_norm", _TABLE, ["name_normalized"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind):
        op.drop_table(_TABLE)
