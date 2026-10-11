import asyncio
import json
import logging
import os
import re
import shutil
import time
from typing import Any, Optional

from app.core.config import settings
from app.core.events import event_bus
from app.schemas.auth import OTPPayload, OTPSource
from app.ai.otp_agent import extract_otp_from_text
from app.db.session import AsyncSessionLocal
from app.db.models import SessionLog

logger = logging.getLogger(__name__)

DEFAULT_DEVICE_ID = os.getenv("KDECONNECT_DEVICE_ID", "9507a3fd53f848da9135ebe6253db18a")

# GSConnect (the GNOME Shell extension, daemon "gjs") exposes its OWN D-Bus service and
# device object tree. It and the native `kdeconnectd` daemon run in PARALLEL and can each
# hold a different transport to the same phone (GSConnect = LAN/Wi-Fi, kdeconnectd =
# Tailscale). See KDE-RCA-004 (twin daemons) / KDE-RCA-005 (dual-link OTP capture).
GSCONNECT_DBUS_NAME = "org.gnome.Shell.Extensions.GSConnect"
GSCONNECT_DEVICE_PREFIX = "/org/gnome/Shell/Extensions/GSConnect/Device"


class KdeConnectService:
    """
    Hardware Bridge for Android (Mi 10T) integration via GSConnect & KDE Connect:
    1. Inbound SMS OTP Interception (Zero-Cloud Local Wi-Fi & Tailscale VPN).
    2. Outbound Critical Alert Notifier (Cut Loss, SBL Return, Session Crash).
    """

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id or DEFAULT_DEVICE_ID

    def _get_gsconnect_bin(self) -> Optional[str]:
        """Returns path to gsconnect CLI if available."""
        return shutil.which("gsconnect") or (
            os.path.expanduser("~/.local/bin/gsconnect")
            if os.path.exists(os.path.expanduser("~/.local/bin/gsconnect"))
            else None
        )

    async def get_reachable_device_id(self) -> Optional[str]:
        """Returns reachable device ID if available, prioritizing the configured target Android device."""
        # 1. First priority: Check reachable devices via kdeconnect-cli
        try:
            proc = await asyncio.create_subprocess_exec(
                "kdeconnect-cli", "-a", "--id-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            devices = [d.strip() for d in stdout.decode().splitlines() if d.strip()]
            if self.device_id in devices:
                return self.device_id
            for dev in devices:
                if dev != "92bf51aaea244830b7ed6a9af0115556" and "nuc" not in dev.lower():
                    return dev
        except Exception as e:
            logger.debug(f"kdeconnect-cli check error: {e}")

        # 2. Check GSConnect CLI if available
        gsconnect_bin = self._get_gsconnect_bin()
        if gsconnect_bin:
            try:
                proc = await asyncio.create_subprocess_exec(
                    gsconnect_bin, "-a",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                for line in stdout.decode().splitlines():
                    parts = [p.strip() for p in line.split("\t") if p.strip()]
                    if len(parts) >= 3 and parts[2].lower() == "true":
                        if parts[0] != "92bf51aaea244830b7ed6a9af0115556" and "nuc" not in parts[1].lower():
                            return parts[0]
                    if len(parts) >= 4 and parts[3].lower() == "true" and parts[0] == self.device_id:
                        return parts[0]
            except Exception as e:
                logger.debug(f"GSConnect device check error: {e}")

        return self.device_id

    async def refresh_devices(self) -> None:
        """Triggers discovery refresh across network/Tailscale."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "busctl", "--user", "call",
                "org.gnome.Shell.Extensions.GSConnect",
                "/org/gnome/Shell/Extensions/GSConnect",
                "org.gtk.Actions", "Activate", "sava{sv}", "refresh", "0", "0",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
        except Exception:
            pass

        try:
            proc = await asyncio.create_subprocess_exec(
                "kdeconnect-cli", "--refresh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        except Exception as e:
            logger.debug(f"KDE Connect refresh error: {e}")

    async def _gsconnect_connected(self) -> bool:
        """
        U4 (KDE-RCA-005): probes GSConnect's *own* D-Bus service for the device's live
        ``Connected`` property.

        GSConnect and the native ``kdeconnectd`` daemon genuinely run in parallel and can
        each hold a different transport to the same phone (GSConnect = LAN/Wi-Fi,
        kdeconnectd = Tailscale). GSConnect exposes NO notifications interface over D-Bus,
        but it DOES expose ``org.gnome.Shell.Extensions.GSConnect.Device.Connected`` — the
        authoritative liveness signal for the LAN link. Never fabricates a result
        (Anti-Mock Guardrail): any failure means "unknown" -> False.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "gdbus", "call", "--session",
                "--dest", GSCONNECT_DBUS_NAME,
                "--object-path", f"{GSCONNECT_DEVICE_PREFIX}/{self.device_id}",
                "--method", "org.freedesktop.DBus.Properties.Get",
                "org.gnome.Shell.Extensions.GSConnect.Device", "Connected",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            out = stdout.decode().strip().lower()
            return "true" in out
        except Exception as e:
            logger.debug(f"GSConnect D-Bus Connected probe error: {e}")
            return False

    async def is_device_reachable(self) -> bool:
        """
        Determines whether the configured Android device is reachable RIGHT NOW.

        Invariant 8: validates live D-Bus ``isReachable`` (with a parallel GSConnect
        link fallback) and never trusts a stale ``kdeconnect-cli -l`` cache. ``iconName``
        / ``statusIconName`` are deliberately NOT consulted — proven unreliable
        (KDE-RCA-008 REVISED). Returns False unless a
        live device is positively confirmed — it must never fabricate reachability
        (Anti-Mock Guardrail).

        NOTE: This method body previously lived orphaned inside ``refresh_devices()``
        (its ``def`` line was lost), which made every caller raise AttributeError.
        Restored and hardened here.
        """
        kdeconnectd_denied = False

        # 1. Primary: Check real-time D-Bus connection state (detects if phone is asleep/disconnected)
        try:
            target = self.device_id
            proc_dbus = await asyncio.create_subprocess_exec(
                "gdbus", "call", "--session",
                "--dest", "org.kde.kdeconnect",
                "--object-path", f"/modules/kdeconnect/devices/{target}",
                "--method", "org.freedesktop.DBus.Properties.Get",
                "org.kde.kdeconnect.device", "isReachable",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_dbus, _ = await proc_dbus.communicate()
            out_str = stdout_dbus.decode().strip().lower()
            if "true" in out_str:
                # KDE-RCA-008 (REVISED): `iconName`/`statusIconName` are UNRELIABLE —
                # `iconName` reads 'smartphonedisconnected' even while the phone is
                # connected (verified live via ping). The authoritative transport-link
                # signal is real-time D-Bus `isReachable`.
                return True
            elif "false" in out_str:
                # kdeconnectd's link is down — but GSConnect may still hold a live LAN link
                # to the same phone. Do NOT declare the whole bridge dead here; fall through
                # to the parallel GSConnect probe (U4 / KDE-RCA-005).
                logger.debug(f"kdeconnectd D-Bus reports device {target} is not reachable (isReachable: false)")
                kdeconnectd_denied = True
        except Exception as e:
            logger.debug(f"KDE Connect D-Bus check error: {e}")

        # 2. Parallel daemon (U4): GSConnect owns its OWN D-Bus service and may hold a live LAN
        #    link even when kdeconnectd's Tailscale link is down (and vice-versa). If it
        #    affirmatively reports Connected, the phone IS reachable -> return True.
        if await self._gsconnect_connected():
            logger.debug("GSConnect D-Bus reports device Connected (parallel LAN link).")
            return True
        if kdeconnectd_denied:
            logger.debug(f"All live D-Bus links report device {target} unreachable.")
            return False

        # 3. Secondary fallback: Check reachable devices via kdeconnect-cli
        try:
            proc = await asyncio.create_subprocess_exec(
                "kdeconnect-cli", "-a", "--id-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            devices = [d.strip() for d in stdout.decode().splitlines() if d.strip()]
            if self.device_id in devices:
                return True
            for dev in devices:
                if dev != "92bf51aaea244830b7ed6a9af0115556" and "nuc" not in dev.lower():
                    return True
        except Exception as e:
            logger.debug(f"kdeconnect-cli reachability check error: {e}")

        # 2. Secondary fallback: GSConnect CLI
        gsconnect_bin = self._get_gsconnect_bin()
        if gsconnect_bin:
            try:
                proc = await asyncio.create_subprocess_exec(
                    gsconnect_bin, "-a",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                for line in stdout.decode().splitlines():
                    parts = [p.strip() for p in line.split("\t") if p.strip()]
                    if len(parts) >= 3 and parts[2].lower() == "true":
                        return True
            except Exception:
                pass

        # No live device could be positively confirmed via D-Bus, kdeconnect-cli,
        # or GSConnect. Never fabricate reachability (Invariant 8 / Anti-Mock).
        return False

    async def send_critical_alert(self, title: str, message: str) -> bool:
        """
        Pushes a critical high-priority alert to the user's Android device.
        Primary: kdeconnect-cli (reaches phone across Tailscale VPN and Wi-Fi).
        Fallback: GSConnect.
        """
        # Target strictly the mobile phone (Mi 10T), NEVER NUC-Intel or other desktop machines
        target_dev = self.device_id
        if target_dev in ["92bf51aaea244830b7ed6a9af0115556"] or "nuc" in str(target_dev).lower():
            target_dev = DEFAULT_DEVICE_ID
        alert_title = f"🚨 [{title.strip()}]"
        alert_msg = message.strip()
        ping_body = f"{alert_title}\n{alert_msg}"

        # 1. Primary: Use native kdeconnect-cli (works on both Tailscale 4G/5G and Home Wi-Fi)
        try:
            proc = await asyncio.create_subprocess_exec(
                "kdeconnect-cli", "-d", target_dev, "--ping-msg", ping_body,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                logger.info(f"Critical alert sent to Android device {target_dev} via KDE Connect CLI.")
                return True
            else:
                logger.warning(f"KDE Connect CLI ping returned non-zero exit code: {proc.returncode}")
        except Exception as e:
            logger.debug(f"KDE Connect CLI alert error: {e}")

        # 2. Fallback: GSConnect (for local Wi-Fi if kdeconnect-cli failed)
        gsconnect_bin = self._get_gsconnect_bin()
        if gsconnect_bin:
            try:
                proc_notif = await asyncio.create_subprocess_exec(
                    gsconnect_bin, "-d", target_dev,
                    f"--notification={alert_title}",
                    f"--notification-body={alert_msg}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc_notif.communicate()

                proc_ping = await asyncio.create_subprocess_exec(
                    gsconnect_bin, "-d", target_dev, "--ping",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc_ping.communicate()

                if proc_notif.returncode == 0 or proc_ping.returncode == 0:
                    logger.info(f"Critical alert sent to Android device {target_dev} via GSConnect fallback.")
                    return True
            except Exception as e:
                logger.debug(f"GSConnect alert fallback error: {e}")

        return False

    async def notify_admin_screen_help(self, reason: str, workflow_or_step: Optional[str] = None) -> bool:
        """
        Pushes a dedicated Human-In-The-Loop escalation alert to Admin's Android device:
        '🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย'
        Triggered when automation encounters an unresolvable anomaly, modal, or verification failure.
        """
        msg = f"มาดูที่จอหน่อย มีปัญหาให้ช่วย\n• สาเหตุ: {reason}"
        if workflow_or_step:
            msg += f"\n• จุดที่ติดขัด: {workflow_or_step}"
        return await self.send_critical_alert("HITL Escalation", msg)

    async def process_incoming_notification(
        self,
        title: str,
        text: str,
        sender: Optional[str] = None
    ) -> Optional[OTPPayload]:
        """
        Inspects an incoming notification string from the mobile device.
        Extracts 6-digit OTP + Ref Code and publishes to EventBus.
        """
        combined_text = f"{title} {text}".strip()
        extract_res = await extract_otp_from_text(combined_text)

        if extract_res.otp:
            logger.info(
                f"KDE Connect intercepted OTP: {extract_res.otp[:2]}**** "
                f"(Ref: {extract_res.ref or 'N/A'})"
            )
            payload = OTPPayload(
                source=OTPSource.KDE_CONNECT,
                otp=extract_res.otp,
                ref=extract_res.ref,
                sender=sender or title
            )
            await event_bus.publish_otp(payload)

            # Persist to database log for cross-process recovery
            try:
                async with AsyncSessionLocal() as db:
                    log = SessionLog(
                        event_type="KDECONNECT_OTP_RECEIVED",
                        details=f"Received SMS OTP: {payload.otp} (Ref: {payload.ref or 'N/A'})"
                    )
                    db.add(log)
                    await db.commit()
            except Exception as e:
                logger.debug(f"DB log error for KDE Connect OTP: {e}")

            return payload

        return None

    @staticmethod
    def _extract_json_packets(text: str) -> list[dict]:
        """Extracts complete JSON objects from multi-line indented journalctl logs."""
        packets = []
        for m in re.finditer(r"\{\s*\"(?:id|type)\"", text):
            start = m.start()
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                c = text[i]
                if c == "\"" and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            json_str = text[start:i+1]
                            try:
                                data = json.loads(json_str)
                                if isinstance(data, dict):
                                    packets.append(data)
                            except Exception:
                                pass
                            break
                escape = (c == "\\" and not escape)
        return packets

    async def poll_active_notifications(
        self,
        expected_ref: Optional[str] = None,
        since_ms: Optional[int] = None
    ) -> Optional[OTPPayload]:
        """
        Polls active SMS and notifications across GSConnect cache, systemd journal,
        and legacy D-Bus to capture pending SMS OTP.
        Optionally matches against an expected Krungsri Ref Code.

        Args:
            expected_ref: Broker Ref Code scraped from the login page. A definitive match
                bypasses the age guard entirely (KDE-RCA-005).
            since_ms: Local wall-clock epoch (ms) at which the OTP was requested. Anchors the
                journal scan to *arrival* time instead of a fixed rolling window, so a late /
                Android-Doze-delayed push is still captured.
        """
        target_dev = await self.get_reachable_device_id()
        if not target_dev:
            return None

        current_time_ms = int(time.time() * 1000)
        norm_expected_ref = expected_ref.strip().upper() if expected_ref else None
        # KDE-RCA-005: phone-clock `date`/`time` is NOT arrival time. Widen the generic age
        # guard (configurable) and let a definitive Ref Code match bypass it.
        grace_ms = int(getattr(settings, "OTP_STALENESS_GRACE_SECONDS", 600)) * 1000

        # 1. Primary: Direct KDE Connect CLI notification check (supports both Tailscale VPN & Home Wi-Fi)
        try:
            proc_cli = await asyncio.create_subprocess_exec(
                "kdeconnect-cli", "-d", target_dev, "--list-notifications",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_cli, _ = await proc_cli.communicate()
            if stdout_cli:
                for line in stdout_cli.decode().splitlines():
                    clean_l = line.strip()
                    if not clean_l:
                        continue
                    extract_res = await extract_otp_from_text(clean_l)
                    if extract_res.otp:
                        if norm_expected_ref and extract_res.ref and extract_res.ref.upper() != norm_expected_ref:
                            continue
                        logger.info(f"KDE Connect CLI intercepted OTP: {extract_res.otp} (Ref: {extract_res.ref})")
                        payload = OTPPayload(
                            source=OTPSource.KDE_CONNECT,
                            otp=extract_res.otp,
                            ref=extract_res.ref,
                            sender="kdeconnect-cli"
                        )
                        await event_bus.publish_otp(payload)
                        return payload
        except Exception as e:
            logger.debug(f"KDE Connect CLI list-notifications check error: {e}")

        # 2. Native KDE Connect D-Bus active notifications inspection
        try:
            proc = await asyncio.create_subprocess_exec(
                "gdbus", "call", "--session", "--dest", "org.kde.kdeconnect",
                "--object-path", f"/modules/kdeconnect/devices/{target_dev}/notifications",
                "--method", "org.kde.kdeconnect.device.notifications.activeNotifications",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            out = stdout.decode().strip()

            match = re.search(r'\(\[([^\]]*)\],?\)', out)
            if match:
                ids_str = match.group(1).replace("'", "").replace('"', '').strip()
                notif_ids = [i.strip() for i in ids_str.split(',') if i.strip()]

                for nid in notif_ids:
                    p_prop = await asyncio.create_subprocess_exec(
                        "gdbus", "call", "--session", "--dest", "org.kde.kdeconnect",
                        "--object-path", f"/modules/kdeconnect/devices/{target_dev}/notifications/{nid}",
                        "--method", "org.freedesktop.DBus.Properties.GetAll",
                        "org.kde.kdeconnect.device.notifications.notification",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    s_prop, _ = await p_prop.communicate()
                    prop_str = s_prop.decode().strip()

                    text_m = re.search(r"'text':\s*<'(.*?)'>", prop_str)
                    ticker_m = re.search(r"'ticker':\s*<'(.*?)'>", prop_str)
                    title_m = re.search(r"'title':\s*<'(.*?)'>", prop_str)

                    text = text_m.group(1) if text_m else ""
                    ticker = ticker_m.group(1) if ticker_m else ""
                    title = title_m.group(1) if title_m else ""

                    notif_content = f"{title} {text} {ticker}".strip()
                    app_m = re.search(r"'appName':\s*<'(.*?)'>", prop_str)
                    app_name = app_m.group(1).lower() if app_m else ""

                    extract_res = await extract_otp_from_text(notif_content)
                    if extract_res.otp:
                        if norm_expected_ref and extract_res.ref and extract_res.ref.upper() != norm_expected_ref:
                            continue
                        logger.info(f"KDE Connect D-Bus intercepted OTP: {extract_res.otp} (Ref: {extract_res.ref})")
                        payload = OTPPayload(
                            source=OTPSource.KDE_CONNECT,
                            otp=extract_res.otp,
                            ref=extract_res.ref,
                            sender=app_name or "kdeconnect-dbus"
                        )
                        await event_bus.publish_otp(payload)
                        return payload
        except Exception as e:
            logger.debug(f"KDE Connect D-Bus check error: {e}")

        # 3. Query recent systemd user journal packets (captures live KDE Connect and GSConnect packets)
        #    U3 (KDE-RCA-005): anchor the scan to the moment the OTP was requested (arrival-time
        #    semantics) instead of a fixed rolling window, so a late/Doze-delayed push is captured.
        try:
            since_arg = f"@{max(1, since_ms // 1000) - 5}" if since_ms else "-5 minutes"
            proc_j = await asyncio.create_subprocess_exec(
                "journalctl", "--user", "--since", since_arg, "--no-pager", "-o", "cat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_j, _ = await proc_j.communicate()
            if stdout_j:
                j_text = stdout_j.decode()
                packets = self._extract_json_packets(j_text)
                
                candidate_payload: Optional[OTPPayload] = None

                # Process packets in reverse chronological order (newest first)
                for pkt in reversed(packets):
                    p_type = pkt.get("type")
                    b = pkt.get("body", {})

                    # Path A: Native KDE Connect SMS packet
                    if p_type == "kdeconnect.sms.messages":
                        messages = b.get("messages", [])
                        for msg in messages:
                            body = msg.get("body", "")
                            msg_date = msg.get("date", 0)
                            addresses = msg.get("addresses", [{}])
                            sender = (addresses[0].get("address") if addresses else "") or "KSS-OTP"

                            extract_res = await extract_otp_from_text(body)
                            if not extract_res.otp:
                                continue

                            # KDE-RCA-005: a definitive Ref Code match is authoritative and must
                            # bypass the phone-clock age guard (a delayed/Doze push keeps an old
                            # `date` even though it arrived at this host only seconds ago).
                            ref_is_definitive = bool(
                                norm_expected_ref and extract_res.ref
                                and extract_res.ref.upper() == norm_expected_ref
                            )
                            if not ref_is_definitive and msg_date and (current_time_ms - msg_date > grace_ms):
                                continue

                            payload = OTPPayload(
                                source=OTPSource.KDE_CONNECT,
                                otp=extract_res.otp,
                                ref=extract_res.ref,
                                sender=sender
                            )
                            if norm_expected_ref:
                                if ref_is_definitive:
                                    logger.info(f"Journal: Matched expected Ref Code '{norm_expected_ref}' from SMS!")
                                    await event_bus.publish_otp(payload)
                                    return payload
                                elif not candidate_payload and not extract_res.ref:
                                    candidate_payload = payload
                            else:
                                logger.info(f"Journal: Extracted SMS OTP: {payload.masked_otp} (Ref: {payload.ref})")
                                await event_bus.publish_otp(payload)
                                return payload

                    # Path B: Standard Notification packet
                    elif p_type == "kdeconnect.notification":
                        app_name = b.get("appName", "").lower()
                        title = b.get("title", "")
                        text = b.get("text", "")
                        ticker = b.get("ticker", "")
                        notif_content = f"{title} {text} {ticker}".strip()

                        extract_res = await extract_otp_from_text(notif_content)
                        if extract_res.otp:
                            payload = OTPPayload(
                                source=OTPSource.KDE_CONNECT,
                                otp=extract_res.otp,
                                ref=extract_res.ref,
                                sender=app_name or title
                            )
                            if norm_expected_ref:
                                if extract_res.ref and extract_res.ref.upper() == norm_expected_ref:
                                    logger.info(f"Journal: Matched expected Ref Code '{norm_expected_ref}' from Notification!")
                                    await event_bus.publish_otp(payload)
                                    return payload
                                elif not candidate_payload and not extract_res.ref:
                                    candidate_payload = payload
                            else:
                                logger.info(f"Journal: Extracted Notification OTP: {payload.masked_otp} (Ref: {payload.ref})")
                                await event_bus.publish_otp(payload)
                                return payload

                if candidate_payload and not norm_expected_ref:
                    logger.info(f"Journal: Using recent SMS OTP candidate: {candidate_payload.masked_otp} (Ref: {candidate_payload.ref})")
                    await event_bus.publish_otp(candidate_payload)
                    return candidate_payload

        except Exception as e:
            logger.debug(f"Error checking journalctl for OTP: {e}")

        # 4. Fallback: GSConnect real-time cache log (~/.cache/gsconnect/incoming_notifications.jsonl)
        cache_log = os.path.expanduser("~/.cache/gsconnect/incoming_notifications.jsonl")
        if os.path.exists(cache_log):
            try:
                with open(cache_log, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines[-30:]):
                    try:
                        record = json.loads(line)

                        app_name = record.get("appName", "").lower()
                        title = record.get("title", "")
                        text = record.get("text", "")
                        ticker = record.get("ticker", "")
                        notif_content = f"{title} {text} {ticker}".strip()

                        extract_res = await extract_otp_from_text(notif_content)
                        if not extract_res.otp:
                            continue

                        # KDE-RCA-005: GSConnect stores the *phone's SMS creation time* in `time`
                        # — NOT the arrival time at this host. A delayed push (Android Doze / link
                        # flapping) can therefore look minutes-old the instant it lands. Apply the
                        # age guard ONLY when we cannot positively match the expected Ref Code.
                        ref_is_definitive = bool(
                            norm_expected_ref and extract_res.ref
                            and extract_res.ref.upper() == norm_expected_ref
                        )
                        rec_time = record.get("time", 0)
                        if not ref_is_definitive and rec_time and (current_time_ms - rec_time > grace_ms):
                            continue

                        if norm_expected_ref:
                            if ref_is_definitive:
                                logger.info(f"GSConnect Cache: Matched expected Ref Code '{norm_expected_ref}'!")
                                return await self.process_incoming_notification(
                                    title=title or "KSS-OTP",
                                    text=f"{text} {ticker}".strip(),
                                    sender=app_name or "GSConnect-SMS"
                                )
                        else:
                            return await self.process_incoming_notification(
                                title=title or "KSS-OTP",
                                text=f"{text} {ticker}".strip(),
                                sender=app_name or "GSConnect-SMS"
                            )
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Error reading GSConnect cache log: {e}")

        return None

    async def get_network_routes(self) -> dict[str, Any]:
        """
        Dynamically inspects active network transport routes for Mi 10T:
        - Wi-Fi (Home Local Subnet 192.168.1.x)
        - Tailscale VPN (Mobile 4G/5G 100.x.x.x)
        """
        wifi_status = "OFFLINE"
        tailscale_status = "OFFLINE"
        active_route = "DISCONNECTED"
        route_label = "❌ Disconnected"
        remote_ip = "-"

        # 1. Inspect live established sockets for KDE Connect (port 1716)
        try:
            proc_ss = await asyncio.create_subprocess_exec(
                "ss", "-tnp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_ss, _ = await proc_ss.communicate()
            if stdout_ss:
                for line in stdout_ss.decode().splitlines():
                    if "1716" in line and "kdeconnectd" in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            local_a = parts[3]
                            remote_a = parts[4]
                            clean_remote = remote_a.replace("[::ffff:", "").replace("]", "")
                            clean_local = local_a.replace("[::ffff:", "").replace("]", "")
                            remote_ip_only = clean_remote.split(":")[0] if ":" in clean_remote else clean_remote

                            # Ignore local loopback or local self-connections (e.g. gjs/gsconnect talking to kdeconnectd on 192.168.1.53)
                            if remote_ip_only in ("127.0.0.1", "::1", "192.168.1.53"):
                                continue

                            if remote_ip_only.startswith("100."):
                                tailscale_status = "ACTIVE"
                                active_route = "TAILSCALE"
                                route_label = "📱 Mobile (Tailscale)"
                                remote_ip = clean_remote
                            elif remote_ip_only.startswith("192.168."):
                                wifi_status = "ACTIVE"
                                active_route = "WIFI"
                                route_label = "📶 Home Wi-Fi"
                                remote_ip = clean_remote
        except Exception as e:
            logger.debug(f"ss inspection error: {e}")

        # 2. Inspect Tailscale peer status for Mi 10T (HostName: M2007J3SY or DNSName: mobile1)
        try:
            proc_ts = await asyncio.create_subprocess_exec(
                "tailscale", "status", "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_ts, _ = await proc_ts.communicate()
            if stdout_ts:
                ts_data = json.loads(stdout_ts.decode())
                peers = ts_data.get("Peer", {})
                for p_key, peer in peers.items():
                    h_name = peer.get("HostName", "")
                    d_name = peer.get("DNSName", "")
                    if "M2007J3SY" in h_name or "mobile1" in d_name:
                        is_online = peer.get("Online", False)
                        cur_addr = peer.get("CurAddr", "")
                        ts_ips = peer.get("TailscaleIPs", ["100.119.166.62"])

                        if is_online:
                            if tailscale_status != "ACTIVE":
                                tailscale_status = "STANDBY"

                            # If Tailscale sees direct local LAN address (192.168.1.x), phone Wi-Fi is currently connected to home network
                            if cur_addr.startswith("192.168.1."):
                                if wifi_status != "ACTIVE":
                                    wifi_status = "ACTIVE"
                                if active_route == "DISCONNECTED":
                                    active_route = "WIFI"
                                    route_label = "📶 Home Wi-Fi"
                                    remote_ip = cur_addr.split(":")[0]
                            else:
                                # Not on local Wi-Fi subnet
                                if wifi_status != "ACTIVE":
                                    wifi_status = "OFFLINE"
                                if active_route == "DISCONNECTED":
                                    active_route = "TAILSCALE"
                                    route_label = "📱 Mobile (Tailscale)"
                                    remote_ip = ts_ips[0] if ts_ips else "100.119.166.62"
                        else:
                            tailscale_status = "OFFLINE"
        except Exception as e:
            logger.debug(f"tailscale status inspection error: {e}")

        # Fallback: If device is reachable via kdeconnect-cli but route wasn't matched above
        if active_route == "DISCONNECTED":
            try:
                proc_cli = await asyncio.create_subprocess_exec(
                    "kdeconnect-cli", "-a", "--id-only",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_cli, _ = await proc_cli.communicate()
                if self.device_id in stdout_cli.decode():
                    active_route = "WIFI"
                    route_label = "📶 Connected"
                    wifi_status = "ACTIVE"
            except Exception:
                pass

        return {
            "active_route": active_route,
            "route_label": route_label,
            "remote_ip": remote_ip,
            "wifi": wifi_status,
            "tailscale": tailscale_status
        }


# Global singleton
kdeconnect_service = KdeConnectService()

