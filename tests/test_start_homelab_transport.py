"""Regression tests for the dual-transport KDE Connect probe (KDE-RCA-003).

Coverage target: ``scripts.start_homelab.check_kde_live_transport``.

The SMS-OTP hardware bridge can be reached over EITHER physical route:
  * Home Wi-Fi : LAN subnet 192.168.1.x
  * Tailscale  : 100.x.x.x (rides over Wi-Fi *or* mobile 4G/5G)

A Tailscale-IP-only probe FALSE-NEGATIVES when the user is at home with Tailscale OFF
but Wi-Fi still carrying KDE Connect (the OTP channel is perfectly fine). These tests
pin the new behaviour so the gate never blocks a working OTP bridge, while still never
trusting the stale ``kdeconnect-cli`` cache (Invariant 8 / Anti-Mock Guardrail).
"""
import types

import scripts.start_homelab as sh

TAILSCALE_IP = "100.119.166.62"

WIFI_LINE = "ESTAB 0 0 [::ffff:192.168.1.45]:42514 [::ffff:192.168.1.54]:1716\n"
SELF_LINE = "ESTAB 0 0 [::ffff:192.168.1.53]:40000 [::ffff:192.168.1.53]:1716\n"
TS_LINE = "ESTAB 0 0 [::ffff:100.88.217.33]:34768 [::ffff:100.119.166.62]:1716\n"


def _patch_ss(monkeypatch, stdout: str) -> None:
    """Replace the module's ``subprocess`` so ``ss -tn`` returns a canned socket table."""
    fake = types.SimpleNamespace(
        run=lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    )
    monkeypatch.setattr(sh, "subprocess", fake)


def test_live_transport_tailscale_path(monkeypatch):
    """When the Tailscale TCP probe succeeds, report the Tailscale transport."""
    monkeypatch.setattr(sh, "check_tcp_port", lambda *a, **k: True)
    ok, desc = sh.check_kde_live_transport(TAILSCALE_IP, 1716)
    assert ok is True
    assert desc == f"Tailscale ({TAILSCALE_IP}:1716)"


def test_live_transport_wifi_path_when_tailscale_down(monkeypatch):
    """KDE-RCA-003: Tailscale OFF + Home Wi-Fi socket -> must be detected as READY."""
    monkeypatch.setattr(sh, "check_tcp_port", lambda *a, **k: False)
    _patch_ss(monkeypatch, WIFI_LINE)
    ok, desc = sh.check_kde_live_transport(TAILSCALE_IP, 1716)
    assert ok is True
    assert desc == "Home Wi-Fi (192.168.1.54:1716)"


def test_live_transport_ignores_same_host_self_connection(monkeypatch):
    """A gsconnect-style loopback (local == remote IP) must NOT count as a LAN transport."""
    monkeypatch.setattr(sh, "check_tcp_port", lambda *a, **k: False)
    _patch_ss(monkeypatch, SELF_LINE)
    ok, desc = sh.check_kde_live_transport(TAILSCALE_IP, 1716)
    assert ok is False
    assert desc == "no live transport"


def test_live_transport_tailscale_socket_is_not_lan(monkeypatch):
    """A 100.x peer in the socket table must not be misclassified as Home Wi-Fi."""
    monkeypatch.setattr(sh, "check_tcp_port", lambda *a, **k: False)
    _patch_ss(monkeypatch, TS_LINE)
    ok, _ = sh.check_kde_live_transport(TAILSCALE_IP, 1716)
    assert ok is False


def test_live_transport_all_down(monkeypatch):
    """Both transports dead -> not ready, reported truthfully (no fabrication)."""
    monkeypatch.setattr(sh, "check_tcp_port", lambda *a, **k: False)
    _patch_ss(monkeypatch, "")
    ok, desc = sh.check_kde_live_transport(TAILSCALE_IP, 1716)
    assert ok is False
    assert desc == "no live transport"
