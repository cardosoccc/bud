from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

import pytest

from bud.filter import parse_filter, apply_filter, FilterClause


# --- parse_filter tests ---


def test_parse_single_tag_clause():
    clauses = parse_filter("t=fixo")
    assert len(clauses) == 1
    assert clauses[0] == FilterClause(field="t", operator="=", value="fixo")


def test_parse_multiple_clauses():
    clauses = parse_filter("c=outros;t=fixo,mercado;v>3;d=transfer")
    assert len(clauses) == 4
    assert clauses[0] == FilterClause(field="c", operator="=", value="outros")
    assert clauses[1] == FilterClause(field="t", operator="=", value="fixo,mercado")
    assert clauses[2] == FilterClause(field="v", operator=">", value="3")
    assert clauses[3] == FilterClause(field="d", operator="=", value="transfer")


def test_parse_exact_description():
    clauses = parse_filter("d==transferência banco->inter")
    assert len(clauses) == 1
    assert clauses[0].operator == "=="
    assert clauses[0].value == "transferência banco->inter"


def test_parse_numeric_operators():
    for op in ("=", "==", ">", "<", ">=", "<="):
        clauses = parse_filter(f"v{op}100")
        assert clauses[0].operator == op


def test_parse_empty_string():
    assert parse_filter("") == []


def test_parse_strips_whitespace():
    clauses = parse_filter(" t=fixo ; c=outros ")
    assert len(clauses) == 2


def test_parse_invalid_clause_raises():
    with pytest.raises(ValueError, match="invalid filter clause"):
        parse_filter("x=bad")


def test_parse_invalid_no_operator_raises():
    with pytest.raises(ValueError, match="invalid filter clause"):
        parse_filter("tfixo")


# --- apply_filter tests ---


@dataclass
class FakeAccount:
    name: str = ""


@dataclass
class FakeRecord:
    description: str = ""
    value: Decimal = Decimal("0")
    tags: List[str] = field(default_factory=list)
    category: Optional[object] = None
    account: Optional[FakeAccount] = None


@dataclass
class FakeCategory:
    name: str = ""


def _make(desc="", value=0, tags=None, cat_name="", acct_name=""):
    cat = FakeCategory(name=cat_name) if cat_name else None
    acct = FakeAccount(name=acct_name) if acct_name else None
    return FakeRecord(
        description=desc,
        value=Decimal(str(value)),
        tags=tags or [],
        category=cat,
        account=acct,
    )


def test_filter_by_single_tag():
    items = [_make(tags=["fixo"]), _make(tags=["variável"]), _make(tags=["fixo", "moradia"])]
    result = apply_filter(items, "t=fixo")
    assert len(result) == 2


def test_filter_by_multiple_tags_and_logic():
    items = [_make(tags=["fixo", "moradia"]), _make(tags=["fixo"]), _make(tags=["moradia"])]
    result = apply_filter(items, "t=fixo,moradia")
    assert len(result) == 1
    assert result[0].tags == ["fixo", "moradia"]


def test_filter_by_category():
    items = [_make(cat_name="outros"), _make(cat_name="salário"), _make(cat_name="outros")]
    result = apply_filter(items, "c=outros")
    assert len(result) == 2


def test_filter_by_category_case_insensitive():
    items = [_make(cat_name="Outros")]
    result = apply_filter(items, "c=outros")
    assert len(result) == 1


def test_filter_by_description_substring():
    items = [_make(desc="transferência banco->inter"), _make(desc="mercado"), _make(desc="transfer pix")]
    result = apply_filter(items, "d=transfer")
    assert len(result) == 2


def test_filter_by_description_exact():
    items = [_make(desc="transferência"), _make(desc="transferência banco")]
    result = apply_filter(items, "d==transferência")
    assert len(result) == 1


def test_filter_by_description_case_insensitive():
    items = [_make(desc="Mercado")]
    result = apply_filter(items, "d=mercado")
    assert len(result) == 1


def test_filter_by_value_greater():
    items = [_make(value=100), _make(value=50), _make(value=-200)]
    result = apply_filter(items, "v>60")
    assert len(result) == 1
    assert result[0].value == Decimal("100")


def test_filter_by_value_less():
    items = [_make(value=100), _make(value=-50), _make(value=-200)]
    result = apply_filter(items, "v<0")
    assert len(result) == 2


