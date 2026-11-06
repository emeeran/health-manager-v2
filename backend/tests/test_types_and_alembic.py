"""EncryptedText round-trips and alembic baseline discipline."""

import os
import tempfile
from datetime import date

from sqlalchemy import select, text

from app.models import FamilyMember, HealthRecord, Household


async def test_encrypted_text_roundtrip(auth_client, session_factory):
    async with session_factory() as db:
        household = (await db.execute(select(Household))).scalars().first()
        member = FamilyMember(household_id=household.id, name="EncTest")
        db.add(member)
        await db.flush()  # assign member.id
        record = HealthRecord(
            member_id=member.id,
            record_type="doctor_visit",
            record_date=date(2026, 1, 15),
            diagnosis="type 2 diabetes mellitus",
            clinical_data='{"finding": "confidential-xyz"}',
        )
        db.add(record)
        await db.commit()
        record_id = record.id

    # Raw storage must be ciphertext — plaintext never on disk in the column.
    async with session_factory() as db:
        raws = (await db.execute(text("SELECT diagnosis FROM health_records"))).scalars().all()
        assert raws and all("diabetes" not in r and r.startswith("gAAAA") for r in raws)

    # ORM reads decrypt transparently.
    async with session_factory() as db:
        loaded = await db.get(HealthRecord, record_id)
        assert loaded.diagnosis == "type 2 diabetes mellitus"
        assert loaded.clinical_data == '{"finding": "confidential-xyz"}'


async def test_encrypted_text_none_and_empty_pass_through(session_factory):
    from app.models.types import EncryptedText

    col = EncryptedText()
    assert col.process_bind_param(None, None) is None
    assert col.process_bind_param("", None) == ""
    assert col.process_result_value(None, None) is None
    assert col.process_result_value("", None) == ""


async def test_alembic_upgrade_head_is_idempotent():
    """Boot discipline: upgrade head twice on a fresh DB must not raise."""
    from alembic import command
    from alembic.config import Config

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "alembic_test.db")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = Config(os.path.join(root, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(root, "alembic"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # second run must be a no-op

        # All expected tables exist after the baseline.
        import sqlite3

        conn = sqlite3.connect(db_path)
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        expected = {
            "users",
            "households",
            "family_members",
            "refresh_tokens",
            "health_records",
            "attachments",
            "medications",
            "lab_results",
            "vital_measurements",
            "allergies",
            "condition_episodes",
        }
        assert expected <= tables
