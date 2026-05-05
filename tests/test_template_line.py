"""Template name prefix matching."""

from finance_common.parsing.template_line import match_template_longest_prefix, strip_template_prefix


class _T:
    def __init__(self, name: str) -> None:
        self.name = name


def test_strip_prefix() -> None:
    assert strip_template_prefix("template rent 500") == "rent 500"
    assert strip_template_prefix("t rent") == "rent"
    assert strip_template_prefix("log rent") is None


def test_longest_prefix() -> None:
    rent = _T("rent")
    monthly = _T("monthly rent")
    templates = [rent, monthly]
    m = match_template_longest_prefix("monthly rent 500", templates)
    assert m is not None
    t, rem = m
    assert t.name == "monthly rent"
    assert rem == "500"