def test_filter_by_value_equal():
    items = [_make(value=100), _make(value=100.00), _make(value=99)]
    result = apply_filter(items, "v=100")
    assert len(result) == 2


def test_filter_by_value_gte():
    items = [_make(value=100), _make(value=99), _make(value=101)]
    result = apply_filter(items, "v>=100")
    assert len(result) == 2


def test_filter_by_value_lte():
    items = [_make(value=-100), _make(value=-99), _make(value=-101)]
    result = apply_filter(items, "v<=-100")
    assert len(result) == 2


def test_combined_filter():
    items = [
        _make(desc="aluguel", value=-1500, tags=["fixo", "moradia"], cat_name="moradia"),
        _make(desc="mercado", value=-200, tags=["variável"], cat_name="outros"),
        _make(desc="aluguel ações", value=50, tags=["fixo"], cat_name="rendimentos"),
    ]
    result = apply_filter(items, "t=fixo;v<0")
    assert len(result) == 1
    assert result[0].description == "aluguel"


def test_filter_no_match():
    items = [_make(tags=["fixo"])]
    result = apply_filter(items, "t=variável")
    assert len(result) == 0


def test_filter_empty_tags_no_match():
    items = [_make(tags=[])]
    result = apply_filter(items, "t=fixo")
    assert len(result) == 0


def test_filter_none_tags_no_match():
    r = FakeRecord(tags=None)
    result = apply_filter([r], "t=fixo")
    assert len(result) == 0


def test_filter_no_category_no_match():
    items = [_make(cat_name="")]
    result = apply_filter(items, "c=outros")
    assert len(result) == 0


def test_custom_get_description():
    """Simulates forecast-style records with base_description."""
    @dataclass
    class FakeRecurrence:
        base_description: str = ""

    @dataclass
    class FakeForecast:
        description: str = ""
        value: Decimal = Decimal("0")
        tags: List[str] = field(default_factory=list)
        category: Optional[object] = None
        recurrence: Optional[FakeRecurrence] = None

    items = [
        FakeForecast(description="", value=Decimal("-100"), tags=["fixo"],
                     recurrence=FakeRecurrence(base_description="aluguel")),
        FakeForecast(description="mercado", value=Decimal("-50"), tags=["variável"]),
    ]
    result = apply_filter(
        items,
        "d=aluguel",
        get_description=lambda f: (f.recurrence.base_description if f.recurrence and f.recurrence.base_description else f.description) or "",
    )
    assert len(result) == 1


def test_invalid_numeric_value_raises():
    items = [_make(value=100)]
    with pytest.raises(ValueError, match="invalid numeric value"):
        apply_filter(items, "v>abc")


# --- account filter tests ---


def test_parse_account_clause():
    clauses = parse_filter("a=bb")
    assert len(clauses) == 1
    assert clauses[0] == FilterClause(field="a", operator="=", value="bb")


def test_filter_by_account():
    items = [_make(acct_name="bb"), _make(acct_name="nubank"), _make(acct_name="bb")]
    result = apply_filter(items, "a=bb")
    assert len(result) == 2


def test_filter_by_account_case_insensitive():
    items = [_make(acct_name="BB"), _make(acct_name="Nubank")]
    result = apply_filter(items, "a=bb")
    assert len(result) == 1


def test_filter_by_account_no_match():
    items = [_make(acct_name="nubank")]
    result = apply_filter(items, "a=bb")
    assert len(result) == 0


def test_filter_by_account_none():
    items = [_make()]  # no account
    result = apply_filter(items, "a=bb")
    assert len(result) == 0


def test_filter_by_account_combined():
    items = [
        _make(desc="aluguel", value=-1500, acct_name="bb", cat_name="moradia"),
        _make(desc="mercado", value=-200, acct_name="nubank", cat_name="outros"),
        _make(desc="salário", value=5000, acct_name="bb", cat_name="rendimentos"),
    ]
    result = apply_filter(items, "a=bb;v<0")
    assert len(result) == 1
    assert result[0].description == "aluguel"


def test_filter_by_account_no_attr():
    """Records without an account attribute (e.g. forecasts) are excluded."""

    @dataclass
    class NoAccountRecord:
        description: str = ""
        value: Decimal = Decimal("0")
        tags: List[str] = field(default_factory=list)
        category: Optional[object] = None

    items = [NoAccountRecord(description="rent", value=Decimal("-100"))]
    result = apply_filter(items, "a=bb")
    assert len(result) == 0
