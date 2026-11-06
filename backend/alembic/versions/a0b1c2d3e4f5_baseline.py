"""Baseline: squashed create_all of all Phase 1+2 tables.

This baseline must never be edited — fresh databases run it via
`alembic upgrade head` on every boot (discipline carried over from
upstream: migrations stay existence-guarded/idempotent).
"""

from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=op.get_bind())
