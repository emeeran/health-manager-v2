"""Phase 9 people breadth: providers directory, assignments, insurance,
member ICE fields, records.provider_id.

Existence-guarded per upstream migration discipline (SQLite boots run
`upgrade head` on every start; guards make reruns safe).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-02

"""

from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "providers"):
        op.create_table(
            "providers",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "household_id",
                sa.Uuid(),
                sa.ForeignKey("households.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("specialty", sa.String(120), nullable=True),
            sa.Column("hospital", sa.String(200), nullable=True),
            sa.Column("phone", sa.Text(), nullable=True),
            sa.Column("notes", sa.String(1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "provider_assignments"):
        op.create_table(
            "provider_assignments",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "provider_id",
                sa.Uuid(),
                sa.ForeignKey("providers.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("uhid", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("member_id", "provider_id", name="uq_member_provider"),
        )

    if not _has_table(bind, "insurance_policies"):
        op.create_table(
            "insurance_policies",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Uuid(),
                sa.ForeignKey("family_members.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("insurer", sa.String(200), nullable=False),
            sa.Column("plan_name", sa.String(200), nullable=True),
            sa.Column("policy_number", sa.Text(), nullable=False),
            sa.Column("sum_insured", sa.Numeric(12, 2), nullable=True),
            sa.Column("valid_till", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "insurance_claims"):
        op.create_table(
            "insurance_claims",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "policy_id",
                sa.Uuid(),
                sa.ForeignKey("insurance_policies.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, index=True),
            sa.Column("claimed_on", sa.Date(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    member_columns = [
        ("phone", sa.Text()),
        ("address", sa.Text()),
        ("medical_history", sa.Text()),
        ("blood_group", sa.String(8)),
        ("emergency_contact_name", sa.Text()),
        ("emergency_contact_phone", sa.Text()),
    ]
    for column, type_ in member_columns:
        if not _has_column(bind, "family_members", column):
            op.add_column("family_members", sa.Column(column, type_, nullable=True))

    if not _has_column(bind, "health_records", "provider_id"):
        # No inline FK: SQLite can't ALTER-add constraints (alembic raises),
        # and the app runs with foreign_keys OFF anyway. The ORM model keeps
        # the relationship; fresh databases get the FK via create_all.
        op.add_column(
            "health_records",
            sa.Column("provider_id", sa.Uuid(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "health_records", "provider_id"):
        op.drop_column("health_records", "provider_id")
    for column in (
        "emergency_contact_phone",
        "emergency_contact_name",
        "blood_group",
        "medical_history",
        "address",
        "phone",
    ):
        if _has_column(bind, "family_members", column):
            op.drop_column("family_members", column)
    for table in ("insurance_claims", "insurance_policies", "provider_assignments", "providers"):
        if _has_table(bind, table):
            op.drop_table(table)
