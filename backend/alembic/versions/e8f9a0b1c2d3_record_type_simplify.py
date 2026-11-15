"""Simplify record types to four buckets.

visit/prescription/discharge/imaging fold into `doctor_visit`, lab
reports become `lab_test`, vaccinations fold into `other`; `eye_checkup`
is new. Rows whose value is remapped lose their content_hash — the hash
salts with record_type, and clinical_data is encrypted app-side so it
cannot be re-hashed in SQL. Dedup re-hashes on the next apply/update.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-11-15

"""

from alembic import op
import sqlalchemy as sa

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

_REMAP = (
    ("('prescription', 'discharge_summary', 'imaging')", "doctor_visit"),
    ("('lab_report',)", "lab_test"),
    ("('vaccination',)", "other"),
)


def _remapped(bind) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM health_records WHERE record_type IN "
            "('prescription', 'discharge_summary', 'imaging', 'lab_report', 'vaccination') LIMIT 1"
        )
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if not _remapped(bind):
        return
    for sources, target in _REMAP:
        bind.execute(
            sa.text(
                f"UPDATE health_records SET record_type = '{target}', content_hash = NULL "
                f"WHERE record_type IN {sources}"
            )
        )


def downgrade() -> None:
    # Irreversible by design: the original distinction is not recoverable.
    pass
