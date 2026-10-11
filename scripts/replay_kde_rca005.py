"""
KDE-RCA-005 real-data replay — PROOF-BY-ARTIFACT.

Replays the *actual* historical Krungsri SMS-OTP that the incident RCA captured
(phone-created 15:53:50.765, arrived on the NUC at 16:01:29 — ~7m39s late) through the
FIXED reader, using ONLY read-only probes (kdeconnect-cli --list-notifications, gdbus Get,
journalctl). No login, no OTP request to the broker, no order, no SMS send.

Before the fix: the packet's phone-clock `date` (1791276830765) was >300_000ms behind
`now`, so it was discarded as "stale" and the journal scan used a 3-minute window.
"""
import asyncio
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.services.kdeconnect_service import KdeConnectService

INCIDENT_SMS_EPOCH_MS = 1791276830765  # 2026-10-06 15:53:50.765 — phone SMS creation time
INCIDENT_REF = "VJKR"
INCIDENT_OTP = "749455"


async def main() -> None:
    svc = KdeConnectService()
    print(f"device_id            : {svc.device_id}")
    print(f"kdeconnectd reachable: {await svc.is_device_reachable()}")
    print(f"gsconnect connected  : {await svc._gsconnect_connected()}")

    t0 = time.time()
    payload = await svc.poll_active_notifications(
        expected_ref=INCIDENT_REF,
        since_ms=INCIDENT_SMS_EPOCH_MS,
    )
    elapsed = time.time() - t0
    print(f"elapsed              : {elapsed:.2f}s")

    if payload:
        print(
            f"RESULT otp={payload.otp} ref={payload.ref} "
            f"source={payload.source} sender={payload.sender}"
        )
    else:
        print("RESULT: None (no capture)")

    ok = bool(payload and payload.otp == INCIDENT_OTP and payload.ref == INCIDENT_REF)
    print("VERDICT:", "PASS - real delayed OTP captured" if ok else "FAIL - not captured")


if __name__ == "__main__":
    asyncio.run(main())
