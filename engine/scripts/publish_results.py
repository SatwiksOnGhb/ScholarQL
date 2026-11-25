"""Assemble the study outputs displayed in the Evaluation page."""

import json

from scholarql.config import ROOT


def main():
    results = ROOT / "results"
    names = {
        "sql": "sql_results.json",
        "retrieval": "retrieval_results.json",
        "indexes": "index_results.json",
    }
    payload = {
        key: json.loads((results / path).read_text(encoding="utf-8"))
        for key, path in names.items()
        if (results / path).is_file()
    }
    (results / "evaluation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
