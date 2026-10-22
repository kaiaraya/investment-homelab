"""
Unit tests for SBL commands in LINE CLI (Loop 2).

Covers:
- /sbl, /sbl sync, /sbl pool <symbol>
- /borrow <symbol> <volume>
- /return <symbol> [volume|all]
- Thai aliases and error cases
"""

import pytest
from app.services.line_cli import parser as p


def test_sbl_status_basic():
    cmd = p.parse("/sbl")
    assert isinstance(cmd, p.SblCommand)
    assert cmd.cmd == "sbl"
    assert cmd.subcmd is None
    assert cmd.symbol is None
    assert cmd.broker == "kss"
    assert not cmd.has("sync")


def test_sbl_status_sync():
    cmd = p.parse("/sbl sync")
    assert isinstance(cmd, p.SblCommand)
    assert cmd.has("sync")

    cmd2 = p.parse("/หุ้นยืม sync")
    assert isinstance(cmd2, p.SblCommand)
    assert cmd2.has("sync")


def test_sbl_pool():
    cmd = p.parse("/sbl pool PTT")
    assert isinstance(cmd, p.SblCommand)
    assert cmd.subcmd == "pool"
    assert cmd.symbol == "PTT"


def test_borrow_happy_path():
    cmd = p.parse("/borrow PTT 1000")
    assert isinstance(cmd, p.SblBorrowOrder)
    assert cmd.cmd == "borrow"
    assert cmd.symbol == "PTT"
    assert cmd.volume == 1000
    assert cmd.broker == "kss"

    cmd_thai = p.parse("/ยืมหุ้น DELTA 500")
    assert isinstance(cmd_thai, p.SblBorrowOrder)
    assert cmd_thai.symbol == "DELTA"
    assert cmd_thai.volume == 500


def test_borrow_missing_args():
    err = p.parse("/borrow")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_MISSING_ARG

    err2 = p.parse("/borrow PTT")
    assert isinstance(err2, p.CliError)
    assert err2.code == p.E_MISSING_ARG


def test_borrow_bad_volume():
    err = p.parse("/borrow PTT -100")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_BAD_VOLUME

    err2 = p.parse("/borrow PTT abc")
    assert isinstance(err2, p.CliError)
    assert err2.code == p.E_BAD_VOLUME


def test_return_happy_path():
    cmd = p.parse("/return PTT 1000")
    assert isinstance(cmd, p.SblReturnOrder)
    assert cmd.symbol == "PTT"
    assert cmd.volume == 1000

    cmd_all = p.parse("/return PTT all")
    assert isinstance(cmd_all, p.SblReturnOrder)
    assert cmd_all.symbol == "PTT"
    assert cmd_all.volume is None

    cmd_thai = p.parse("/คืนหุ้น BANPU ทั้งหมด")
    assert isinstance(cmd_thai, p.SblReturnOrder)
    assert cmd_thai.symbol == "BANPU"
    assert cmd_thai.volume is None


def test_return_missing_args():
    err = p.parse("/return")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_MISSING_ARG


def test_sbl_pool_missing_symbol():
    err = p.parse("/sbl pool")
    assert isinstance(err, p.CliError)
    assert err.code == p.E_MISSING_ARG
    assert "ต้องการระบุชื่อหุ้น" in err.message


def test_sbl_pool_thai_alias():
    cmd = p.parse("/หุ้นยืม คลัง PTT")
    assert isinstance(cmd, p.SblCommand)
    assert cmd.subcmd == "pool"
    assert cmd.symbol == "PTT"


def test_borrow_and_return_comma_formatted_volume():
    cmd_borrow = p.parse("/borrow PTT 1,000")
    assert isinstance(cmd_borrow, p.SblBorrowOrder)
    assert cmd_borrow.volume == 1000

    cmd_return = p.parse("/return PTT 2,500")
    assert isinstance(cmd_return, p.SblReturnOrder)
    assert cmd_return.volume == 2500


def test_sbl_broker_isolation_rejects_liberator():
    err1 = p.parse("/sbl lib")
    assert isinstance(err1, p.CliError)
    assert err1.code == p.E_BAD_BROKER
    assert "Credit Balance Margin 3024959" in err1.message

    err2 = p.parse("/borrow lib PTT 1000")
    assert isinstance(err2, p.CliError)
    assert err2.code == p.E_BAD_BROKER

    err3 = p.parse("/return liberator PTT 1000")
    assert isinstance(err3, p.CliError)
    assert err3.code == p.E_BAD_BROKER


def test_sbl_symbol_alias_query_pool():
    cmd = p.parse("/sbl PTT")
    assert isinstance(cmd, p.SblCommand)
    assert cmd.subcmd == "pool"
    assert cmd.symbol == "PTT"


def test_borrow_and_return_explicit_kss_broker():
    cmd_borrow = p.parse("/borrow kss PTT 1000")
    assert isinstance(cmd_borrow, p.SblBorrowOrder)
    assert cmd_borrow.symbol == "PTT"
    assert cmd_borrow.volume == 1000

    cmd_borrow_long = p.parse("/borrow krungsri DELTA 500")
    assert isinstance(cmd_borrow_long, p.SblBorrowOrder)
    assert cmd_borrow_long.symbol == "DELTA"
    assert cmd_borrow_long.volume == 500

    cmd_return = p.parse("/return kss PTT 1000")
    assert isinstance(cmd_return, p.SblReturnOrder)
    assert cmd_return.symbol == "PTT"
    assert cmd_return.volume == 1000

    cmd_return_all = p.parse("/return kss PTT all")
    assert isinstance(cmd_return_all, p.SblReturnOrder)
    assert cmd_return_all.symbol == "PTT"
    assert cmd_return_all.volume is None


def test_sbl_thai_broker_aliases():
    cmd_borrow_thai = p.parse("/borrow กรุงศรี PTT 2000")
    assert isinstance(cmd_borrow_thai, p.SblBorrowOrder)
    assert cmd_borrow_thai.symbol == "PTT"
    assert cmd_borrow_thai.volume == 2000

    cmd_return_thai = p.parse("/return กรุงศรี PTT ทั้งหมด")
    assert isinstance(cmd_return_thai, p.SblReturnOrder)
    assert cmd_return_thai.symbol == "PTT"
    assert cmd_return_thai.volume is None

    err_lib_thai = p.parse("/borrow ลิเบอเรเตอร์ PTT 1000")
    assert isinstance(err_lib_thai, p.CliError)
    assert err_lib_thai.code == p.E_BAD_BROKER
