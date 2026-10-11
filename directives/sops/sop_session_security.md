# Standard Operating Procedure (SOP): Session Sentinel & Security Management
**Document ID:** `SOP-001`  
**Governing Sub-Agent:** `SessionSentinelAgent`  
**Version:** 1.0  
**Effective Date:** 2026-10-03  

---

## 1. Objective & Scope
Define the standard procedures for managing authentication, 2FA SMS OTP resolution, headless browser lifecycle, and real-time session health across Krungsri Securities (TradeMan), Settrade Click2Win (Sandbox), and Settrade Open API.

---

## 2. Input & Output Contracts

### Inputs:
- `broker_name`: Target broker (`'krungsri'`, `'click2win'`).
- `force_refresh`: Boolean flag to force a fresh Chromium browser context.
- `manual_otp`: Optional 6-digit SMS OTP string provided via CLI/API.

### Outputs:
- `health_status`: Dictionary containing:
  - `browser_connected`: bool
  - `dom_ready`: bool
  - `active_broker`: str
  - `openapi_token_valid`: bool
  - `last_heartbeat_timestamp`: ISO 8601 string
- `login_result`: Status enum (`'SUCCESS'`, `'WAITING_OTP'`, `'FAILED'`).

---

## 3. Step-by-Step Standard Operating Procedure

### Step 3.1: Pre-Flight Health Inspection
1. Call `session_get_health`.
2. Inspect if browser context is active and DOM matches active market view:
   - For Krungsri TradeMan: Element `div.trademan-container` or `div.widget-trading-view`.
   - For Click2Win: Element `div.bg-color-account-info-group` or `span:text('CW32_')`.
3. Check Settrade Open API token expiry timestamp. If expired (< 5 mins remaining), trigger SDK re-auth.

### Step 3.2: Automated Login & Popup Mitigation
1. Launch Chromium context via Playwright (`headless=False` or `headless=True` per environment).
2. Navigate to broker portal:
   - Krungsri: `https://www.krungsrisecurities.com/` -> SSO -> `https://trademan.in.th/`
   - Click2Win: `https://click2win.settrade.com/`
3. Auto-fill credentials from environment (`.env`).
4. Dismiss any promotional banners, modal overlays (`.ReactModal__Overlay`), or maintenance dialogs immediately.

### Step 3.3: 2FA SMS OTP Interception & Resolution
1. When Krungsri prompts for SMS OTP:
   - Extract `Reference Code` (e.g. `Ref: ABCD`) from the web DOM.
   - **Tier 1 (Automated D-Bus)**: Listen for incoming SMS via KDE Connect service (`app/services/kdeconnect_service.py`).
   - Extract 6-digit OTP using regex (`\b\d{6}\b`).
   - **Tier 2 (LINE Mobile Fallback)**: If KDE Connect does not deliver OTP within 20 seconds, send LINE notification with Reference Code to user.
   - Wait up to 180 seconds for OTP input via Webhook or CLI.
2. Fill OTP digits into the input field and submit.
3. Confirm arrival at the main trading dashboard.

### Step 3.4: Heartbeat Sentinel Loop
1. Every 5 minutes during market hours (09:30 - 16:35):
   - Ping the page DOM to ensure user session has not timed out.
   - Verify WebSocket connection status.
   - If session is lost, attempt silent reconnection before escalating.

### Step 3.5: End-of-Day Safe Logout
1. At 16:35 (Market Close):
   - Click broker Logout button.
   - Flush cookies and close Chromium context.
   - Release Open API WebSocket streams.

---

## 4. Guardrails & Safety Constraints
- **Never store plaintext OTPs** in log files.
- Max OTP retry attempts: **3**. If failed 3 times, abort login and trigger KDE Connect + LINE alert to avoid account lockout.
- Always cleanly terminate dangling Chromium processes upon shutdown.

---

## 5. Definition of Done (DoD)
- Both Browser DOM and Open API return valid alive status in `session_get_health`.
- Anomaly capture and screenshots are saved to `data/screenshots/` if any step fails.
