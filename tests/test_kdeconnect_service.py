import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.auth import OTPSource, OTPPayload
from app.services.kdeconnect_service import KdeConnectService
from app.core.events import InternalEventBus


@pytest.mark.asyncio
async def test_kdeconnect_process_incoming_krungsri_sms():
    """Verify KDE Connect processes a Krungsri 2FA SMS notification and publishes OTPPayload."""
    test_bus = InternalEventBus()
    svc = KdeConnectService(device_id="test_device_123")

    with patch("app.services.kdeconnect_service.event_bus", test_bus):
        # Simulated Krungsri SMS notification
        sms_text = "Krungsri Sec: รหัส OTP ของคุณคือ 849201 รหัสอ้างอิง BIPE ใช้งานได้ภายใน 3 นาที"
        payload = await svc.process_incoming_notification(
            title="Messages",
            text=sms_text,
            sender="KrungsriSec"
        )

        assert payload is not None
        assert payload.otp == "849201"
        assert payload.ref == "BIPE"
        assert payload.source == OTPSource.KDE_CONNECT
        assert payload.sender == "KrungsriSec"

        # Verify queued in event bus
        assert test_bus.otp_queue.qsize() == 1
        bus_event = await test_bus.otp_queue.get()
        assert bus_event["payload"].otp == "849201"
        assert bus_event["payload"].source == OTPSource.KDE_CONNECT


@pytest.mark.asyncio
async def test_kdeconnect_ignore_non_otp_notification():
    """Verify non-OTP notifications are ignored without publishing to event bus."""
    test_bus = InternalEventBus()
    svc = KdeConnectService(device_id="test_device_123")

    with patch("app.services.kdeconnect_service.event_bus", test_bus):
        payload = await svc.process_incoming_notification(
            title="LINE",
            text="สวัสดีครับ วันนี้มีประชุม 10:00 น.",
            sender="Friend"
        )

        assert payload is None
        assert test_bus.otp_queue.qsize() == 0


@pytest.mark.asyncio
async def test_kdeconnect_send_critical_alert():
    """Verify critical alert sends expected alert via GSConnect or kdeconnect-cli."""
    svc = KdeConnectService(device_id="test_device_123")

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        success = await svc.send_critical_alert(
            title="CUT_LOSS_EXECUTED",
            message="AOT SELL 600 @ 62.25 Matched"
        )

        assert success is True
        assert mock_exec.call_count >= 1
        # Find the call that targeted the device
        target_calls = [c[0] for c in mock_exec.call_args_list if "-d" in c[0]]
        assert len(target_calls) >= 1
        alert_call_args = target_calls[0]
        cli_bin = alert_call_args[0]
        assert "gsconnect" in cli_bin or "kdeconnect-cli" in cli_bin
        assert "-d" in alert_call_args
        assert "test_device_123" in alert_call_args


@pytest.mark.asyncio
async def test_kdeconnect_poll_active_notifications_from_cache(tmp_path):
    """Verify OTP is extracted from GSConnect cache log."""
    import time
    test_bus = InternalEventBus()
    svc = KdeConnectService(device_id="test_device_123")

    fake_cache = tmp_path / "incoming_notifications.jsonl"
    fake_cache.write_text(
        '{"id":"1","appName":"Messages","title":"KrungsriSec","text":"รหัส OTP คือ 918234 รหัสอ้างอิง XYZW","ticker":"","time":'
        + str(int(time.time() * 1000))
        + '}\n',
        encoding="utf-8"
    )

    with patch("asyncio.create_subprocess_exec", return_value=_proc(b"")), \
         patch("os.path.expanduser", return_value=str(fake_cache)), \
         patch("app.services.kdeconnect_service.event_bus", test_bus):
        payload = await svc.poll_active_notifications()

        assert payload is not None
        assert payload.otp == "918234"
        assert payload.ref == "XYZW"
        assert payload.source == OTPSource.KDE_CONNECT


@pytest.mark.asyncio
async def test_kdeconnect_get_network_routes():
    """Verify get_network_routes properly resolves transport status."""
    svc = KdeConnectService(device_id="9507a3fd53f848da9135ebe6253db18a")
    routes = await svc.get_network_routes()
    assert isinstance(routes, dict)
    assert "active_route" in routes
    assert "route_label" in routes
    assert "remote_ip" in routes
    assert "wifi" in routes
    assert "tailscale" in routes


# ---------------------------------------------------------------------------
# is_device_reachable (Invariant 8): real-time, no fabricated reachability.
# Regression guard for the orphaned-method bug where callers raised AttributeError.
# ---------------------------------------------------------------------------

def _proc(stdout: bytes):
    proc = AsyncMock()
    proc.communicate.return_value = (stdout, b"")
    proc.returncode = 0
    return proc


def _dbus_side_effect(icon: bytes = b"('smartphoneconnected',)", reachable: bytes = b"(true,)"):
    def _side(*args, **kwargs):
        if "iconName" in args:
            return _proc(icon)
        return _proc(reachable)
    return _side


@pytest.mark.asyncio
async def test_is_device_reachable_true_when_dbus_live():
    svc = KdeConnectService(device_id="test_device_123")
    with patch("asyncio.create_subprocess_exec", side_effect=_dbus_side_effect()):
        assert await svc.is_device_reachable() is True


@pytest.mark.asyncio
async def test_is_device_reachable_false_when_dbus_not_reachable():
    svc = KdeConnectService(device_id="test_device_123")
    with patch("asyncio.create_subprocess_exec",
               side_effect=_dbus_side_effect(reachable=b"(false,)")):
        assert await svc.is_device_reachable() is False



