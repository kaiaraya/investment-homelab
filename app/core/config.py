from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Investment Homelab Gateway"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./investment_homelab.db"
    CLICK2WIN_DATABASE_URL: str = "sqlite+aiosqlite:///./investment_homelab_click2win.db"
    
    # Secret Key for LINE and External Webhook protection
    HOMELAB_SECRET_KEY: str = "change-me-set-in-dotenv"
    
    # LINE Messaging API Credentials
    LINE_CHANNEL_SECRET: str = "mock_line_channel_secret"
    LINE_CHANNEL_ACCESS_TOKEN: str = "mock_line_channel_token"
    LINE_ADMIN_USER_ID: Optional[str] = None
    LINE_SIMULATION_MODE: bool = True

    # --- LINE Group OTP Relay (2026-10-08: replaces KDE Connect as primary OTP channel) ---
    # groupId of the "a14s homelab" LINE group. When set, push_message() targets the
    # group (push `to` accepts a groupId) instead of falling back to broadcast.
    # Auto-captured by the webhook on the first group message (webhook_line.py).
    LINE_GROUP_ID: Optional[str] = None
    # Public webhook URL that the cloudflared tunnel exposes (diagnostics / readiness).
    LINE_PUBLIC_WEBHOOK_URL: str = "https://line.a14s.dev/api/v1/webhook/line"
    # Master switch for the LINE-based OTP readiness gate (Invariant 9 — LINE variant).
    LINE_OTP_RELAY_ENABLED: bool = True
    
    # Pre-trade Risk & Guard Configuration
    MAX_ORDER_VALUE_THB: float = 1_000_000.0
    ORDER_IDEMPOTENCY_WINDOW_SEC: int = 10
    
    # Optional Gemini / LLM API key
    GEMINI_API_KEY: Optional[str] = None

    # DeepSeek LLM (OpenAI-compatible) — primary AI interpreter for Signal/OTP agents
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    
    # Krungsri Securities & Browser Automation Configuration
    KRUNGSRI_USERNAME: str = ""
    KRUNGSRI_PASSWORD: str = ""
    KRUNGSRI_LOGIN_URL: str = "https://www.krungsrisecurities.com/th/main/default.aspx"
    PLAYWRIGHT_HEADLESS: bool = False
    PLAYWRIGHT_CHROME_EXECUTABLE: str = "/usr/bin/google-chrome"
    OTP_TIMEOUT_SECONDS: int = 180
    # KDE-RCA-005: max age (seconds) of a mobile notification still accepted as an OTP
    # candidate when we CANNOT positively match the broker Ref Code. Android Doze /
    # KDE Connect link flapping can delay a push well past the phone-clock `date`, so a
    # tight 5-minute guard silently discards freshly-arrived OTPs. A definitive Ref Code
    # match always bypasses this guard entirely.
    OTP_STALENESS_GRACE_SECONDS: int = 600
    SESSION_STATE_PATH: str = "data/session_state.json"
    SESSION_HEARTBEAT_INTERVAL: int = 1800  # Sentinel check interval: 30 minutes (1800s)
    TRADEMAN_URL: str = "https://trademan.in.th"
    TRADEMAN_PORTFOLIO_URL: str = "https://trademan.in.th/Portfolio"
    TRADEMAN_ACCOUNT_NO_CASH: str = "3024952"
    TRADEMAN_ACCOUNT_NO_MARGIN: str = "3024959"
    KRUNGSRI_PIN: str = ""  # set in .env
    TRADING_PIN: str = ""  # set in .env

    # Target Trading Platform Switch ("CLICK2WIN" for Settrade sandbox or "TRADEMAN" for Krungsri live)
    TRADING_PLATFORM: str = "CLICK2WIN"

    # Settrade Click2Win Credentials & Configuration (Web Scraping Legacy)
    CLICK2WIN_URL: str = "https://click2win.settrade.com"
    CLICK2WIN_USERNAME: str = ""
    CLICK2WIN_PASSWORD: str = ""
    CLICK2WIN_PIN: str = ""
    CLICK2WIN_ACCOUNT_NO_EQUITY: str = "CW32_E_7338419"
    CLICK2WIN_ACCOUNT_NO_DERIVATIVES: str = "CW32_D_7338419"
    CLICK2WIN_SESSION_PATH: str = "data/click2win_session.json"

    # Settrade Open API Configuration (Direct Machine-to-Machine Sandbox / Live API)
    SETTRADE_APP_ID: str = ""
    SETTRADE_APP_SECRET: str = ""
    SETTRADE_BROKER_ID: str = "SANDBOX"
    SETTRADE_APP_CODE: str = "SANDBOX"
    SETTRADE_ACCOUNT_NO_EQUITY: str = ""
    SETTRADE_ACCOUNT_NO_DERIVATIVES: str = ""
    SETTRADE_PIN: str = "000000"

    # Liberator Securities Configuration
    LIBERATOR_USERNAME: str = ""
    LIBERATOR_PASSWORD: str = ""
    LIBERATOR_PIN: str = ""
    LIBERATOR_LOGIN_URL: str = "https://webtrade.liberator.co.th/login"
    LIBERATOR_SESSION_PATH: str = "data/liberator_session.json"

    # Phase 3 & Policy Engine Configuration (4 Centers & Forward-Compatible Safety)
    DRY_RUN_MODE: bool = True  # Safety mode: prepares and fills orders but does not submit final PIN
    TRADING_MODE: str = "TEST"  # "TEST" (Virtual TradeMan Simulator) or "LIVE" (TradeMan Real Orders)
    LIVE_ORDER_VALUE_LIMIT_THB: float = 50_000.0  # Guardrail limit per order in LIVE mode
    CARD_TTL_SECONDS: int = 180  # Card expiration window (3 minutes)
    UNANSWERED_ACTION_POLICY: str = "HOLD"  # Options: "HOLD", "URGENT_PING", "AUTO_EXECUTE_CUTLOSS", "AI_AGENT_DECIDE"
    UNANSWERED_TIMEOUT_SECONDS: int = 180  # Timeout for interactive LINE card response
    PRICE_NEGOTIATION_POLICY: str = "PROPOSE_LINE"  # Options: "PROPOSE_LINE", "AUTO_ADJUST", "CANCEL_ORDER", "AI_AGENT_DECIDE"
    ABNORMAL_PRICE_CHANGE_THRESHOLD: float = 3.0  # Alert if %Change vs prior day close >= +3% or <= -3%
    PORTFOLIO_OVERVIEW_TIME: str = "10:15"
    ALERT_CENTER_START: str = "10:30"
    ALERT_CENTER_END: str = "17:30"
    PRICE_NEGOTIATION_ROUNDS: list[str] = ["11:00", "15:30"]
    EOD_REPORT_TIME: str = "16:35"

    # Scheduler and Notification Control
    ENABLE_INTRADAY_SCHEDULER: bool = False  # Master switch for the intraday market-regime scheduler (8 regimes; formerly Phase 3)
    # Slim-gateway switches (2026-10-08): heavy background daemons default OFF so the
    # gateway boots lean (webhook + API + DB + session sentinel only). Flip to True only
    # when the corresponding Pillar is actually under test.
    ENABLE_ACTION_EXIT_DISPATCHER: bool = False  # Tactical Action-Exit daemon + 09:45 pre-flight
    ENABLE_AGENTIC_ORCHESTRATOR: bool = False  # PT-MRO MasterOrchestrator background loop
    ENABLE_CLICK2WIN_POLLING: bool = False  # Master switch for Click2Win Favourite Polling Sentinel Worker (Pillar 2)
    ENABLE_PROGRESS_NOTIFICATIONS: bool = False  # Control 1-line progress updates (⏳/✅) to LINE
    KDECONNECT_DEVICE_ID: str = "9507a3fd53f848da9135ebe6253db18a"
    ENABLE_HITL_LIVE_GATE: bool = True  # Require 1-click confirmation at /console + KDE Connect mobile alert for real money
    ENABLE_HITL_SANDBOX_GATE: bool = True  # Allow testing HITL Gate on Click2Win sandbox without real money risk
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
