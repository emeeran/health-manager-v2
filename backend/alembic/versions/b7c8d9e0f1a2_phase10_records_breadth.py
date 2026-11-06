"""Phase 10 records breadth: symptom/vaccination/milestone tables, search
mirror, record condition-link + confidentiality + dedup columns, medication
condition link, member sex.

Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: b7c8d9e0f1a2
Revises: a7b8c9d0e1f2
Create Date: 2026-11-02

"""

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, name: str) -> bool:
    return name in {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # --- symptom_entries ----------------------------------------------------
    if not _has_table(bind, "symptom_entries"):
        op.create_table(
            "symptom_entries",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("symptom", sa.String(120), nullable=False),
            sa.Column("severity", sa.String(16), nullable=False),
            sa.Column("started_at", sa.Date(), nullable=False),
            sa.Column("resolved_at", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        if not _has_index(bind, "symptom_entries", "ix_symptoms_member_symptom"):
            op.create_index(
                "ix_symptoms_member_symptom",
                "symptom_entries",
                ["member_id", "symptom"],
            )
        if not _has_index(bind, "symptom_entries", "ix_symptoms_member_started"):
            op.create_index(
                "ix_symptoms_member_started",
                "symptom_entries",
                ["member_id", "started_at"],
            )

    # --- vaccinations ---------------------------------------------------------
    if not _has_table(bind, "vaccinations"):
        op.create_table(
            "vaccinations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("date_administered", sa.Date(), nullable=False),
            sa.Column("booster_due_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )

    # --- milestone_achievements ----------------------------------------------
    if not _has_table(bind, "milestone_achievements"):
        op.create_table(
            "milestone_achievements",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("milestone_key", sa.String(64), nullable=False),
            sa.Column("achieved_on", sa.Date(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("member_id", "milestone_key", name="uq_milestone_member_key"),
        )

    # --- search_mirror ---------------------------------------------------------
    if not _has_table(bind, "search_mirror"):
        op.create_table(
            "search_mirror",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("row_type", sa.String(32), nullable=False, index=True),
            sa.Column("row_id", sa.Uuid(), nullable=False, index=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "household_id",
                sa.Uuid(),
                sa.ForeignKey("households.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
    # The FTS5 virtual table is created lazily by the search service
    # (SQLAlchemy cannot express virtual tables); nothing to do here.

    # --- new columns on existing tables ---------------------------------------
    if not _has_column(bind, "health_records", "condition_id"):
        op.add_column(
            "health_records",
            sa.Column("condition_id", sa.Uuid(), nullable=True),
        )
    if not _has_column(bind, "health_records", "confidentiality_level"):
        op.add_column(
            "health_records",
            sa.Column(
                "confidentiality_level",
                sa.String(16),
                nullable=False,
                server_default="household",
            ),
        )
        op.create_index(
            "ix_health_records_confidentiality_level",
            "health_records",
            ["confidentiality_level"],
        )
    if not _has_column(bind, "health_records", "content_hash"):
        op.add_column(
            "health_records",
            sa.Column("content_hash", sa.String(64), nullable=True),
        )
        op.create_index("ix_health_records_content_hash", "health_records", ["content_hash"])
    if not _has_column(bind, "health_records", "merged_into_id"):
        op.add_column(
            "health_records",
            sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        )
    if not _has_column(bind, "medications", "condition_id"):
        op.add_column("medications", sa.Column("condition_id", sa.Uuid(), nullable=True))
    if not _has_column(bind, "family_members", "sex"):
        op.add_column("family_members", sa.Column("sex", sa.String(10), nullable=True))

    # Growth reference CSVs ship as package data under app/data/growth and are
    # validated by the growth service's fail-fast import; nothing to migrate.


def downgrade() -> None:
    # No destructive downgrade: shipped migrations are never edited and the
    # additive columns/tables are harmless if left behind.
    pass
