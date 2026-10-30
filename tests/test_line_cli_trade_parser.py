"""
Unit tests for the Phase-B trade grammar in the pure LINE slash-command parser.

Covers ``/buy`` ``/sell`` ``/short`` ``/cover`` with the optional
``broker[:account]`` override and the bare-6-digit OTP contract. No I/O — the
parser module is dependency-free (see ``docs/handoff/TASK-line-cli.md`` and the
master directive §1 side→broker routing).
"""

import pytest

from app.services.line_cli import parser as p


# --------------------------------------------------------------------------- #
# happy paths — default side→broker routing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,cmd,broker,account",
    [
        ("/buy PTT 100 12.50", "buy", "lib", "cash"),
        ("/sell KBANK 200 125.25", "sell", "lib", "cash"),
        ("/short PTT 300 12.00", "short", "kss", "margin"),
        ("/cover KBANK 150 120.00", "cover", "kss", "margin"),
    ],
)
def test_trade_default_routing(text, cmd, broker, account):
    parsed = p.parse(text)
    assert isinstance(parsed, p.TradeOrder), parsed
    assert parsed.cmd == cmd
    assert parsed.symbol == text.split()[1].upper()
    assert parsed.broker == broker
    assert parsed.account == account


def test_trade_fields_are_parsed_and_normalised():
    o = p.parse("/buy ptt 100 12.5")
    assert isinstance(o, p.TradeOrder)
    assert o.symbol == "PTT"          # upper-cased
    assert o.volume == 100
    assert o.price == 12.5
    assert o.broker == "lib"
    assert o.account == "cash"


def test_trade_full_width_slash_and_case():
    o = p.parse("／BUY ptt 100 12.5")
    assert isinstance(o, p.TradeOrder)
    assert o.cmd == "buy" and o.symbol == "PTT"


def test_trade_integer_price_is_a_float():
    assert p.parse("/buy PTT 100 12").price == 12.0


@pytest.mark.parametrize(
    "text,cmd",
    [
        ("/ซื้อ PTT 100 12.5", "buy"),
        ("/ขาย KBANK 100 12.5", "sell"),
        ("/ชอร์ต PTT 100 12.5", "short"),
        ("/คัฟเวอร์ PTT 100 12.5", "cover"),
    ],
)
def test_trade_thai_aliases(text, cmd):
    assert p.parse(text).cmd == cmd


@pytest.mark.parametrize(
    "cmd,letter",
    [("buy", "B"), ("sell", "S"), ("short", "H"), ("cover", "C")],
)
def test_trade_side_letter(cmd, letter):
    assert p.parse(f"/{cmd} PTT 100 12.5").side_letter == letter


# --------------------------------------------------------------------------- #
# broker[:account] override
# --------------------------------------------------------------------------- #
def test_override_broker_account():
    o = p.parse("/buy kss:margin PTT 100 12.5")
    assert o.broker == "kss" and o.account == "margin"


def test_override_can_cross_default_routing():
    # lib has no margin account, but the parser stays permissive — the
    # handler's guardrails decide whether a side/broker/account combo is valid.
    assert p.parse("/short lib:cash PTT 100 12.5").broker == "lib"


def test_override_bare_broker_uses_default_account():
    assert p.parse("/buy kss PTT 100 12.5").account == "margin"
    assert p.parse("/cover lib PTT 100 12.5").account == "cash"


def test_override_thai_broker_and_account():
    assert p.parse("/buy กรุงศรี:margin PTT 100 12.5").broker == "kss"
    assert p.parse("/buy kss:เครดิต PTT 100 12.5").account == "margin"


# --------------------------------------------------------------------------- #
# 6-digit bare input = OTP (never a slash command)
# --------------------------------------------------------------------------- #
def test_is_otp_exactly_six_digits():
    assert p.is_otp("123456") is True
    assert p.is_otp(" 123456 ") is True
    assert p.is_otp("12345") is False
    assert p.is_otp("1234567") is False
    assert p.is_otp("12a456") is False
    assert p.is_otp("/buy PTT 100 12.5") is False


def test_bare_otp_is_not_routed_as_a_command():
    assert p.is_command("123456") is False
    assert p.parse("123456") is None


# --------------------------------------------------------------------------- #
# invalid input — rejected cleanly, never a crash
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", ["/buy", "/buy PTT", "/short"])
def test_trade_missing_args(text):
    err = p.parse(text)
    assert isinstance(err, p.CliError)
    assert err.code == p.E_MISSING_ARG


def test_trade_omitted_price_parses():
    order = p.parse("/buy PTT 100")
    assert isinstance(order, p.TradeOrder)
    assert order.symbol == "PTT"
    assert order.volume == 100
    assert order.price is None


def test_trade_extra_args_rejected():
    err = p.parse("/buy kss:margin PTT 100 12.5 extra")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_UNKNOWN_CMD


@pytest.mark.parametrize("text", ["/buy !!! 100 12.5", "/buy 123 100 12.5"])
def test_trade_bad_symbol(text):
    err = p.parse(text)
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_SYMBOL


@pytest.mark.parametrize(
    "text", ["/buy PTT 0 12.5", "/buy PTT abc 12.5", "/buy PTT -5 12.5", "/buy PTT 1.5 12.5"],
)
def test_trade_bad_volume(text):
    err = p.parse(text)
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_VOLUME


@pytest.mark.parametrize(
    "text", ["/buy PTT 100 abc", "/buy PTT 100 0", "/buy PTT 100 -5", "/buy PTT 100 1.2.3"],
)
def test_trade_bad_price(text):
    err = p.parse(text)
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_PRICE


def test_trade_bad_account_in_override():
    err = p.parse("/buy kss:foo PTT 100 12.5")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_ACCOUNT


@pytest.mark.parametrize("text", ["/buy c2w:cash PTT 100 12.5", "/buy c2w PTT 100 12.5"])
def test_trade_bad_broker_override(text):
    err = p.parse(text)
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_BROKER


def test_trade_unknown_side_is_unknown_command():
    err = p.parse("/long PTT 100 12.5")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_UNKNOWN_CMD


# --------------------------------------------------------------------------- #
# no regression on the existing read/broker grammar
# --------------------------------------------------------------------------- #
def test_existing_commands_still_parse():
    assert p.parse("/port kss").broker == "kss"
    assert p.parse("/status").broker == "all"
    assert p.parse("/nego lib PTT").target == "PTT"
