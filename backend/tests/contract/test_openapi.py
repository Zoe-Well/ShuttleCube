from pathlib import Path

import yaml


def test_openapi_references_and_future_scope() -> None:
    path = (
        Path(__file__).parents[3]
        / "specs"
        / "001-badminton-operations"
        / "contracts"
        / "openapi.yaml"
    )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["openapi"] == "3.1.0"
    assert "/schedule" in doc["paths"]
    assert "/agent-runs" in doc["x-future-path-prefixes"]
