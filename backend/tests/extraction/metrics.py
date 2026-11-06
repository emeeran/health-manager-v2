"""Field-level extraction scoring: precision / recall / F1.

Scalars and list entries are compared on normalized leaf values keyed by
path (e.g. labs.[name=hemoglobin].result). List entries are matched by
their `name` field when present, else by position.
"""


def _norm(value) -> str:
    return str(value).strip().lower()


def _flatten(expected: dict, actual: dict) -> tuple[set, set]:
    """Return (predicted_key:set, gold_key:set) of normalized leaf values."""
    predicted: set[tuple] = set()
    gold: set[tuple] = set()

    def add_leaf(target: set, path: tuple, value) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                add_leaf(target, (*path, k), v)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict) and "name" in item:
                    key = _norm(item["name"])
                    add_leaf(
                        target,
                        (*path, f"[name={key}]"),
                        {k: v for k, v in item.items() if k != "name"},
                    )
                else:
                    add_leaf(target, (*path, f"[{i}]"), item)
        else:
            target.add((*path, _norm(value)))

    add_leaf(predicted, (), actual)
    add_leaf(gold, (), expected)
    return predicted, gold


def score(expected: dict, actual: dict) -> dict:
    # Only score keys the golden doc asks for — summary/facility prose is
    # free-form and can never match a gold string, so counting it would
    # depress precision for reasons unrelated to extraction quality.
    scoped = {k: v for k, v in actual.items() if k in expected}
    predicted, gold = _flatten(expected, scoped)
    true_positives = len(predicted & gold)
    precision = true_positives / len(predicted) if predicted else 0.0
    recall = true_positives / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": true_positives,
        "predicted": len(predicted),
        "gold": len(gold),
    }
