#!/usr/bin/env python
"""Write `docs/ai-systems.md` from the AI system registry.

EU AI Act Article 11 technical documentation that is maintained by hand is wrong
within one release. This regenerates it from the objects the features actually run
on, so a prompt edit and its documentation land in the same commit.

    python scripts/generate_model_cards.py           # write the doc
    python scripts/generate_model_cards.py --check   # fail if it has drifted

`--check` is what CI runs; `tests/test_ai_systems.py` asserts the same thing so a
drifted doc fails the ordinary suite too.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.aisystems import model_card_markdown  # noqa: E402

DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "ai-systems.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed document differs from the registry",
    )
    args = parser.parse_args()

    generated = model_card_markdown()
    current = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else None

    if args.check:
        if current == generated:
            print(f"{DOC_PATH.name} is up to date.")
            return 0
        print(
            f"{DOC_PATH} is out of date with app/services/aisystems.py.\n"
            "Run: python scripts/generate_model_cards.py",
            file=sys.stderr,
        )
        return 1

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(generated, encoding="utf-8")
    print(f"{'Updated' if current != generated else 'Unchanged'}: {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
