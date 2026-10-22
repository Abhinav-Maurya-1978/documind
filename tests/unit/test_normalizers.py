import pytest
from documind.extraction.normalizers import ValueNormalizer

def test_monetary_normalization_inr():
    res = ValueNormalizer.normalize_monetary("Rs. 55,000.00")
    assert res["valid"] is True
    assert res["normalized"] == 55000.0
    assert res["currency"] == "INR"

def test_monetary_normalization_usd():
    res = ValueNormalizer.normalize_monetary("$ 1,250.50")
    assert res["valid"] is True
    assert res["normalized"] == 1250.50
    assert res["currency"] == "USD"

def test_date_normalization_unambiguous():
    res = ValueNormalizer.normalize_date("February 1, 2026")
    assert res["valid"] is True
    assert res["normalized"] == "2026-02-01"
    assert res["is_ambiguous"] is False

def test_date_normalization_ambiguous():
    # 01/02/2026 has both parts <= 12
    res = ValueNormalizer.normalize_date("01/02/2026")
    assert res["valid"] is True
    assert res["is_ambiguous"] is True

def test_date_normalization_day_greater_than_12():
    # 25/02/2026 is strictly unambiguous (part 1 must be day)
    res = ValueNormalizer.normalize_date("25/02/2026")
    assert res["valid"] is True
    assert res["is_ambiguous"] is False
    assert res["normalized"] == "2026-02-25"

def test_quantity_normalization():
    res = ValueNormalizer.normalize_quantity("25 units")
    assert res["valid"] is True
    assert res["normalized"] == 25.0
    assert res["unit"] == "units"

def test_deadline_normalization():
    res = ValueNormalizer.normalize_deadline("delivery within 30 days")
    assert res["valid"] is True
    assert res["days"] == 30

    res_net = ValueNormalizer.normalize_deadline("Net 45 days")
    assert res_net["valid"] is True
    assert res_net["days"] == 45
