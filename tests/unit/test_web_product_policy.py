"""Guard the browser product evidence against test-only mutation shortcuts."""

from __future__ import annotations

from pathlib import Path


def test_product_e2e_never_injects_storage_or_constructs_a_completed_save() -> None:
    source = (Path(__file__).resolve().parents[1] / "e2e" / "test_web_product.py").read_text(encoding="utf-8")

    assert "localStorage." + "setItem" not in source
    assert "_one_" + "clear_save" not in source
