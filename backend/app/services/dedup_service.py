"""Record dedup/merge (Phase 10, ported from v1's dedup_service).

Two halves:

**Detection** — scan a member's non-deleted records and return candidate
duplicate pairs ``[{primary_id, duplicate_id, reason, score}]``. Signals,
in descending confidence:

* ``identical_content``  — the record's ``content_hash`` (SHA-256 over the
  canonical clinical payload) matches another record's.
* ``same_attachment``    — both records reference an attachment with the
  same plaintext content hash (the store dedups files by that hash).
* ``same_type_adjacent_date`` — same record type within ±3 days.
* ``similar_content``    — Jaccard similarity ≥ 0.5 over the medicine /
  lab-test names embedded in structured ``clinical_data``.

Exotic scoring from v1 (provider/diagnosis pairs, union-find grouping) is
dropped — pairs are enough for the merge surface.

**Merge** — fold the duplicate into the primary: attachments are moved,
missing fields are filled, structured clinical JSON lists are unioned,
and labs/medications/vitals that reference the duplicate are re-pointed.
The duplicate is marked ``merged_into_id`` + soft-deleted. Merging is
IDEMPOTENT: re-merging an already-merged duplicate into the same primary
is a no-op that returns the primary unchanged.
"""

import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Attachment, HealthRecord

logger = logging.getLogger(__name__)

DATE_PROXIMITY_DAYS = 3
CONTENT_SIMILARITY_THRESHOLD = 0.5