@pytest.mark.asyncio
async def test_is_device_reachable_never_fabricates_when_all_probes_fail():
    """Regression: when every probe errors, reachability must be False (Anti-Mock)."""
    svc = KdeConnectService(device_id="test_device_123")

    def _boom(*args, **kwargs):
        raise OSError("gdbus not available")

    with patch("asyncio.create_subprocess_exec", side_effect=_boom):
        assert await svc.is_device_reachable() is False


# ---------------------------------------------------------------------------
# KDE-RCA-005: dual-link (LAN + Tailscale) OTP capture.
#   D2  - GSConnect stores the PHONE's SMS creation time, so a Doze/link-flap delayed
#         OTP arrives "old" and was silently dropped by a 300s guard.
#   D1  - journal scan used a fixed rolling window instead of the OTP-request time.
#   U4  - GSConnect (LAN) and kdeconnectd (Tailscale) run in parallel; either may be live.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_accepts_stale_phone_time_when_ref_matches(tmp_path):
    """D2 regression (VJKR incident): a ~7m39s-delayed OTP with a matching Ref must be
    accepted even though its phone-clock `time` is far older than the grace window."""
    import json
    import time

    test_bus = InternalEventBus()
    svc = KdeConnectService(device_id="test_device_123")

    stale_ms = int(time.time() * 1000) - 459_000  # 7m39s late, exactly the real incident
    fake_cache = tmp_path / "incoming_notifications.jsonl"
    fake_cache.write_text(
        json.dumps({
            "id": "1", "appName": "Messages", "title": "KSS-OTP",
            "text": "Your OTP is 749455 (Ref : VJKR)", "ticker": "", "time": stale_ms,
        }) + "\n",
        encoding="utf-8",
    )

    with patch("asyncio.create_subprocess_exec", return_value=_proc(b"")), \
         patch("os.path.expanduser", return_value=str(fake_cache)), \
         patch("app.services.kdeconnect_service.event_bus", test_bus):
        payload = await svc.poll_active_notifications(expected_ref="VJKR")

    assert payload is not None
    assert payload.otp == "749455"
    assert payload.ref == "VJKR"
    assert payload.source == OTPSource.KDE_CONNECT


@pytest.mark.asyncio
async def test_poll_rejects_old_record_when_no_ref_expected(tmp_path):
    """Grace guard still protects against replaying a genuinely old SMS when the caller
    supplies no expected Ref Code (Anti-Mock: never surface a stale code as fresh)."""
    import json
    import time

    test_bus = InternalEventBus()
    svc = KdeConnectService(device_id="test_device_123")

    old_ms = int(time.time() * 1000) - 900_000  # 15 minutes old (> 600s grace)
    fake_cache = tmp_path / "incoming_notifications.jsonl"
    fake_cache.write_text(
        json.dumps({
            "id": "1", "appName": "Messages", "title": "KSS-OTP",
            "text": "Your OTP is 111222 (Ref : OLDX)", "ticker": "", "time": old_ms,
        }) + "\n",
        encoding="utf-8",
    )

    with patch("asyncio.create_subprocess_exec", return_value=_proc(b"")), \
         patch("os.path.expanduser", return_value=str(fake_cache)), \
         patch("app.services.kdeconnect_service.event_bus", test_bus):
        payload = await svc.poll_active_notifications()

    assert payload is None
    assert test_bus.otp_queue.qsize() == 0


@pytest.mark.asyncio
async def test_poll_journal_window_anchored_to_otp_request(tmp_path):
    """U3 regression: the journalctl scan must be anchored to the OTP-request epoch
    (arrival-time semantics) rather than a fixed rolling window."""
    import time

    svc = KdeConnectService(device_id="test_device_123")
    captured = []
    since_ms = int(time.time() * 1000) - 30_000

    def _side(*args, **kwargs):
        if args and args[0] == "journalctl":
            captured.append(list(args))
        return _proc(b"")

    missing_cache = tmp_path / "does_not_exist.jsonl"

    with patch("asyncio.create_subprocess_exec", side_effect=_side), \
         patch("os.path.expanduser", return_value=str(missing_cache)):
        await svc.poll_active_notifications(expected_ref="VJKR", since_ms=since_ms)

    assert captured, "journalctl must have been invoked"
    expected_since = f"@{since_ms // 1000 - 5}"
    assert expected_since in captured[0], f"expected {expected_since} in {captured[0]}"


@pytest.mark.asyncio
async def test_gsconnect_connected_probe_true():
    """U4: GSConnect's own D-Bus service exposes Device.Connected."""
    svc = KdeConnectService(device_id="test_device_123")
    with patch("asyncio.create_subprocess_exec", return_value=_proc(b"(<true>,)")):
        assert await svc._gsconnect_connected() is True


@pytest.mark.asyncio
async def test_gsconnect_connected_probe_never_fabricates():
    """U4 / Anti-Mock: a failing probe must report False (unknown), never True."""
    svc = KdeConnectService(device_id="test_device_123")

    def _boom(*args, **kwargs):
        raise OSError("GSConnect D-Bus unavailable")

    with patch("asyncio.create_subprocess_exec", side_effect=_boom):
        assert await svc._gsconnect_connected() is False


@pytest.mark.asyncio
async def test_is_device_reachable_true_via_gsconnect_parallel_link():
    """U4: kdeconnectd's link (Tailscale) reports unreachable, but GSConnect's LAN link is
    Connected -> the phone IS reachable. Previously this returned False and the driver
    wrongly declared the OTP bridge offline."""
    svc = KdeConnectService(device_id="test_device_123")

    def _side(*args, **kwargs):
        if "org.gnome.Shell.Extensions.GSConnect" in args:
            return _proc(b"(<true>,)")
        return _proc(b"(false,)")

    with patch("asyncio.create_subprocess_exec", side_effect=_side):
        assert await svc.is_device_reachable() is True



