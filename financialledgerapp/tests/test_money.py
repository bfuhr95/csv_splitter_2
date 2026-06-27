"""Unit tests for ledger.money: cents conversion, formatting, parsing."""

from __future__ import annotations

import unittest
from decimal import Decimal

from ledger.money import ZERO, fmt, from_cents, parse_money, to_cents


class ToCentsTest(unittest.TestCase):
    def test_whole_dollars(self):
        self.assertEqual(to_cents(Decimal("10")), 1000)
        self.assertEqual(to_cents(10), 1000)
        self.assertEqual(to_cents("10"), 1000)

    def test_dollars_and_cents(self):
        self.assertEqual(to_cents(Decimal("12.34")), 1234)
        self.assertEqual(to_cents("0.01"), 1)
        self.assertEqual(to_cents("0.99"), 99)

    def test_zero(self):
        self.assertEqual(to_cents(ZERO), 0)
        self.assertEqual(to_cents(0), 0)
        self.assertEqual(to_cents("0.00"), 0)

    def test_half_up_rounding(self):
        # ROUND_HALF_UP at the third decimal place.
        self.assertEqual(to_cents("1.005"), 101)
        self.assertEqual(to_cents("1.015"), 102)
        self.assertEqual(to_cents("2.675"), 268)
        self.assertEqual(to_cents("0.004"), 0)
        self.assertEqual(to_cents("0.005"), 1)

    def test_negative_half_up(self):
        # ROUND_HALF_UP rounds the magnitude away from zero.
        self.assertEqual(to_cents("-1.005"), -101)
        self.assertEqual(to_cents(Decimal("-50")), -5000)

    def test_large_value(self):
        self.assertEqual(to_cents("1234567.89"), 123456789)


class FromCentsTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(from_cents(1234), Decimal("12.34"))
        self.assertEqual(from_cents(1), Decimal("0.01"))
        self.assertEqual(from_cents(0), Decimal("0.00"))

    def test_negative(self):
        self.assertEqual(from_cents(-5000), Decimal("-50.00"))

    def test_quantized_to_two_places(self):
        result = from_cents(100)
        self.assertEqual(result, Decimal("1.00"))
        # Exponent of -2 means two decimal places retained.
        self.assertEqual(result.as_tuple().exponent, -2)

    def test_roundtrip(self):
        for dollars in ["0.00", "1.00", "12.34", "1000.99", "-7.50"]:
            cents = to_cents(dollars)
            self.assertEqual(from_cents(cents), Decimal(dollars))


class ZeroConstantTest(unittest.TestCase):
    def test_value_and_precision(self):
        self.assertEqual(ZERO, Decimal("0.00"))
        self.assertEqual(ZERO.as_tuple().exponent, -2)


class FmtTest(unittest.TestCase):
    def test_thousands_separator(self):
        self.assertEqual(fmt(Decimal("1234.56")), "1,234.56")
        self.assertEqual(fmt(Decimal("1000000")), "1,000,000.00")

    def test_small_values(self):
        self.assertEqual(fmt(Decimal("0")), "0.00")
        self.assertEqual(fmt(Decimal("5")), "5.00")
        self.assertEqual(fmt(Decimal("999.9")), "999.90")

    def test_negative_in_parentheses(self):
        self.assertEqual(fmt(Decimal("-1234.56")), "(1,234.56)")
        self.assertEqual(fmt(Decimal("-0.01")), "(0.01)")

    def test_accepts_int_and_str(self):
        self.assertEqual(fmt(1234), "1,234.00")
        self.assertEqual(fmt("1234.5"), "1,234.50")

    def test_rounding_in_fmt(self):
        self.assertEqual(fmt("1.005"), "1.01")


class ParseMoneyTest(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(parse_money("100"), Decimal("100.00"))
        self.assertEqual(parse_money("12.34"), Decimal("12.34"))

    def test_strips_currency_symbol(self):
        self.assertEqual(parse_money("$2,000"), Decimal("2000.00"))
        self.assertEqual(parse_money("$ 1.50"), Decimal("1.50"))

    def test_strips_commas(self):
        self.assertEqual(parse_money("1,234,567.89"), Decimal("1234567.89"))

    def test_parentheses_are_negative(self):
        self.assertEqual(parse_money("(1,234.56)"), Decimal("-1234.56"))
        self.assertEqual(parse_money("($1,000.00)"), Decimal("-1000.00"))

    def test_leading_minus(self):
        self.assertEqual(parse_money("-50"), Decimal("-50.00"))
        self.assertEqual(parse_money("-$50.25"), Decimal("-50.25"))

    def test_leading_plus(self):
        self.assertEqual(parse_money("+50"), Decimal("50.00"))

    def test_empty_and_whitespace(self):
        self.assertEqual(parse_money(""), ZERO)
        self.assertEqual(parse_money("   "), ZERO)
        self.assertEqual(parse_money(None), ZERO)

    def test_parens_with_only_symbols(self):
        # "()" reduces to empty interior -> ZERO.
        self.assertEqual(parse_money("()"), ZERO)

    def test_surrounding_whitespace(self):
        self.assertEqual(parse_money("  42.00  "), Decimal("42.00"))

    def test_double_negative_cancels(self):
        # Parentheses (negative) plus an internal leading minus cancel out.
        self.assertEqual(parse_money("(-50)"), Decimal("50.00"))

    def test_result_is_quantized(self):
        self.assertEqual(parse_money("7").as_tuple().exponent, -2)


if __name__ == "__main__":
    unittest.main()