def compute_content_hash(record_type, record_date, clinical_data) -> str:
    """Plaintext SHA-256 over the canonical clinical payload.

    ``record_date``/``record_type`` participate so a genuine follow-up
    visit that reuses a template does not hash identical to the original;
    ``clinical_data`` is canonicalized (sorted keys, compact separators)
    so key order never changes the hash.
    """
    payload = {
        "record_type": str(getattr(record_type, "value", record_type)),
        "record_date": str(record_date),
        "clinical_data": clinical_data,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _structured_lists(clinical_data: str | None) -> dict[str, set[tuple]]:
    """Lowercased row-keys of prescriptions / labs inside clinical JSON."""
    out: dict[str, set[tuple]] = {"prescriptions": set(), "labs": set()}
    if not clinical_data:
        return out
    try:
        parsed = json.loads(clinical_data)
    except (ValueError, TypeError):
        return out
    if not isinstance(parsed, dict):
        return out
    rx = parsed.get("prescriptions") or []
    if isinstance(rx, list):
        out["prescriptions"] = {
            (str(r.get("medicine") or "").strip().lower(),)
            for r in rx
            if isinstance(r, dict) and r.get("medicine")
        }
    tests = parsed.get("lab_results") or parsed.get("tests") or []
    if isinstance(tests, list):
        out["labs"] = {
            (str(t.get("test_name") or "").strip().lower(),)
            for t in tests
            if isinstance(t, dict) and t.get("test_name")
        }
    return out


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _union_clinical_data(keeper_raw: str | None, loser_raw: str | None) -> str | None:
    """Union prescriptions/lab rows from the loser into the keeper's JSON.

    Rows dedupe on (medicine, dosage, timing, duration) / (test, result);
    returns None (keeper untouched) when either side isn't structured JSON.
    """
    try:
        keeper = json.loads(keeper_raw) if keeper_raw else None
        loser = json.loads(loser_raw) if loser_raw else None
    except (ValueError, TypeError):
        return None
    if not isinstance(keeper, dict) or not isinstance(loser, dict):
        return None

    def rx_key(rx: dict) -> tuple:
        return tuple(
            str(rx.get(k) or "").lower() for k in ("medicine", "dosage", "timing", "duration")
        )

    def lab_key(t: dict) -> tuple:
        return tuple(str(t.get(k) or "").lower() for k in ("test_name", "result"))

    changed = False
    for list_key, key_fn in (
        ("prescriptions", rx_key),
        ("lab_results", lab_key),
        ("tests", lab_key),
    ):
        loser_items = loser.get(list_key)
        if not isinstance(loser_items, list) or not loser_items:
            continue
        keeper_items = keeper.get(list_key)
        if not isinstance(keeper_items, list):
            keeper_items = []
        seen = {key_fn(i) for i in keeper_items if isinstance(i, dict)}
        for item in loser_items:
            if not isinstance(item, dict):
                continue
            k = key_fn(item)
            if k in seen:
                continue
            seen.add(k)
            keeper_items.append(item)
            changed = True
        keeper[list_key] = keeper_items
    return json.dumps(keeper) if changed else None


class DedupService:
    """Pair-level duplicate detection + idempotent merge for one member."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def load_active_records(self, member_id: UUID) -> list[HealthRecord]:
        rows = await self.db.scalars(
            select(HealthRecord)
            .options(selectinload(HealthRecord.attachments))
            .where(
                HealthRecord.member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        )
        return list(rows)

    async def find_duplicate_pairs(self, member_id: UUID) -> dict:
        """Candidate pairs [{primary_id, duplicate_id, reason, score}]."""
        records = await self.load_active_records(member_id)
        by_hash: dict[str, list[HealthRecord]] = {}
        att_hash_to_records: dict[str, set[UUID]] = {}
        for rec in records:
            if rec.content_hash:
                by_hash.setdefault(rec.content_hash, []).append(rec)
            for att in rec.attachments:
                att_hash_to_records.setdefault(att.content_hash, set()).add(rec.id)

        structured = {r.id: _structured_lists(r.clinical_data) for r in records}

        pairs: dict[tuple[UUID, UUID], dict] = {}

        def _add(a: HealthRecord, b: HealthRecord, reason: str, score: int) -> None:
            key = (a.id, b.id) if str(a.id) < str(b.id) else (b.id, a.id)
            entry = pairs.setdefault(key, {"reasons": [], "score": 0})
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)
            entry["score"] = max(entry["score"], score)

        # 1. identical record content hash
        for group in by_hash.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    _add(group[i], group[j], "identical_content", 3)

        # 2. shared attachment content hash (same uploaded file)
        ids = {r.id: r for r in records}
        for rec_ids in att_hash_to_records.values():
            recs = [ids[rid] for rid in rec_ids if rid in ids]
            for i in range(len(recs)):
                for j in range(i + 1, len(recs)):
                    _add(recs[i], recs[j], "same_attachment", 2)

        # 3/4. heuristics over every pair (family scale: tens, not millions)
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                a, b = records[i], records[j]
                if a.record_type == b.record_type:
                    day_diff = abs((a.record_date - b.record_date).days)
                    if day_diff <= DATE_PROXIMITY_DAYS:
                        _add(a, b, "same_type_adjacent_date", 1)
                if (
                    _jaccard(
                        structured[a.id]["prescriptions"],
                        structured[b.id]["prescriptions"],
                    )
                    >= CONTENT_SIMILARITY_THRESHOLD
                    or _jaccard(structured[a.id]["labs"], structured[b.id]["labs"])
                    >= CONTENT_SIMILARITY_THRESHOLD
                ):
                    _add(a, b, "similar_content", 1)

        results = []
        for (id_a, id_b), entry in pairs.items():
            a, b = ids[id_a], ids[id_b]
            primary, duplicate = _pick_primary(a, b)
            results.append(
                {
                    "primary_id": str(primary.id),
                    "duplicate_id": str(duplicate.id),
                    "reason": ",".join(sorted(entry["reasons"])),
                    "score": entry["score"],
                }
            )
        results.sort(key=lambda p: (-p["score"], p["reason"]))
        return {"pairs": results, "total_records_scanned": len(records)}

    async def merge_duplicate(
        self, member_id: UUID, duplicate_id: UUID, primary_id: UUID
    ) -> HealthRecord:
        """Fold ``duplicate_id`` into ``primary_id``. Idempotent.

        Raises ``ValueError`` when either record is missing/not in scope, or
        when the duplicate was already merged into a *different* record.
        """
        if duplicate_id == primary_id:
            raise ValueError("A record cannot be merged into itself")

        primary = await self.db.get(HealthRecord, primary_id)
        duplicate = await self.db.get(HealthRecord, duplicate_id)
        if (
            primary is None
            or duplicate is None
            or primary.member_id != member_id
            or duplicate.member_id != member_id
        ):
            raise ValueError("Record not found")
        if primary.is_deleted:
            raise ValueError("Primary record is already merged away")

        # Idempotency: merging an already-merged duplicate into the same
        # primary is a no-op (the merge's side effects are all idempotent
        # by construction — attachments move by id, fields fill-if-empty,
        # clinical lists dedupe on row keys).
        if duplicate.merged_into_id is not None or duplicate.is_deleted:
            if duplicate.merged_into_id == primary_id:
                return primary
            raise ValueError("Record was already merged into another record")

        # Attachments move to the primary (rows keep their ids; the store
        # is content-addressable so shared file_paths are already safe).
        atts = await self.db.scalars(select(Attachment).where(Attachment.record_id == duplicate_id))
        for att in atts:
            att.record_id = primary_id

        # Fill-in missing fields from the duplicate.
        for field in (
            "diagnosis",
            "prescription_text",
            "summary",
            "doctor_name",
            "provider_id",
        ):
            if getattr(primary, field) is None and getattr(duplicate, field) is not None:
                setattr(primary, field, getattr(duplicate, field))
        if duplicate.tags:
            existing = {t for t in (primary.tags or "").split(",") if t}
            extra = {t for t in duplicate.tags.split(",") if t}
            merged = existing | extra
            if merged:
                primary.tags = ",".join(sorted(merged))

        merged_cd = _union_clinical_data(primary.clinical_data, duplicate.clinical_data)
        if merged_cd is not None:
            primary.clinical_data = merged_cd
            primary.content_hash = compute_content_hash(
                primary.record_type, primary.record_date, json.loads(merged_cd)
            )

        # Re-point child references (labs / medications / vitals).
        from app.models import LabResult, Medication, VitalMeasurement

        for model in (LabResult, Medication, VitalMeasurement):
            await self.db.execute(
                update(model).where(model.record_id == duplicate_id).values(record_id=primary_id)
            )

        duplicate.merged_into_id = primary_id
        duplicate.is_deleted = True
        await self.db.flush()
        await self.db.refresh(primary)
        return primary


def _pick_primary(a: HealthRecord, b: HealthRecord) -> tuple[HealthRecord, HealthRecord]:
    """Keeper heuristic: more attachments, then richer payload, then older."""
    key = lambda r: (  # noqa: E731
        len(r.attachments),
        len(r.clinical_data or ""),
        -r.created_at.timestamp() if r.created_at else 0,
    )
    if key(a) >= key(b):
        return a, b
    return b, a
