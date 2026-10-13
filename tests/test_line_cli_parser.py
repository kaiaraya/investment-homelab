"""
Unit tests for the pure LINE slash-command parser.

No I/O, no DB, no settings — see `docs/handoff/TASK-line-cli.md` step 1-2.
"""

import pytest

from app.services.line_cli import parser as p


# --------------------------------------------------------------------------- #
# routing gate
# --------------------------------------------------------------------------- #
def test_non_slash_text_is_not_a_command():
    assert p.is_command("hello homelab") is False
    assert p.parse("hello homelab") is None


def test_full_width_slash_and_case_and_spacing_are_normalised():
    assert p.is_command("／PORT") is True
    cmd = p.parse("／  PORT   kss  ")
    assert isinstance(cmd, p.CliCommand)
    assert cmd.cmd == "port"
    assert cmd.broker == "kss"


# --------------------------------------------------------------------------- #
# happy paths
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,cmd,broker",
    [
        ("/status", "status", "all"),
        ("/status kss", "status", "kss"),
        ("/สถานะ", "status", "all"),
        ("/port", "port", "all"),
        ("/พอร์ต lib", "port", "lib"),
        ("/orders kss sync", "orders", "kss"),
        ("/ออเดอร์ all", "orders", "all"),
        ("/cash lib", "cash", "lib"),
        ("/เงิน", "cash", "all"),
    ],
)
def test_read_commands_default_broker_all(text, cmd, broker):
    parsed = p.parse(text)
    assert isinstance(parsed, p.CliCommand), parsed
    assert parsed.cmd == cmd
    assert parsed.broker == broker


def test_help_with_and_without_topic():
    assert p.parse("/help") == p.CliCommand(cmd="help", target=None)
    assert p.parse("/ช่วย nego") == p.CliCommand(cmd="help", target="nego")


def test_login_force_and_logout_aliases():
    cmd = p.parse("/login kss force")
    assert cmd == p.CliCommand(cmd="login", broker="kss", flags={"force"})
    assert p.parse("/ออกระบบ lib") == p.CliCommand(cmd="logout", broker="lib")


def test_broker_aliases_map_to_kss_and_lib():
    assert p.parse("/port กรุงศรี").broker == "kss"
    assert p.parse("/port trademan").broker == "kss"
    assert p.parse("/port ลิเบอเรเตอร์").broker == "lib"
    assert p.parse("/port ทั้งหมด").broker == "all"


# --------------------------------------------------------------------------- #
# flags
# --------------------------------------------------------------------------- #
def test_sync_flag_only_kept_for_reads():
    assert "sync" in p.parse("/port kss sync").flags
    # /login does not take sync -> dropped
    assert p.parse("/login kss sync").flags == set()
    # force on a read command is dropped
    assert p.parse("/port kss force").flags == set()


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
def test_unknown_command_suggests_nearest():
    err = p.parse("/prot")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_UNKNOWN_CMD
    assert "/port" in err.suggestions


def test_bad_broker_is_rejected():
    err = p.parse("/port c2w")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_BROKER


@pytest.mark.parametrize("text", ["/login", "/logout", "/nego"])
def test_broker_required_commands_ask_for_broker(text):
    err = p.parse(text)
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BROKER_REQUIRED
    assert any("kss" in q for q in err.quick_reply)


# --------------------------------------------------------------------------- #
# /nego target
# --------------------------------------------------------------------------- #
def test_nego_without_target_targets_all():
    cmd = p.parse("/nego kss")
    assert isinstance(cmd, p.CliCommand)
    assert cmd.broker == "kss" and cmd.target is None


def test_nego_symbol_and_order_no_targets():
    assert p.parse("/nego lib PTT").target == "PTT"
    assert p.parse("/nego kss ptt").target == "PTT"      # upper-cased
    assert p.parse("/nego kss 12345").target == "12345"


def test_nego_bad_target_is_rejected():
    err = p.parse("/nego kss !!!")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_TARGET


def test_extra_parameter_is_rejected():
    err = p.parse("/status kss extra")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_UNKNOWN_CMD
