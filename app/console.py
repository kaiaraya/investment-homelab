CONSOLE_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Investment Homelab - Operations & Capability Cockpit</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #080b11;
            --bg-secondary: #0f1420;
            --bg-card: rgba(16, 22, 36, 0.88);
            --bg-card-hover: rgba(22, 30, 48, 0.95);
            --accent-blue: #3b82f6;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-emerald: #059669;
            --accent-red: #ef4444;
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
            --accent-violet: #7c3aed;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(59, 130, 246, 0.35);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 24px 28px 60px;
            background-image: 
                radial-gradient(circle at 12% 10%, rgba(59, 130, 246, 0.12) 0%, transparent 45%),
                radial-gradient(circle at 88% 85%, rgba(139, 92, 246, 0.10) 0%, transparent 45%),
                radial-gradient(circle at 50% 50%, rgba(6, 182, 212, 0.04) 0%, transparent 60%);
            background-attachment: fixed;
        }

        .container { max-width: 1480px; margin: 0 auto; }

        /* Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 22px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .logo-area h1 {
            font-size: 23px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #60a5fa 10%, #a78bfa 50%, #38bdf8 90%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .logo-area p {
            color: var(--text-secondary);
            font-size: 13px;
            margin-top: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .badge-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 11px;
            border-radius: 9999px;
            font-size: 11.5px;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            font-family: 'JetBrains Mono', monospace;
        }

        .badge-green { color: #34d399; border-color: rgba(52, 211, 153, 0.3); background: rgba(16, 185, 129, 0.12); }
        .badge-blue { color: #60a5fa; border-color: rgba(96, 165, 250, 0.3); background: rgba(59, 130, 246, 0.12); }
        .badge-purple { color: #c084fc; border-color: rgba(192, 132, 252, 0.3); background: rgba(139, 92, 246, 0.12); }
        .badge-cyan { color: #22d3ee; border-color: rgba(34, 211, 238, 0.3); background: rgba(6, 182, 212, 0.12); }
        .badge-amber { color: #fbbf24; border-color: rgba(251, 191, 36, 0.3); background: rgba(245, 158, 11, 0.12); }

        .pulse-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background-color: #10b981; box-shadow: 0 0 8px #10b981;
            animation: pulse 2s infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .btn-spinner {
            display: inline-block;
            width: 13px;
            height: 13px;
            border: 2px solid rgba(255, 255, 255, 0.35);
            border-top-color: #ffffff;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            vertical-align: middle;
            margin-right: 6px;
        }

        .btn-locked, button:disabled {
            opacity: 0.65 !important;
            cursor: not-allowed !important;
            pointer-events: none !important;
        }

        /* Master Connect All Button */
        .btn-master-connect {
            background: linear-gradient(135deg, #2563eb, #7c3aed);
            color: #ffffff;
            font-weight: 700;
            font-size: 13.5px;
            padding: 9px 18px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: 0 4px 20px rgba(59, 130, 246, 0.35);
            cursor: pointer;
            transition: all 0.25s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn-master-connect:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(124, 58, 237, 0.45);
            background: linear-gradient(135deg, #1d4ed8, #6d28d9);
        }

        /* Grid Layout */
        .grid {
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 18px;
            margin-bottom: 22px;
        }

        .grid-brokers {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 22px;
        }

        @media (max-width: 1200px) {
            .grid-brokers { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 600px) {
            .grid-brokers { grid-template-columns: 1fr; }
        }

        .price-flash-up {
            animation: flashGreen 0.9s ease;
        }

        .price-flash-down {
            animation: flashRed 0.9s ease;
        }

        @keyframes flashGreen {
            0% { background-color: rgba(16, 185, 129, 0.45); }
            100% { background-color: transparent; }
        }

        @keyframes flashRed {
            0% { background-color: rgba(239, 68, 68, 0.45); }
            100% { background-color: transparent; }
        }

        .col-3 { grid-column: span 3; }
        .col-4 { grid-column: span 4; }
        .col-6 { grid-column: span 6; }
        .col-8 { grid-column: span 8; }
        .col-12 { grid-column: span 12; }

        @media (max-width: 1200px) {
            .col-3 { grid-column: span 6; }
            .col-4 { grid-column: span 6; }
        }

        @media (max-width: 800px) {
            .col-3, .col-4, .col-6, .col-8 { grid-column: span 12; }
        }

        /* Cards */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 18px 20px;
            backdrop-filter: blur(16px);
            transition: border-color 0.2s, box-shadow 0.2s;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            position: relative;
        }

        .card:hover {
            border-color: rgba(255, 255, 255, 0.16);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            gap: 8px;
        }

        .card-title {
            font-size: 14px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
            letter-spacing: -0.2px;
        }

        .card-tag {
            font-size: 10.5px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 2px 7px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
        }

        /* Status Pills */
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.2px;
        }

        .status-READY, .status-LOGGED_IN, .status-ONLINE, .status-ACTIVE, .status-CONNECTED, .status-FILLED, .status-WIFI, .status-AUTHENTICATED, .status-SESSION_SAVED {
            background: rgba(16, 185, 129, 0.16);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }

        .status-TAILSCALE {
            background: rgba(139, 92, 246, 0.16);
            color: #c084fc;
            border: 1px solid rgba(139, 92, 246, 0.35);
        }

        .status-STANDBY {
            background: rgba(148, 163, 184, 0.12);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.25);
        }

        .status-AWAITING_OTP, .status-WAITING, .status-DEGRADED, .status-PENDING {
            background: rgba(245, 158, 11, 0.16);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.35);
            animation: pulse-border 1.5s infinite;
        }

        .status-DISCONNECTED, .status-OFFLINE, .status-FAILED, .status-REJECTED {
            background: rgba(239, 68, 68, 0.16);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.35);
        }

        @keyframes pulse-border {
            0%, 100% { border-color: rgba(245, 158, 11, 0.6); }
            50% { border-color: rgba(245, 158, 11, 0.2); }
        }

        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 7px 13px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            border: none;
            transition: all 0.2s ease;
            text-decoration: none;
            font-family: inherit;
        }

        .btn-primary { background: linear-gradient(135deg, #2563eb, #3b82f6); color: white; }
        .btn-primary:hover { background: linear-gradient(135deg, #1d4ed8, #2563eb); transform: translateY(-1px); }

        .btn-success { background: linear-gradient(135deg, #059669, #10b981); color: white; }
        .btn-success:hover { background: linear-gradient(135deg, #047857, #059669); transform: translateY(-1px); }

        .btn-danger { background: linear-gradient(135deg, #dc2626, #ef4444); color: white; }
        .btn-danger:hover { background: linear-gradient(135deg, #b91c1c, #dc2626); transform: translateY(-1px); }

        .btn-amber { background: linear-gradient(135deg, #d97706, #f59e0b); color: white; }
        .btn-amber:hover { background: linear-gradient(135deg, #b45309, #d97706); transform: translateY(-1px); }

        .btn-purple { background: linear-gradient(135deg, #7c3aed, #8b5cf6); color: white; }
        .btn-purple:hover { background: linear-gradient(135deg, #6d28d9, #7c3aed); transform: translateY(-1px); }

        .btn-secondary { background: rgba(255, 255, 255, 0.07); color: var(--text-primary); border: 1px solid var(--border-color); }
        .btn-secondary:hover { background: rgba(255, 255, 255, 0.12); border-color: rgba(255, 255, 255, 0.18); }

        .btn-sm { padding: 5px 9px; font-size: 11px; border-radius: 6px; }

        /* Form Inputs */
        label { display: block; font-size: 11.5px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px; }

        input, select, textarea {
            width: 100%;
            padding: 8px 12px;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--border-color);
            border-radius: 7px;
            color: var(--text-primary);
            font-size: 12.5px;
            font-family: inherit;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        input:focus, select:focus, textarea:focus {
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
        }

        /* HITL OTP Banner */
        .hitl-banner {
            display: none;
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(245, 158, 11, 0.15));
            border: 2px solid #f59e0b;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 22px;
            animation: glow 2s infinite alternate;
        }

        .hitl-banner.active { display: block; }

        @keyframes glow {
            from { box-shadow: 0 0 10px rgba(245, 158, 11, 0.2); }
            to { box-shadow: 0 0 24px rgba(245, 158, 11, 0.5); }
        }

        /* Sentinel Cards Info Grid */
        .sentinel-info {
            display: flex;
            flex-direction: column;
            gap: 6px;
            font-size: 11.5px;
            margin: 10px 0 14px;
            background: rgba(0, 0, 0, 0.2);
            padding: 10px 12px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }

        .sentinel-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .sentinel-label { color: var(--text-muted); font-size: 11px; }
        .sentinel-val { color: var(--text-primary); font-family: 'JetBrains Mono', monospace; font-size: 11px; }

        /* Tables */
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th {
            text-align: left;
            padding: 9px 11px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }
        td {
            padding: 9px 11px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            color: var(--text-primary);
        }
        tr:hover td { background: rgba(255, 255, 255, 0.02); }

        /* Terminal Console */
        .console-output {
            background: #04060a;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11.5px;
            color: #cbd5e1;
            height: 220px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
        }

        /* Toast */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            padding: 12px 18px;
            border-radius: 10px;
            font-size: 12.5px;
            font-weight: 600;
            background: rgba(18, 24, 38, 0.95);
            border: 1px solid var(--border-color);
            color: white;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6);
            display: flex;
            align-items: center;
            gap: 10px;
            z-index: 2000;
            opacity: 0;
            transform: translateY(12px);
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: none;
        }
        .toast.show { opacity: 1; transform: translateY(0); }

        /* Watchlist Tabs & Multi-Account Cockpit Styles */
        .fav-tabs {
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 16px;
            overflow-x: auto;
            padding-bottom: 8px;
        }
        .fav-tab-btn {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            white-space: nowrap;
        }
        .fav-tab-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
        }
        .fav-tab-btn.active {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.25), rgba(6, 182, 212, 0.25));
            border-color: #38bdf8;
            color: #f8fafc;
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);
        }
        .fav-tab-badge {
            background: rgba(255, 255, 255, 0.1);
            padding: 2px 7px;
            border-radius: 9999px;
            font-size: 11px;
            font-family: 'JetBrains Mono', monospace;
        }
        .tick-flash-up {
            animation: flashGreen 1.2s ease-out;
        }
        .tick-flash-down {
            animation: flashRed 1.2s ease-out;
        }
        @keyframes flashGreen {
            0% { background-color: rgba(16, 185, 129, 0.45); color: #34d399; }
            100% { background-color: transparent; }
        }
        @keyframes flashRed {
            0% { background-color: rgba(239, 68, 68, 0.45); color: #f87171; }
            100% { background-color: transparent; }
        }
        .capacity-bar {
            width: 120px;
            height: 6px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
            overflow: hidden;
            display: inline-block;
            vertical-align: middle;
            margin-left: 6px;
        }
        .capacity-fill {
            height: 100%;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            border-radius: 3px;
            transition: width 0.3s ease;
        }

        /* Master Readiness Checklist Banner */
        .readiness-banner {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(16, 24, 39, 0.92));
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 22px;
            box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
            backdrop-filter: blur(16px);
            transition: border-color 0.3s ease;
        }
        .readiness-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1.25fr;
            gap: 14px;
            align-items: center;
        }
        @media (max-width: 960px) {
            .readiness-grid { grid-template-columns: 1fr; }
        }
        .readiness-step {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            transition: all 0.2s ease;
        }
        .readiness-step.step-success {
            background: rgba(16, 185, 129, 0.08);
            border-color: rgba(16, 185, 129, 0.3);
        }
        .readiness-step.step-warning {
            background: rgba(245, 158, 11, 0.08);
            border-color: rgba(245, 158, 11, 0.3);
        }
        .readiness-icon {
            font-size: 22px;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.05);
            flex-shrink: 0;
        }
        .readiness-details {
            flex: 1;
            min-width: 0;
        }
        .readiness-title {
            font-size: 13px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .readiness-subtitle {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 3px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        /* CLI Test Runner Panel */
        .cli-runner-card {
            background: var(--bg-card);
            border: 1px solid rgba(139, 92, 246, 0.3);
            border-radius: 14px;
            padding: 18px 20px;
            margin-bottom: 22px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }
        .cli-cmd-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 8px 12px;
            gap: 12px;
            transition: all 0.15s ease;
        }
        .cli-cmd-row:hover {
            border-color: rgba(139, 92, 246, 0.45);
            background: rgba(139, 92, 246, 0.06);
        }
        .cli-cmd-text {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11.5px;
            color: #38bdf8;
            white-space: nowrap;
            overflow-x: auto;
        }
        .cli-cmd-label {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 600;
            margin-bottom: 2px;
        }
    </style>
</head>
<body>

<div class="container">
    <!-- Header -->
    <header>
        <div class="logo-area">
            <h1>⚡ Investment Homelab - Operations Cockpit</h1>
            <p>
                <span>6-Pillars Modular Architecture</span>
                <span>•</span>
                <span style="color: #60a5fa;">Settrade Open API (MQTT Ticks)</span>
                <span>•</span>
                <span style="color: #a78bfa;">Playwright Runbooks</span>
                <span>•</span>
                <span style="color: #34d399;">Sandbox Verified</span>
            </p>
        </div>

        <div class="header-actions">
            <div class="badge-bar">
                <div class="badge badge-green">
                    <div class="pulse-dot"></div> Gateway Online
                </div>
                <div class="badge badge-cyan" id="sseBadge" title="Server-Sent Events Market Stream">
                    <div class="pulse-dot"></div> SSE Live Stream
                </div>
                <div class="badge badge-purple" title="FastMCP Remote Server">
                    🛡️ Remote MCP (/sse)
                </div>
                <div class="badge badge-blue">
                    📦 SQLite Ready
                </div>
                <div class="badge badge-cyan">
                    🌐 100.88.217.33
                </div>
                <a href="/docs" target="_blank" class="btn btn-secondary btn-sm">📖 Docs</a>
            </div>

            <div style="display: flex; gap: 8px; align-items: center;">
                <button class="btn btn-danger" id="btnEmergencyPanic" onclick="triggerKillSwitch()" style="background: linear-gradient(135deg, #ef4444, #b91c1c); color: white; font-weight: 700; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);">
                    🚨 PANIC KILL SWITCH
                </button>
                <button class="btn btn-secondary btn-sm" id="btnResetKillSwitch" onclick="resetKillSwitch()" style="display: none; border-color: #10b981; color: #34d399;">
                    ✅ Reset Panic
                </button>
                <button class="btn btn-secondary" id="btnReloadGateway" onclick="reloadGateway()" title="Restart the uvicorn gateway process in-place (os.execv)" style="border-color: #06b6d4; color: #22d3ee; font-weight: 700; padding: 10px 16px; border-radius: 8px;">
                    🔄 Reload
                </button>
                <button class="btn-master-connect" id="btnMasterConnect" onclick="triggerConnectAll()">
                    ⚡ Connect All Brokers (Prepare MCP)
                </button>
            </div>
        </div>
    </header>

    <!-- Master Readiness Checklist Banner (Step 1 Krungsri -> Step 2 Ready) -->
    <div class="readiness-banner" id="masterReadinessBanner">
        <div class="readiness-grid">
            <!-- Step 1: Krungsri TradeMan Session Gate -->
            <div class="readiness-step" id="step2KssCard">
                <div class="readiness-icon" id="step2KssIcon">🔑</div>
                <div class="readiness-details">
                    <div class="readiness-title">
                        <span>1. Krungsri TradeMan Session</span>
                        <span id="step2KssBadge" class="status-pill status-PENDING">CHECKING</span>
                    </div>
                    <div class="readiness-subtitle" id="step2KssDesc">Portfolio Accounts (3024952 / 3024959)</div>
                </div>
            </div>

            <!-- Step 2: Master System Readiness Indicator -->
            <div class="readiness-step" id="step3ReadyCard" style="background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.3);">
                <div class="readiness-icon" id="step3ReadyIcon">🟢</div>
                <div class="readiness-details">
                    <div class="readiness-title">
                        <span>2. Operations Cockpit Status</span>
                        <span id="step3ReadyBadge" class="status-pill status-READY">ALL SYSTEMS GO</span>
                    </div>
                    <div class="readiness-subtitle" id="step3ReadyDesc">Ready for Terminal CLI Execution & SBL Audits</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Block 1.5: Pillar x Broker Feature Matrix + Component Toggles (2026-10-10) -->
    <div class="card" id="controlPanel" style="margin-bottom: 16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
            <div>
                <div style="font-size:15px; font-weight:700; color: var(--text-primary);">🧩 Pillar × Broker — Feature Matrix</div>
                <div style="font-size:11.5px; color: var(--text-muted); margin-top:3px;">
                    สถานะที่ยืนยันด้วยการทดสอบจริง · 🟢 live &nbsp; 🧪 sandbox &nbsp; ⏳ pending &nbsp; ⛔ disabled &nbsp; ➖ n/a
                </div>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
                <span class="badge badge-purple" id="tradingModeBadge" title="เปลี่ยนได้ทาง LINE เท่านั้น">MODE: -</span>
                <button class="btn btn-secondary btn-sm" id="btnRefreshControl" onclick="loadControlPanel()">🔄 Refresh</button>
            </div>
        </div>

        <div style="overflow-x:auto; margin-top:12px;">
            <table id="featureMatrixTable" style="width:100%; border-collapse:collapse; font-size:12px; font-family:'JetBrains Mono', monospace;">
                <thead id="featureMatrixHead"></thead>
                <tbody id="featureMatrixBody">
                    <tr><td style="color: var(--text-muted); padding:8px;">Loading feature matrix…</td></tr>
                </tbody>
            </table>
        </div>

        <div style="margin-top:20px; padding-top:16px; border-top:1px solid var(--border-color);">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="font-size:14px; font-weight:700; color: var(--text-primary);">⚙️ Component Toggles</div>
                <div style="font-size:11px; color: var(--text-muted);" id="componentHint">Daemon = ต้องกด 🔄 Reload · Safety/LINE = มีผลทันที</div>
            </div>
            <div id="componentToggles" style="margin-top:12px; display:grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap:12px;">
                <div style="color: var(--text-muted); font-size:12px;">Loading components…</div>
            </div>
        </div>
    </div>


    <!-- Block 2: HITL Emergency & OTP Interception Banner -->
    <div class="hitl-banner" id="hitlOtpBanner">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">🚨</span>
                    <strong style="font-size: 15px; color: #fbbf24;">AI Escalation: Krungsri TradeMan 2FA SMS OTP Required</strong>
                    <span class="badge badge-amber" id="otpRefBadge" style="font-size: 13px; font-weight: 700;">Ref: -</span>
                </div>
                <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">
                    ระบบต้องการรหัส OTP เพื่อยืนยันตัวตน (หาก KDE Connect ดึงผ่าน D-Bus ไม่สำเร็จ ให้กรอก 6 หลักด้านขวา)
                </div>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <input type="text" id="manualOtpInput" maxlength="6" placeholder="123456" style="width: 140px; font-family: 'JetBrains Mono'; font-size: 16px; font-weight: 700; text-align: center; letter-spacing: 2px;">
                <button class="btn btn-amber" onclick="submitManualOtp()">📲 Submit OTP</button>
                <button class="btn btn-secondary btn-sm" onclick="dismissOtpBanner()">ปิดแจ้งเตือน</button>
            </div>
        </div>
    </div>

    <!-- Block 2.5: HITL Live Order Confirmation Banner & Multi-Order Queue -->
    <div class="hitl-banner" id="hitlOrderBanner" style="border-left-color: #f59e0b; background: rgba(245, 158, 11, 0.12); padding: 16px 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 22px;">⚠️</span>
                <div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <strong style="font-size: 16px; color: #fbbf24;">Live Trade Confirmation Required (HITL Gate)</strong>
                        <span class="badge badge-amber" id="hitlOrderBadge" style="font-size: 12px; font-weight: 700;">0 ORDERS</span>
                    </div>
                    <div style="font-size: 12px; color: #cbd5e1; margin-top: 2px;">
                        ระบบส่งแจ้งเตือนด่วนไปยังมือถือ Xiaomi Mi 10T แล้ว กรุณาตรวจสอบรายละเอียดและกด Confirm เพื่อส่งคำสั่งเข้าสู่ตลาด
                    </div>
                </div>
            </div>
            <div id="hitlBatchActions" style="display: none; gap: 8px;">
                <button class="btn btn-green btn-sm" onclick="confirmAllHitlOrders()" style="font-weight: 700; padding: 7px 16px;">
                    🚀 Confirm All
                </button>
                <button class="btn btn-danger btn-sm" onclick="rejectAllHitlOrders()" style="padding: 7px 14px;">
                    🛑 Cancel All
                </button>
            </div>
        </div>
        <!-- Dynamic Multi-Order List -->
        <div id="hitlOrdersList" style="display: flex; flex-direction: column; gap: 8px;">
            <!-- Populated dynamically via checkPendingHitlOrders() -->
        </div>
    </div>

    <!-- Block 1: Unified Sentinel & Connection Cockpit (2 Cards in a row) -->
    <div class="grid-brokers">
        <!-- 1. Krungsri TradeMan -->
        <div class="card" style="border-left: 3px solid #3b82f6;">
            <div class="card-header">
                <div class="card-title">
                    <span>🏢 Krungsri TradeMan</span>
                </div>
                <span id="kssStatusPill" class="status-pill status-PENDING">CHECKING</span>
            </div>
            <div class="sentinel-info">
                <div class="sentinel-row">
                    <span class="sentinel-label">Active Account:</span>
                    <span class="sentinel-val" id="kssAccount">Cash / Margin</span>
                </div>
                <div class="sentinel-row">
                    <span class="sentinel-label">Current OTP Ref:</span>
                    <span class="sentinel-val" id="kssRefCode" style="color: #fbbf24; font-weight: 700;">-</span>
                </div>
                <div class="sentinel-row">
                    <span class="sentinel-label">Heartbeat:</span>
                    <span class="sentinel-val" id="kssHeartbeat">-</span>
                </div>
            </div>
            <div style="display: flex; gap: 6px;">
                <button class="btn btn-primary btn-sm" style="flex: 1;" onclick="triggerLoginBroker('KRUNGSRI')">🚀 Login</button>
                <button class="btn btn-danger btn-sm" onclick="triggerLogoutAll()">🛑 Disconnect</button>
            </div>
        </div>

        <!-- 2. Liberator Securities (WebTrade) -->
        <div class="card" style="border-left: 3px solid #f59e0b;">
            <div class="card-header">
                <div class="card-title">
                    <span>🦁 Liberator WebTrade</span>
                </div>
                <span id="libStatusPill" class="status-pill status-STANDBY">STANDBY</span>
            </div>
            <div class="sentinel-info">
                <div class="sentinel-row">
                    <span class="sentinel-label">Active Account:</span>
                    <span class="sentinel-val" id="libAccount">Cash / SBL</span>
                </div>
                <div class="sentinel-row">
                    <span class="sentinel-label">Platform:</span>
                    <span class="sentinel-val" style="color: #fbbf24;">WebTrade PWA</span>
                </div>
                <div class="sentinel-row">
                    <span class="sentinel-label">Heartbeat:</span>
                    <span class="sentinel-val" id="libHeartbeat">-</span>
                </div>
            </div>
            <div style="display: flex; gap: 6px;">
                <button class="btn btn-amber btn-sm" style="flex: 1;" onclick="triggerLoginBroker('LIBERATOR')">🚀 Launch WebTrade</button>
                <button class="btn btn-secondary btn-sm" onclick="checkUnifiedHealth()">🔄 Check</button>
            </div>
        </div>
    </div>

    <!-- Terminal CLI Test Runner & Command Cheat Sheet -->
    <div class="card cli-runner-card" style="border-left: 3px solid #8b5cf6;">
        <div class="card-header" style="margin-bottom: 12px;">
            <div class="card-title">
                <span>💻 Terminal CLI Test Runner</span>
                <span class="card-tag" style="color: #a78bfa; background: rgba(139, 92, 246, 0.15);">Verified Ready for Run</span>
            </div>
            <span class="badge badge-purple">Safe Post-Startup Execution</span>
        </div>
        <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 14px;">
            ระบบผ่านการตรวจสอบ Hardware Bridge และ Krungsri Session เรียบร้อยแล้ว สามารถกด <b>Copy</b> คำสั่งด้านล่างไปรันใน Terminal เพื่อทดสอบระบบได้ทันที:
        </p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 10px;">
            <div class="cli-cmd-row">
                <div style="min-width: 0;">
                    <div class="cli-cmd-label">🔍 Live SBL Inventory & Short Audit (Krungsri)</div>
                    <div class="cli-cmd-text">python -m scripts.krungsri.test_sbl_live_audit</div>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="copyCliCmd(this, 'python -m scripts.krungsri.test_sbl_live_audit')">📋 Copy</button>
            </div>
            <div class="cli-cmd-row">
                <div style="min-width: 0;">
                    <div class="cli-cmd-label">⚡ Homelab Pre-Flight Inspection</div>
                    <div class="cli-cmd-text">python scripts/preflight_check.py</div>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="copyCliCmd(this, 'python scripts/preflight_check.py')">📋 Copy</button>
            </div>
            <div class="cli-cmd-row">
                <div style="min-width: 0;">
                    <div class="cli-cmd-label">🤖 End-to-End AutoTrade Workflow (Shared)</div>
                    <div class="cli-cmd-text">python -m scripts.shared.run_autotrade_e2e_test</div>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="copyCliCmd(this, 'python -m scripts.shared.run_autotrade_e2e_test')">📋 Copy</button>
            </div>
            <div class="cli-cmd-row">
                <div style="min-width: 0;">
                    <div class="cli-cmd-label">🏢 Krungsri Real Money CLI</div>
                    <div class="cli-cmd-text">python -m app.brokers.krungsri.cli status</div>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="copyCliCmd(this, 'python -m app.brokers.krungsri.cli status')">📋 Copy</button>
            </div>
            <div class="cli-cmd-row">
                <div style="min-width: 0;">
                    <div class="cli-cmd-label">🕊️ Liberator 0% Comm CLI</div>
                    <div class="cli-cmd-text">python -m app.brokers.liberator.cli status</div>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="copyCliCmd(this, 'python -m app.brokers.liberator.cli status')">📋 Copy</button>
            </div>
            <div class="cli-cmd-row">
                <div style="min-width: 0;">
                    <div class="cli-cmd-label">🎯 Click2Win Multi-Account Test</div>
                    <div class="cli-cmd-text">python -m scripts.click2win.test_c2w_account_switch</div>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="copyCliCmd(this, 'python -m scripts.click2win.test_c2w_account_switch')">📋 Copy</button>
            </div>
        </div>
    </div>

    <!-- Block 3.5: Krungsri SSO SBL Real-time Radar & Corporate Actions (XD/XR) Shield -->
    <div class="card sbl-radar-card" style="border-left: 3px solid #f59e0b; margin-bottom: 24px;">
        <div class="card-header" style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div class="card-title">
                <span>🎯 Krungsri SSO SBL Real-time Radar & Risk Shield</span>
                <span class="card-tag" style="color: #fbbf24; background: rgba(245, 158, 11, 0.15);">Member Portal Real Time</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3);" id="sblPpBadge">PP: ฿96,885.94</span>
                <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; border-color: rgba(59, 130, 246, 0.3);" id="sblAccountBadge">Acc: 302495 (อารยะ สวัสดิชัย)</span>
                <button class="btn btn-primary btn-sm" id="btnSyncSbl" onclick="syncSblOnDemand()" style="background: linear-gradient(135deg, #f59e0b, #d97706); border: none; font-weight: 700;">
                    🔄 On-Demand Sync SBL
                </button>
            </div>
        </div>

        <!-- Corporate Actions XD/XR Warning Banner -->
        <div id="sblXdXrBanner" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; font-weight: 700; color: #f87171; margin-bottom: 6px; font-size: 13px;">
                <span>⛔ CORPORATE ACTIONS (XD/XR) HARD BLOCK ACTIVE</span>
                <span style="font-size: 11px; background: rgba(239, 68, 68, 0.25); padding: 2px 8px; border-radius: 4px; color: #fca5a5;">Protected against 100% Dividend Liability</span>
            </div>
            <div style="font-size: 12px; color: #fecaca; margin-bottom: 8px;">
                หุ้นด้านล่างนี้อยู่ในบัญชี XD/XR ของ บล.กรุงศรี ระบบจะ <b>บล็อกคำสั่งยืมและขายชอร์ต (Short Sell) อัตโนมัติ</b> เพื่อป้องกันการเสียสิทธิ์และชดเชยเงินปันผล:
            </div>
            <div id="sblBlockedSymbolsList" style="display: flex; gap: 8px; flex-wrap: wrap;">
                <!-- Filled dynamically by JS -->
            </div>
        </div>

        <!-- Quick Symbol SBL Risk Auditor -->
        <div style="display: flex; gap: 10px; align-items: center; background: rgba(15, 23, 42, 0.6); padding: 12px; border-radius: 8px; border: 1px solid var(--border-color); margin-bottom: 16px; flex-wrap: wrap;">
            <span style="font-size: 12px; font-weight: 600; color: var(--text-secondary);">🔍 ตรวจสอบหุ้นเดี่ยว:</span>
            <input type="text" id="sblAuditSymbolInput" placeholder="พิมพ์ชื่อหุ้น เช่น SAWAD หรือ BDMS" style="background: rgba(0,0,0,0.4); border: 1px solid var(--border-color); color: #fff; padding: 6px 12px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; font-size: 13px; width: 220px;" onkeydown="if(event.key==='Enter') checkSymbolSblRisk()">
            <button class="btn btn-secondary btn-sm" onclick="checkSymbolSblRisk()">ตรวจสอบความเสี่ยง</button>
            <div id="sblAuditResultBadge" style="font-size: 12px; font-weight: 600;"></div>
        </div>

        <!-- Pool Statistics -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-bottom: 14px;">
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">SET 50 Inventory</div>
                <div style="font-size: 18px; font-weight: 700; color: #60a5fa;" id="sblSet50Count">-</div>
            </div>
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">SET 100 Inventory</div>
                <div style="font-size: 18px; font-weight: 700; color: #a78bfa;" id="sblSet100Count">-</div>
            </div>
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">NEW SEC Inventory</div>
                <div style="font-size: 18px; font-weight: 700; color: #38bdf8;" id="sblNewSecCount">-</div>
            </div>
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px;">
                <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Corporate Actions (XD/XR)</div>
                <div style="font-size: 18px; font-weight: 700; color: #f87171;" id="sblXdCount">-</div>
            </div>
        </div>

        <div style="font-size: 11px; color: var(--text-muted); text-align: right;" id="sblLastUpdated">
            Last Updated: -
        </div>
    </div>



    <!-- Block 4: Execution Engine & Tactical Operations Cockpit (Pillar 3 & Pillar 6) -->
    <div class="grid">
        <!-- Left: Quick Order Test Box (Pillar 3 Sandbox Execution) -->
        <div class="col-6">
            <div class="card" style="border-color: rgba(59, 130, 246, 0.4); background: rgba(14, 22, 38, 0.9);">
                <div class="card-header">
                    <div class="card-title">
                        <span>🚀 Direct Order Execution (Sandbox / Broker)</span>
                        <span class="card-tag" style="color: #60a5fa; background: rgba(59, 130, 246, 0.15);">Pillar 3 Engine</span>
                    </div>
                </div>
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                    ส่งคำสั่งซื้อขายจริงบนกระดานจำลอง (Click2Win Sandbox) หรือ Krungsri พร้อมระบบตรวจ Pre-Trade Guardrails
                </p>

                <div class="grid" style="gap: 8px; margin-bottom: 8px;">
                    <div class="col-6">
                        <label>เลือกโบรกเกอร์เป้าหมาย</label>
                        <select id="quickBroker">
                            <option value="CLICK2WIN">Settrade Click2Win (Sandbox จำลอง)</option>
                            <option value="TRADEMAN">Krungsri TradeMan (กระดานจริง)</option>
                            <option value="LIBERATOR">Liberator Securities (WebTrade)</option>
                        </select>
                    </div>
                    <div class="col-6">
                        <label>ประเภทบัญชี</label>
                        <select id="quickAccountType" onchange="onQuickAccountTypeChange()">
                            <option value="EQUITY">Equity (หุ้นทั่วไป)</option>
                            <option value="DERIVATIVES">Derivatives (TFEX อนุพันธ์)</option>
                            <option value="CASH">Cash Balance (Krungsri 3024952)</option>
                            <option value="MARGIN">Credit Balance SBL (Krungsri 3024959)</option>
                        </select>
                    </div>
                </div>

                <div class="grid" style="gap: 8px; margin-bottom: 10px;">
                    <div class="col-3">
                        <label>Symbol</label>
                        <input type="text" id="quickSymbol" value="CPALL" oninput="onQuickSymbolInput()" style="text-transform: uppercase;">
                    </div>
                    <div class="col-3" id="quickSideCol">
                        <label id="quickSideLabel">Side</label>
                        <select id="quickSide">
                            <option value="BUY">BUY (ซื้อ)</option>
                            <option value="SELL">SELL (ขาย)</option>
                            <option value="OPEN_SHORT">OPEN_SHORT (ยืมขาย SBL)</option>
                            <option value="COVER">COVER (ซื้อคืน SBL)</option>
                        </select>
                    </div>
                    <div class="col-2" id="quickPositionCol" style="display: none;">
                        <label>Position (TFEX)</label>
                        <select id="quickPosition">
                            <option value="AUTO">AUTO (ตรวจพอร์ตอัตโนมัติ)</option>
                            <option value="OPEN">OPEN (เปิดสัญญา)</option>
                            <option value="CLOSE">CLOSE (ปิดสัญญา)</option>
                        </select>
                    </div>
                    <div class="col-2" id="quickVolCol">
                        <label id="quickVolumeLabel">Volume (หุ้น)</label>
                        <input type="number" id="quickVolume" value="100" step="100" min="1">
                    </div>
                    <div class="col-2">
                        <label>Price (บาท)</label>
                        <input type="number" id="quickPrice" step="0.01" value="50.00">
                    </div>
                </div>

                <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;">
                    <button class="btn btn-primary" id="btnExecuteQuickOrder" style="flex: 1; min-width: 220px;" onclick="executeQuickOrder()">
                        ⚡ Submit Order with Pre-Trade Guardrails
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="setQuickPreset('CPALL', 'BUY', 100, 50.00, 'EQUITY')">Preset CPALL</button>
                    <button class="btn btn-secondary btn-sm" onclick="setQuickPreset('TRUE', 'BUY', 100, 13.20, 'EQUITY')">Preset TRUE</button>
                    <button class="btn btn-secondary btn-sm" style="border-color: #8b5cf6; color: #c084fc;" onclick="setQuickPreset('SPALIU26', 'LONG', 1, 16.00, 'DERIVATIVES', 'AUTO')">Preset SPALIU26 (TFEX)</button>
                    <button class="btn btn-secondary btn-sm" style="border-color: #8b5cf6; color: #c084fc;" onclick="setQuickPreset('S50U26', 'LONG', 1, 950.00, 'DERIVATIVES', 'AUTO')">Preset S50U26 (TFEX)</button>
                </div>

                <div style="font-size: 11px; color: var(--text-muted); display: flex; gap: 12px;">
                    <span id="quickGuardrailHint">🛡️ Guardrails: Volume % 100 == 0 (Board lot required)</span>
                    <span>•</span>
                    <span>Max Value: ฿1,000,000</span>
                    <span>•</span>
                    <span>TypeSafe Isolated</span>
                </div>
            </div>
        </div>

        <!-- Right: Tactical Strategy Tools & Live Execution Log (Pillar 6) -->
        <div class="col-6">
            <div class="card" style="border-color: rgba(139, 92, 246, 0.4); background: rgba(18, 16, 36, 0.9);">
                <div class="card-header">
                    <div class="card-title">
                        <span>🎯 Tactical Strategy Tools & Runbook Log</span>
                        <span class="card-tag" style="color: #c084fc; background: rgba(139, 92, 246, 0.15);">Pillar 6: Tactics</span>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="clearConsoleLog()">ล้าง Log</button>
                </div>

                <div style="display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;">
                    <button class="btn btn-purple btn-sm" onclick="triggerPriceNegotiation()">
                        🤝 สั่งต่อราคาคำสั่งค้าง (Pillar 6.1)
                    </button>
                    <button class="btn btn-amber btn-sm" onclick="triggerEodCleanup()">
                        ⏰ เคลียร์คำสั่งค้างก่อนปิดวัน (Pillar 6.2)
                    </button>
                </div>

                <!-- Natural Language Tactical Action Exit Card (Pillar 6.3) -->
                <div style="margin-bottom: 12px; padding: 12px; background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(139, 92, 246, 0.35); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-weight: 700; color: #c084fc; font-size: 13px;">⚡ Natural Language Tactical Action Exit (Pillar 6.3)</span>
                            <span style="background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 9999px;">🤖 AUTO-TRADE READY</span>
                        </div>
                        <button class="btn btn-secondary btn-sm" onclick="pasteSampleActionExit()" style="font-size: 11px; padding: 2px 8px; border-color: rgba(139, 92, 246, 0.5); color: #e9d5ff;">📋 ใส่ตัวอย่าง Krungsri</button>
                    </div>
                    <textarea id="actionExitTextInput" rows="4" style="width: 100%; background: #0b0f19; border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 6px; color: #f8fafc; font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px; resize: vertical; box-sizing: border-box;" placeholder="วางข้อความ Action Exits ประจำวัน เช่น:
🏛️ [พอร์ต Krungsri Margin - KSS]
🚨 Action Exits วันนี้:
• [Timeout] SAWAD (LONG): SELL 2,200 หุ้น @ 22.30 (+0.45% / +0.22x ATR) 👉 ครบ 10 วันทำการ ปิดล็อกกำไรปลดล็อกเงินสด
• [Timeout] COCOCO (LONG): SELL 8,800 หุ้น @ 5.60 (-0.88% / -0.47x ATR) 👉 ครบ 10 วันทำการ ปิดรอบปลดล็อกเงินสด
• [Weed-out] AAV (LONG): SELL 57,000 หุ้น @ 0.84 (-2.33% / -0.64x ATR) 👉 ถือ 7 วัน > 5D ขาดทุนเกิน -1.0% ตัดทิ้งคัดกรองไม้แย่"></textarea>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; flex-wrap: wrap; gap: 8px;">
                        <div style="font-size: 11px; color: #94a3b8;">
                            <span>🛡️ 09:45 Pre-Flight Session Check | Win: 10:00-10:30 (Offer 1) | Loss: 10:30-12:00 (Offer 1 / Bid 1)</span>
                        </div>
                        <button class="btn btn-purple btn-sm" id="btnParseActionExit" onclick="submitNaturalLanguageActionExit()" style="font-weight: 700; padding: 6px 14px;">
                            🚀 Parse & Auto-Schedule (ยิงอัตโนมัติตามเวลา)
                        </button>
                    </div>
                </div>

                <div class="console-output" id="consoleLog">⚡ Operations Cockpit พร้อมทำงาน...
• Settrade Open API: WebSocket MQTT Engine สตรีมราคา ticks อัตโนมัติ
• Playwright Engine: พร้อมส่งคำสั่งจริงบนกระดานจำลอง Sandbox
• KDE Connect: เชื่อมต่อ D-Bus เพื่อรับ OTP อัตโนมัติ</div>
            </div>
        </div>
    </div>

    <!-- Block 5: SQLite Database Orders Journal -->
    <div class="grid">
        <div class="col-12">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>📋 Database Orders Journal (SQLite)</span>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <button class="btn btn-secondary btn-sm" onclick="loadOrdersHistory()">🔄 Refresh Journal</button>
                        <button class="btn btn-danger btn-sm" onclick="clearOrdersDatabase()">🗑️ Clear Journal</button>
                    </div>
                </div>

                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Order ID</th>
                                <th>Side</th>
                                <th>Symbol</th>
                                <th>Volume</th>
                                <th>Price</th>
                                <th>Status</th>
                                <th>Broker/Source</th>
                                <th>Note / Error</th>
                                <th>Timestamp</th>
                            </tr>
                        </thead>
                        <tbody id="ordersTableBody">
                            <tr>
                                <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 18px;">
                                    กำลังโหลดรายการคำสั่งจาก SQLite...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="toast" id="toast">Message</div>

<script>
    const API_BASE = '/api/v1';

    function showToast(msg) {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.classList.add('show');
        setTimeout(() => t.classList.remove('show'), 3200);
    }

    function appendLog(msg, type = "info") {
        const el = document.getElementById('consoleLog');
        const ts = new Date().toLocaleTimeString();
        let prefix = "ℹ️";
        if (type === "success") prefix = "✅";
        if (type === "warn") prefix = "⚠️";
        if (type === "error") prefix = "❌";
        el.textContent = `[${ts}] ${prefix} ${msg}\n` + el.textContent;
    }

    function clearConsoleLog() {
        document.getElementById('consoleLog').textContent = "⚡ Log cleared.";
    }

    function copyCliCmd(btn, cmd) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(cmd).then(() => {
                const orig = btn.innerHTML;
                btn.innerHTML = "✅ Copied!";
                btn.style.borderColor = "#10b981";
                btn.style.color = "#34d399";
                showToast(`📋 Copied: ${cmd}`);
                setTimeout(() => {
                    btn.innerHTML = orig;
                    btn.style.borderColor = "";
                    btn.style.color = "";
                }, 2000);
            }).catch(() => {
                prompt("Copy command:", cmd);
            });
        } else {
            prompt("Copy command:", cmd);
        }
    }

    // --------------------------------------------------------------------------
    // Unified Health & Sentinel
    // --------------------------------------------------------------------------
    async function checkUnifiedHealth() {
        try {
            const res = await fetch(`${API_BASE}/session/health`);
            if (!res.ok) return;
            const data = await res.json();

            // Krungsri TradeMan
            const kss = data.krungsri_trademan || {};
            const kssPill = document.getElementById('kssStatusPill');
            kssPill.textContent = kss.status || "DISCONNECTED";
            kssPill.className = `status-pill status-${kss.status}`;
            document.getElementById('kssHeartbeat').textContent = kss.last_heartbeat ? new Date(kss.last_heartbeat).toLocaleTimeString() : "-";
            document.getElementById('kssRefCode').textContent = kss.current_otp_ref || "-";

            // Liberator
            const lib = (data.brokers && data.brokers.liberator) ? data.brokers.liberator : {};
            const libPill = document.getElementById('libStatusPill');
            if (libPill) {
                const libStatus = lib.status || "STANDBY";
                libPill.textContent = libStatus;
                libPill.className = `status-pill status-${libStatus}`;
                const libHb = document.getElementById('libHeartbeat');
                if (libHb) libHb.textContent = lib.last_heartbeat ? new Date(lib.last_heartbeat).toLocaleTimeString() : "-";
                const libAcc = document.getElementById('libAccount');
                if (libAcc) libAcc.textContent = lib.is_configured ? "7055938 (Cash)" : "Not Configured";
            }

            // Check for HITL OTP condition
            if (kss.status === "AWAITING_OTP" || (kss.current_otp_ref && kss.current_otp_ref !== "-")) {
                const banner = document.getElementById('hitlOtpBanner');
                banner.classList.add('active');
                document.getElementById('otpRefBadge').textContent = `Ref: ${kss.current_otp_ref}`;
            } else {
                const banner = document.getElementById('hitlOtpBanner');
                if (!banner.dataset.manualKeep) {
                    banner.classList.remove('active');
                }
            }

            // Check for pending Live Orders awaiting HITL confirmation
            checkPendingHitlOrders();

            // Update Master Readiness Checklist Banner
            const step2Badge = document.getElementById('step2KssBadge');
            const step2Card = document.getElementById('step2KssCard');
            const step3Badge = document.getElementById('step3ReadyBadge');
            const step3Card = document.getElementById('step3ReadyCard');
            const step3Desc = document.getElementById('step3ReadyDesc');
            const banner = document.getElementById('masterReadinessBanner');

            const isKssReady = kss.status === "AUTHENTICATED" || kss.status === "CONNECTED";

            if (step2Badge) {
                step2Badge.textContent = isKssReady ? "AUTHENTICATED" : (kss.status || "DISCONNECTED");
                step2Badge.className = `status-pill status-${isKssReady ? 'READY' : (kss.status || 'OFFLINE')}`;
                if (step2Card) step2Card.className = `readiness-step ${isKssReady ? 'step-success' : 'step-warning'}`;
            }

            if (step3Badge) {
                if (isKssReady) {
                    step3Badge.textContent = "ALL SYSTEMS GO";
                    step3Badge.className = "status-pill status-READY";
                    if (step3Desc) step3Desc.textContent = "Ready for Terminal CLI Execution & SBL Audits";
                    if (step3Card) {
                        step3Card.style.background = "rgba(16, 185, 129, 0.12)";
                        step3Card.style.borderColor = "rgba(16, 185, 129, 0.4)";
                    }
                    if (banner) banner.style.borderColor = "rgba(16, 185, 129, 0.35)";
                } else {
                    step3Badge.textContent = "INITIALIZING";
                    step3Badge.className = "status-pill status-PENDING";
                    const pendingItems = [];
                    if (!isKssReady) pendingItems.push("Krungsri Session");
                    if (step3Desc) step3Desc.textContent = `Pending: ${pendingItems.join(" + ")}`;
                    if (step3Card) {
                        step3Card.style.background = "rgba(245, 158, 11, 0.08)";
                        step3Card.style.borderColor = "rgba(245, 158, 11, 0.3)";
                    }
                    if (banner) banner.style.borderColor = "rgba(245, 158, 11, 0.3)";
                }
            }

        } catch (e) {
            console.warn("Unified health check error:", e);
        }
    }

    // --------------------------------------------------------------------------
    // UI Concurrency & Button Lock Guard
    // --------------------------------------------------------------------------
    const inFlightHitlOrders = new Set();
    const lockedButtons = new WeakSet();

    async function withButtonLock(btn, loadingHtml, asyncFn) {
        if (!btn) return await asyncFn();
        if (btn.disabled || lockedButtons.has(btn)) return;
        
        lockedButtons.add(btn);
        btn.disabled = true;
        btn.classList.add('btn-locked');
        const origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="btn-spinner"></span> ${loadingHtml}`;

        try {
            return await asyncFn();
        } finally {
            btn.innerHTML = origHtml;
            btn.disabled = false;
            btn.classList.remove('btn-locked');
            lockedButtons.delete(btn);
        }
    }

    async function triggerConnectAll() {
        const btn = document.getElementById('btnMasterConnect');
        await withButtonLock(btn, "Connecting All Sessions...", async () => {
            showToast("⚡ กำลังเชื่อมต่อทุกโบรกเกอร์ (KDE Connect, Click2Win, TradeMan, Open API)...");
            appendLog("Triggered 1-Click Connect All Brokers for MCP operations...");
            try {
                const res = await fetch(`${API_BASE}/session/connect-all`, { method: 'POST' });
                const data = await res.json();
                appendLog(`Connect All Completed: ${JSON.stringify(data.actions)}`, "success");
                showToast("เชื่อมต่อทุกโบรกเกอร์เรียบร้อยแล้ว!");
                checkUnifiedHealth();
            } catch (e) {
                appendLog(`Connect All failed: ${e.message}`, "error");
                showToast(`เชื่อมต่อล้มเหลว: ${e.message}`);
            }
        });
    }

    async function triggerLoginBroker(platform, forceFresh = true) {
        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Logging in...", async () => {
            showToast(`กำลังเริ่มล็อกอิน ${platform}...`);
            appendLog(`Initiating fresh login for ${platform}...`);
            try {
                const res = await fetch(`${API_BASE}/session/login-broker`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ platform: platform, force_fresh: forceFresh })
                });
                const data = await res.json();
                if (data.success) {
                    appendLog(`Login initiated for ${platform}: ${data.message || 'Success'}`, "success");
                    showToast(`สั่งล็อกอิน ${platform} สำเร็จ`);
                } else {
                    appendLog(`Login status for ${platform}: ${data.message || data.status}`, "warn");
                    showToast(data.message || "กำลังรอดำเนินการ");
                }
                setTimeout(checkUnifiedHealth, 1500);
            } catch (e) {
                appendLog(`Login error for ${platform}: ${e.message}`, "error");
            }
        });
    }

    async function triggerLogoutAll() {
        if (!confirm("ต้องการตัดการเชื่อมต่อและปิดเบราว์เซอร์ทั้งหมดใช่หรือไม่?")) return;
        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Disconnecting...", async () => {
            try {
                const res = await fetch(`${API_BASE}/session/logout`, { method: 'POST' });
                const data = await res.json();
                appendLog(`Sessions terminated: ${data.message}`, "warn");
                showToast("ปิดเซสชันทั้งหมดเรียบร้อยแล้ว");
                checkUnifiedHealth();
            } catch (e) {
                appendLog(`Logout error: ${e.message}`, "error");
            }
        });
    }

    // --------------------------------------------------------------------------
    // OTP Submission
    // --------------------------------------------------------------------------
    async function submitManualOtp() {
        const input = document.getElementById('manualOtpInput');
        const code = input.value.trim();
        if (code.length !== 6 || isNaN(code)) {
            showToast("กรุณากรอกรหัส OTP ให้ครบ 6 หลัก");
            return;
        }

        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Submitting OTP...", async () => {
            showToast(`กำลังส่ง OTP ${code} ไปยังระบบล็อกอิน...`);
            appendLog(`Submitting manual OTP ${code} to session...`);
            try {
                const res = await fetch(`${API_BASE}/session/submit-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ otp: code })
                });
                const data = await res.json();
                if (res.ok) {
                    appendLog(`OTP ${code} submitted successfully!`, "success");
                    showToast("ส่ง OTP สำเร็จ!");
                    input.value = "";
                    dismissOtpBanner();
                    setTimeout(checkUnifiedHealth, 1500);
                } else {
                    appendLog(`Failed to submit OTP: ${data.detail}`, "error");
                    showToast(`ส่ง OTP ล้มเหลว: ${data.detail}`);
                }
            } catch (e) {
                appendLog(`OTP submission error: ${e.message}`, "error");
            }
        });
    }

    function dismissOtpBanner() {
        const b = document.getElementById('hitlOtpBanner');
        if (b) {
            b.classList.remove('active');
            b.dataset.manualKeep = "";
        }
    }

    // --------------------------------------------------------------------------
    // HITL Live Order Confirmation Handlers
    // --------------------------------------------------------------------------
    let pendingHitlOrders = [];
    let currentPendingHitlOrder = null;

    async function checkPendingHitlOrders() {
        try {
            const res = await fetch(`${API_BASE}/orders/hitl/pending`);
            if (!res.ok) return;
            pendingHitlOrders = await res.json();
            const banner = document.getElementById('hitlOrderBanner');
            const list = document.getElementById('hitlOrdersList');
            const badge = document.getElementById('hitlOrderBadge');
            const batchActions = document.getElementById('hitlBatchActions');

            if (pendingHitlOrders && pendingHitlOrders.length > 0) {
                currentPendingHitlOrder = pendingHitlOrders[0];
                if (banner) banner.classList.add('active');
                if (badge) badge.innerText = `${pendingHitlOrders.length} ORDER${pendingHitlOrders.length > 1 ? 'S' : ''} PENDING`;
                if (batchActions) batchActions.style.display = pendingHitlOrders.length > 1 ? 'flex' : 'none';

                if (list) {
                    list.innerHTML = pendingHitlOrders.map(o => {
                        const isBuy = ['BUY', 'LONG', 'COVER'].includes(o.side.toUpperCase());
                        const sideColor = isBuy ? '#34d399' : '#f87171';
                        const posBadge = o.position ? `<span class="badge" style="background: rgba(139, 92, 246, 0.25); color: #c084fc; font-weight: 700; font-size: 11px;">${o.position}</span>` : '';
                        const isSubmitting = inFlightHitlOrders.has(o.order_id);

                        const tagBadge = o.tag ? `<span class="badge" style="background: rgba(234, 179, 8, 0.25); color: #fde047; font-weight: 700; font-size: 11px;">[${o.tag}]</span>` : '';
                        const windowBadge = o.window ? (
                            o.is_profit
                                ? `<span class="badge" style="background: rgba(16, 185, 129, 0.25); color: #6ee7b7; font-weight: 700; font-size: 11px;">🟢 ${o.window}</span>`
                                : `<span class="badge" style="background: rgba(239, 68, 68, 0.25); color: #fca5a5; font-weight: 700; font-size: 11px;">🔴 ${o.window}</span>`
                        ) : '';
                        const pnlBadge = (o.pnl_pct != null) ? `<span style="font-size: 12px; color: ${o.pnl_pct >= 0 ? '#34d399' : '#f87171'}; font-weight: 600;">(${o.pnl_pct > 0 ? '+' : ''}${o.pnl_pct}%)</span>` : '';
                        const reasonRow = o.reason ? `<div style="font-size: 11.5px; color: #94a3b8; width: 100%; margin-top: 4px; display: flex; gap: 8px; flex-wrap: wrap;"><span>👉 ${o.reason}</span> <span style="color: #64748b;">|</span> <span style="color: #cbd5e1;">Rule: ${o.pricing_rule || 'Passive Offer1 Queue'}</span></div>` : '';

                        const confirmBtnHtml = isSubmitting
                            ? `<button class="btn btn-green btn-sm btn-locked" id="btnConfirm_${o.order_id}" disabled style="font-weight: 700; padding: 6px 14px; font-size: 13px;">
                                 <span class="btn-spinner"></span> ⏳ Submitting...
                               </button>`
                            : `<button class="btn btn-green btn-sm" id="btnConfirm_${o.order_id}" onclick="confirmSingleHitlOrder('${o.order_id}')" style="font-weight: 700; padding: 6px 14px; font-size: 13px;">
                                 ✅ Confirm
                               </button>`;

                        const rejectBtnHtml = isSubmitting
                            ? `<button class="btn btn-secondary btn-sm btn-locked" disabled style="background: rgba(239, 68, 68, 0.15); color: #fca5a5; opacity: 0.5; padding: 6px 10px; font-size: 13px;">
                                 ❌ Cancel
                               </button>`
                            : `<button class="btn btn-secondary btn-sm" onclick="rejectSingleHitlOrder('${o.order_id}')" style="background: rgba(239, 68, 68, 0.25); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4); padding: 6px 10px; font-size: 13px;">
                                 ❌ Cancel
                               </button>`;

                        return `
                            <div style="display: flex; flex-direction: column; background: rgba(15, 23, 42, 0.75); border: 1px solid ${isSubmitting ? 'rgba(59, 130, 246, 0.6)' : 'rgba(245, 158, 11, 0.35)'}; border-radius: 8px; padding: 10px 14px; gap: 6px; transition: all 0.3s ease;">
                                <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">
                                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                        <span class="badge" style="background: rgba(59, 130, 246, 0.25); color: #93c5fd; font-weight: 700; font-size: 11.5px;">${o.broker || 'BROKER'}</span>
                                        ${tagBadge}
                                        ${windowBadge}
                                        <span style="color: ${sideColor}; font-weight: 800; font-size: 14.5px;">[${o.side}]</span>
                                        ${posBadge}
                                        <strong style="font-size: 15px; color: #f8fafc;">${o.volume.toLocaleString()} ${o.symbol}</strong>
                                        <span style="color: #fbbf24; font-weight: 700; font-size: 14px;">@ ฿${Number(o.price).toFixed(2)}</span>
                                        ${pnlBadge}
                                        <span style="color: #64748b; font-size: 11.5px; font-family: 'JetBrains Mono';">(${o.order_id})</span>
                                    </div>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        ${confirmBtnHtml}
                                        ${rejectBtnHtml}
                                    </div>
                                </div>
                                ${reasonRow}
                            </div>
                        `;
                    }).join('');
                }
            } else {
                pendingHitlOrders = [];
                currentPendingHitlOrder = null;
                if (banner) banner.classList.remove('active');
            }
        } catch (e) {
            console.debug("Check pending hitl orders:", e);
        }
    }

    async function confirmSingleHitlOrder(orderId) {
        if (inFlightHitlOrders.has(orderId)) return;
        inFlightHitlOrders.add(orderId);

        const btn = document.getElementById(`btnConfirm_${orderId}`);
        if (btn) {
            btn.disabled = true;
            btn.classList.add('btn-locked');
            btn.innerHTML = `<span class="btn-spinner"></span> ⏳ Submitting...`;
        }

        const card = btn?.closest('div[style*="justify-content: space-between"]');
        if (card) {
            const cancelBtn = card.querySelector("button[onclick*='rejectSingleHitlOrder']");
            if (cancelBtn) {
                cancelBtn.disabled = true;
                cancelBtn.classList.add('btn-locked');
            }
        }

        try {
            showToast(`⏳ กำลังส่งคำสั่ง ${orderId} เข้าสู่ตลาด...`);
            const res = await fetch(`${API_BASE}/orders/hitl/${orderId}/confirm`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast(`✅ ยืนยันคำสั่ง ${orderId} สำเร็จ ส่งเข้าตลาดเรียบร้อย!`);
                appendLog(`Live Order ${orderId} Confirmed & Executed on ${data.message || 'broker'}`, "success");
            } else {
                showToast(`❌ ยืนยันคำสั่งล้มเหลว: ${data.message || 'Error'}`);
                appendLog(`Live Order ${orderId} confirmation failed: ${data.message}`, "error");
            }
        } catch (e) {
            showToast(`Error: ${e.message}`);
        } finally {
            inFlightHitlOrders.delete(orderId);
            checkPendingHitlOrders();
            loadOrdersHistory();
        }
    }

    async function rejectSingleHitlOrder(orderId) {
        if (inFlightHitlOrders.has(orderId)) return;
        if (!confirm(`ต้องการยกเลิกคำสั่ง ${orderId} ใช่หรือไม่?`)) return;
        inFlightHitlOrders.add(orderId);

        const btn = window.event?.currentTarget;
        if (btn) {
            btn.disabled = true;
            btn.classList.add('btn-locked');
            btn.innerHTML = `<span class="btn-spinner"></span> ⏳ Cancelling...`;
        }

        try {
            const res = await fetch(`${API_BASE}/orders/hitl/${orderId}/reject`, { method: 'POST' });
            if (res.ok) {
                showToast(`ยกเลิกคำสั่ง ${orderId} เรียบร้อยแล้ว`);
                appendLog(`Live Order ${orderId} cancelled by user`, "warn");
            }
        } catch (e) {
            showToast(`Error: ${e.message}`);
        } finally {
            inFlightHitlOrders.delete(orderId);
            checkPendingHitlOrders();
            loadOrdersHistory();
        }
    }

    async function confirmAllHitlOrders() {
        if (!pendingHitlOrders || pendingHitlOrders.length === 0) return;
        if (!confirm(`ต้องการยืนยันส่งคำสั่งทั้งหมด (${pendingHitlOrders.length} รายการ) เข้าสู่ตลาดทันทีใช่หรือไม่?`)) return;
        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Submitting All...", async () => {
            for (const o of [...pendingHitlOrders]) {
                await confirmSingleHitlOrder(o.order_id);
            }
        });
    }

    async function rejectAllHitlOrders() {
        if (!pendingHitlOrders || pendingHitlOrders.length === 0) return;
        if (!confirm(`ต้องการยกเลิกคำสั่งทั้งหมด (${pendingHitlOrders.length} รายการ) ใช่หรือไม่?`)) return;
        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Cancelling All...", async () => {
            for (const o of [...pendingHitlOrders]) {
                await rejectSingleHitlOrder(o.order_id);
            }
        });
    }

    // Backwards-compatible aliases
    const confirmHitlOrder = () => pendingHitlOrders[0] && confirmSingleHitlOrder(pendingHitlOrders[0].order_id);
    const rejectHitlOrder = () => pendingHitlOrders[0] && rejectSingleHitlOrder(pendingHitlOrders[0].order_id);

    // --------------------------------------------------------------------------
    // Natural Language Tactical Action Exit Handlers (Pillar 6.3)
    // --------------------------------------------------------------------------
    function pasteSampleActionExit() {
        const sample = `🏛️ [พอร์ต Krungsri Margin - KSS]\n🚨 Action Exits วันนี้:\n• [Timeout] SAWAD (LONG): SELL 2,200 หุ้น @ 22.30 (+0.45% / +0.22x ATR) 👉 ครบ 10 วันทำการ ปิดล็อกกำไรปลดล็อกเงินสด\n• [Timeout] COCOCO (LONG): SELL 8,800 หุ้น @ 5.60 (-0.88% / -0.47x ATR) 👉 ครบ 10 วันทำการ ปิดรอบปลดล็อกเงินสด\n• [Weed-out] AAV (LONG): SELL 57,000 หุ้น @ 0.84 (-2.33% / -0.64x ATR) 👉 ถือ 7 วัน > 5D ขาดทุนเกิน -1.0% ตัดทิ้งคัดกรองไม้แย่`;
        const el = document.getElementById('actionExitTextInput');
        if (el) el.value = sample;
    }

    async function submitNaturalLanguageActionExit() {
        const input = document.getElementById('actionExitTextInput');
        const text = input ? input.value.trim() : '';
        if (!text) {
            alert('กรุณากรอกข้อความ Action Exit Briefing');
            return;
        }
        const btn = document.getElementById('btnParseActionExit');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="btn-spinner"></span> กำลังวิเคราะห์และตั้งเวลา Auto-Trade...';
        }
        try {
            const res = await fetch(`${API_BASE}/orders/action-exit/natural-language`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, auto_schedule: true })
            });
            const data = await res.json();
            if (data.success) {
                appendLog(`⏰ [Action Exit Auto-Scheduled] สำเร็จ ${data.queued_count} รายการ (Win: ${data.profitable_count} ไม้, Loss: ${data.losing_count} ไม้) สำหรับ ${data.broker} Margin -> ตั้งเวลาส่งอัตโนมัติเรียบร้อย!`, "info");
                showToast(`ตั้งเวลา Auto-Trade สำเร็จ ${data.queued_count} รายการ พร้อมยิงอัตโนมัติ!`);
                checkPendingHitlOrders();
                loadOrdersHistory();
            } else {
                appendLog(`❌ [Action Exit Error] ${data.message || data.error}`, "error");
                alert(data.message || data.error);
            }
        } catch (e) {
            appendLog(`❌ [Action Exit Failed] ${e.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '🚀 Parse & Auto-Schedule (ยิงอัตโนมัติตามเวลา)';
            }
        }
    }

    async function dispatchOrderNow(orderId) {
        if (!confirm(`ต้องการสั่งยิงคำสั่ง ${orderId} เข้าสู่ตลาดทันทีใช่หรือไม่?`)) return;
        try {
            const res = await fetch(`${API_BASE}/orders/action-exit/${orderId}/dispatch-now`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast(`ยิงคำสั่งสำเร็จ: ${data.broker_order_no || 'Submitted'}`);
                appendLog(`⚡ [Manual Dispatch] สั่งยิงคำสั่ง ${orderId} สำเร็จ: Order #${data.broker_order_no}`, "info");
                loadOrdersHistory();
            } else {
                showToast(`เกิดข้อผิดพลาด: ${data.message || data.error}`);
                appendLog(`❌ [Manual Dispatch Failed] ${data.message || data.error}`, "error");
            }
        } catch (e) {
            showToast(`Error: ${e.message}`);
        }
    }

    // --------------------------------------------------------------------------
    // Order Placement & Execution (Pillar 3) - Dynamic TypeSafe Asset Segregation
    // --------------------------------------------------------------------------
    function isTfexSymbol(sym) {
        if (!sym) return false;
        const s = sym.trim().toUpperCase();
        return /^(S50|GO|SV|USD|[A-Z]{2,6})([HMUZ]\d{2,4}|\d{2,4})$/i.test(s) || s.startsWith('S50') || s.startsWith('SET50') || s.includes('TFEX');
    }

    function onQuickAccountTypeChange() {
        const acc = document.getElementById('quickAccountType').value;
        const sym = document.getElementById('quickSymbol').value.trim().toUpperCase();
        const isDeriv = (acc === 'DERIVATIVES') || isTfexSymbol(sym);

        const sideSelect = document.getElementById('quickSide');
        const posCol = document.getElementById('quickPositionCol');
        const volLabel = document.getElementById('quickVolumeLabel');
        const volInput = document.getElementById('quickVolume');
        const hint = document.getElementById('quickGuardrailHint');

        if (isDeriv) {
            sideSelect.innerHTML = `
                <option value="LONG">LONG (เก็งขาขึ้น)</option>
                <option value="SHORT">SHORT (เก็งขาลง)</option>
            `;
            if (posCol) posCol.style.display = 'block';
            if (volLabel) volLabel.innerText = 'Volume (สัญญา)';
            if (volInput) { volInput.step = '1'; if (parseInt(volInput.value) > 10) volInput.value = '1'; }
            if (hint) hint.innerHTML = '🛡️ Guardrails: 1 contract minimum (TFEX Derivatives)';
        } else {
            sideSelect.innerHTML = `
                <option value="BUY">BUY (ซื้อ)</option>
                <option value="SELL">SELL (ขาย)</option>
                <option value="OPEN_SHORT">OPEN_SHORT (ยืมขาย SBL)</option>
                <option value="COVER">COVER (ซื้อคืน SBL)</option>
            `;
            if (posCol) posCol.style.display = 'none';
            if (volLabel) volLabel.innerText = 'Volume (หุ้น)';
            if (volInput) { volInput.step = '100'; if (parseInt(volInput.value) < 100) volInput.value = '100'; }
            if (hint) hint.innerHTML = '🛡️ Guardrails: Volume % 100 == 0 (Board lot required)';
        }
    }

    function onQuickSymbolInput() {
        const sym = document.getElementById('quickSymbol').value.trim().toUpperCase();
        const accSelect = document.getElementById('quickAccountType');
        if (isTfexSymbol(sym)) {
            if (accSelect.value !== 'DERIVATIVES') {
                accSelect.value = 'DERIVATIVES';
                onQuickAccountTypeChange();
            }
        } else if (sym.length >= 3 && !isTfexSymbol(sym)) {
            if (accSelect.value === 'DERIVATIVES') {
                accSelect.value = 'EQUITY';
                onQuickAccountTypeChange();
            }
        }
    }

    function setQuickPreset(symbol, side, vol, price, accType = 'EQUITY', position = 'AUTO') {
        document.getElementById('quickSymbol').value = symbol;
        document.getElementById('quickAccountType').value = accType;
        onQuickAccountTypeChange();
        document.getElementById('quickSide').value = side;
        const posEl = document.getElementById('quickPosition');
        if (posEl) posEl.value = position;
        document.getElementById('quickVolume').value = vol;
        document.getElementById('quickPrice').value = price;
        showToast(`Preset: ${side} ${vol} ${symbol} @ ฿${price} (${accType})`);
    }

    async function executeQuickOrder() {
        const broker = document.getElementById('quickBroker').value;
        const accountType = document.getElementById('quickAccountType').value;
        const symbol = document.getElementById('quickSymbol').value.trim().toUpperCase();
        const side = document.getElementById('quickSide').value;
        const posEl = document.getElementById('quickPosition');
        const position = (accountType === 'DERIVATIVES' || isTfexSymbol(symbol)) ? (posEl ? posEl.value : 'AUTO') : null;
        const volume = parseInt(document.getElementById('quickVolume').value);
        const price = parseFloat(document.getElementById('quickPrice').value);

        if (!symbol) { showToast("กรุณาระบุ Symbol"); return; }
        if (isNaN(volume) || volume <= 0) { showToast("Volume ไม่ถูกต้อง"); return; }
        if (isNaN(price) || price <= 0) { showToast("Price ไม่ถูกต้อง"); return; }

        const submitBtn = document.getElementById('btnExecuteQuickOrder') || window.event?.currentTarget;
        await withButtonLock(submitBtn, "Submitting Order...", async () => {
            const posText = position ? ` [${position}]` : '';
            appendLog(`⚡ Submitting Order: ${side}${posText} ${volume} ${symbol} @ ฿${price} on ${broker}...`);
            showToast(`กำลังส่งคำสั่ง ${side}${posText} ${symbol}...`);

            try {
                const res = await fetch(`${API_BASE}/orders/quick-execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        broker, account_type: accountType,
                        symbol, side, position, volume, price
                    })
                });
                const data = await res.json();
                if (data.success) {
                    appendLog(`✅ Order Submitted! Order ID: ${data.order_id || 'N/A'}, Status: ${data.status || 'DONE'}`, "success");
                    showToast(`ส่งคำสั่ง ${symbol} สำเร็จ (${data.status || 'DONE'})`);
                    checkPendingHitlOrders();
                    setTimeout(loadOrdersHistory, 1200);
                } else {
                    appendLog(`❌ Order Rejected / Failed: ${data.error || data.detail || 'Validation Guardrail'}`, "error");
                    showToast(`คำสั่งถูกปฏิเสธ: ${data.error || data.detail}`);
                }
            } catch (e) {
                appendLog(`❌ Execution exception: ${e.message}`, "error");
            }
        });
    }

    // --------------------------------------------------------------------------
    // Tactical Strategy (Pillar 6)
    // --------------------------------------------------------------------------
    async function triggerPriceNegotiation() {
        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Negotiating...", async () => {
            appendLog("🤝 Running Pillar 6.1: Price Negotiation Round...");
            showToast("กำลังรันการต่อราคาคำสั่งค้าง (Pillar 6.1)...");
            try {
                const res = await fetch(`${API_BASE}/phase3/negotiate`, { method: 'POST' });
                const data = await res.json();
                appendLog(`Negotiation complete: ${data.length || 0} order(s) evaluated`, "success");
                showToast(`ต่อราคาเสร็จสิ้น (${data.length || 0} รายการ)`);
                loadOrdersHistory();
            } catch (e) {
                appendLog(`Negotiation error: ${e.message}`, "error");
            }
        });
    }

    async function triggerEodCleanup() {
        if (!confirm("ยืนยันการเคลียร์คำสั่งค้างสิ้นวัน (EOD Cleanup)?")) return;
        const btn = window.event?.currentTarget;
        await withButtonLock(btn, "Cleaning...", async () => {
            appendLog("⏰ Running Pillar 6.2: EOD Cleanup...");
            showToast("กำลังยกเลิกคำสั่งค้างก่อนปิดวัน...");
            try {
                const res = await fetch(`${API_BASE}/orders/eod/expire`, { method: 'POST' });
                const data = await res.json();
                appendLog(`EOD Cleanup complete: Expired ${data.expired_count} pending day orders`, "warn");
                showToast(`ยกเลิกคำสั่งค้างเรียบร้อย (${data.expired_count} รายการ)`);
                loadOrdersHistory();
            } catch (e) {
                appendLog(`EOD Cleanup error: ${e.message}`, "error");
            }
        });
    }

    // --------------------------------------------------------------------------
    // Orders Database Journal
    // --------------------------------------------------------------------------
    async function loadOrdersHistory() {
        try {
            const res = await fetch(`${API_BASE}/orders?limit=30`);
            if (!res.ok) return;
            const orders = await res.json();
            const tbody = document.getElementById('ordersTableBody');

            if (orders.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 18px;">ยังไม่มีประวัติคำสั่งซื้อขายในระบบ</td></tr>`;
                return;
            }

            tbody.innerHTML = orders.map(o => {
                const side = o.side || o.action || 'BUY';
                const sideColor = (side === 'BUY' || side === 'COVER') ? '#34d399' : '#f87171';
                return `
                    <tr>
                        <td style="font-family: 'JetBrains Mono'; font-weight: 600; color: #94a3b8;">${o.order_id ? o.order_id.slice(0, 8) : '-'}</td>
                        <td style="color: ${sideColor}; font-weight: 700;">${side}</td>
                        <td style="font-weight: 700; font-family: 'JetBrains Mono';">${o.symbol}</td>
                        <td style="font-family: 'JetBrains Mono';">${(o.volume || 0).toLocaleString()}</td>
                        <td style="font-family: 'JetBrains Mono';">฿${(o.price || 0).toFixed(2)}</td>
                        <td>
                            <span class="status-pill status-${o.status}">${o.status}</span>
                            ${o.status === 'SCHEDULED' ? `<button onclick="dispatchOrderNow('${o.order_id}')" class="btn btn-purple btn-sm" style="font-size: 9px; padding: 2px 6px; margin-top: 4px; display: block; border-radius: 4px;">⚡ ยิงทันที</button>` : ''}
                        </td>
                        <td style="font-size: 11px; color: #93c5fd;">${o.source || 'CLICK2WIN'}</td>
                        <td style="font-size: 11px; color: var(--text-muted);">${o.error_message || o.strategy_note || '-'}</td>
                        <td style="font-size: 11px; color: var(--text-muted);">${o.created_at ? new Date(o.created_at).toLocaleTimeString() : '-'}</td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.warn("Load orders history error:", e);
        }
    }

    async function clearOrdersDatabase() {
        if (!confirm("ต้องการล้างประวัติคำสั่งและบันทึกทดสอบทั้งหมดในฐานข้อมูลใช่หรือไม่?")) return;
        try {
            const res = await fetch(`${API_BASE}/orders/clear`, { method: 'DELETE' });
            if (res.ok) {
                showToast("ล้างประวัติเรียบร้อยแล้ว");
                loadOrdersHistory();
            }
        } catch (e) {
            showToast(`เกิดข้อผิดพลาด: ${e.message}`);
        }
    }

    // --------------------------------------------------------------------------
    // Operations Cockpit Live-Event Stream (SSE)
    // --------------------------------------------------------------------------
    let sseSource = null;

    function initSSE() {
        if (sseSource) {
            try { sseSource.close(); } catch (e) {}
        }
        try {
            sseSource = new EventSource(`${API_BASE}/cockpit/stream`);
            sseSource.onopen = () => {
                appendLog("⚡ Connected to Operations Cockpit live-event stream", "success");
            };
            sseSource.addEventListener('hitl_order_pending', (e) => {
                try {
                    const evt = JSON.parse(e.data);
                    showToast(`⚠️ คำสั่งจริงรอยืนยัน: ${evt.symbol || ''} ${evt.side || ''}`);
                } catch (err) {
                    showToast("⚠️ มีคำสั่งซื้อขายจริงรอคุณกดยืนยันบนหน้าจอ!");
                }
                checkPendingHitlOrders();
                loadOrdersHistory();
            });
            sseSource.onerror = () => {};
        } catch (err) {
            console.warn("SSE init error:", err);
        }
    }


    async function triggerKillSwitch() {
        if (!confirm("🚨 ยืนยันการสั่ง EMERGENCY KILL SWITCH หรือไม่?\\nระบบจะหยุดการเทรดอัตโนมัติทั้งหมดทันที และส่งคำขอยกเลิกออเดอร์ค้างทั้งหมด!")) return;
        try {
            const res = await fetch("/api/v1/agentic/kill-switch/activate", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({reason: "Triggered from Web Console Emergency Button", triggered_by: "WEB_CONSOLE"})
            });
            const data = await res.json();
            showToast("🚨 EMERGENCY KILL SWITCH ACTIVATED!");
            appendLog(`🚨 EMERGENCY KILL SWITCH ACTIVATED: ${JSON.stringify(data)}`, "error");
            checkKillSwitchStatus();
        } catch(err) {
            alert("Error activating kill switch: " + err);
        }
    }

    async function resetKillSwitch() {
        if (!confirm("ยืนยันการปลดล็อก Emergency Kill Switch หรือไม่?")) return;
        try {
            const res = await fetch("/api/v1/agentic/kill-switch/reset", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({authorized_by: "WEB_CONSOLE"})
            });
            const data = await res.json();
            showToast("✅ Emergency Kill Switch Reset!");
            appendLog(`✅ Kill Switch Reset: ${JSON.stringify(data)}`, "success");
            checkKillSwitchStatus();
        } catch(err) {
            alert("Error resetting kill switch: " + err);
        }
    }

    async function checkKillSwitchStatus() {
        try {
            const res = await fetch("/api/v1/agentic/kill-switch/status");
            const data = await res.json();
            const panicBtn = document.getElementById("btnEmergencyPanic");
            const resetBtn = document.getElementById("btnResetKillSwitch");
            if (data.is_active) {
                panicBtn.innerText = "🚨 KILL SWITCH ACTIVE (FROZEN)";
                panicBtn.style.background = "#b91c1c";
                panicBtn.style.border = "2px solid #f87171";
                resetBtn.style.display = "inline-block";
            } else {
                panicBtn.innerText = "🚨 PANIC KILL SWITCH";
                panicBtn.style.background = "linear-gradient(135deg, #ef4444, #b91c1c)";
                panicBtn.style.border = "none";
                resetBtn.style.display = "none";
            }
        } catch(err) {}
    }

    // --------------------------------------------------------------------------
    // Krungsri SSO SBL Real-time Radar & Risk Shield Handlers
    // --------------------------------------------------------------------------
    async function loadSblRealtime() {
        try {
            const res = await fetch("/api/v1/simulation/live/probe/krungsri-sbl/cached");
            const data = await res.json();
            if (data.status === "SUCCESS" && data.data) {
                renderSblData(data.data);
            }
        } catch (e) {
            console.error("Error loading SBL cached:", e);
        }
    }

    async function syncSblOnDemand() {
        const btn = document.getElementById("btnSyncSbl");
        if (btn) {
            btn.disabled = true;
            btn.innerText = "⏳ กำลังดึงข้อมูลจาก Krungsri SBL...";
        }
        try {
            const res = await fetch("/api/v1/simulation/live/probe/krungsri-sbl/sync", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                renderSblData(data);
                showToast("✅ อัปเดตข้อมูล Krungsri SBL Real Time เรียบร้อยแล้ว!");
            } else {
                alert("SBL Sync Error: " + (data.error || "Unknown"));
            }
        } catch (e) {
            alert("SBL Sync Failed: " + e);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerText = "🔄 On-Demand Sync SBL";
            }
        }
    }

    function renderSblData(data) {
        if (!data) return;
        const pp = data.purchasing_power || 0;
        const ppBadge = document.getElementById("sblPpBadge");
        if (ppBadge) ppBadge.innerText = `PP: ฿${pp.toLocaleString('en-US', {minimumFractionDigits: 2})}`;

        const accBadge = document.getElementById("sblAccountBadge");
        if (accBadge) accBadge.innerText = `Acc: ${data.account_no || '302495'} (${data.account_name || 'คุณอารยะ สวัสดิชัย'})`;

        const counts = data.counts || {};
        if (document.getElementById("sblSet50Count")) document.getElementById("sblSet50Count").innerText = `${counts.set50 || 0} หุ้น`;
        if (document.getElementById("sblSet100Count")) document.getElementById("sblSet100Count").innerText = `${counts.set100 || 0} หุ้น`;
        if (document.getElementById("sblNewSecCount")) document.getElementById("sblNewSecCount").innerText = `${counts.newsec || 0} หุ้น`;
        if (document.getElementById("sblXdCount")) document.getElementById("sblXdCount").innerText = `${counts.xd_xr_risks || 0} หุ้นเสี่ยง`;

        const listEl = document.getElementById("sblBlockedSymbolsList");
        if (listEl && data.xd_xr_inventory) {
            listEl.innerHTML = "";
            data.xd_xr_inventory.forEach(item => {
                const badge = document.createElement("span");
                badge.style.cssText = "background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-family: 'JetBrains Mono', monospace; font-size: 11.5px;";
                badge.innerHTML = `⛔ ${item.symbol} <span style="font-weight: 400; opacity: 0.85;">(${item.type} ${item.book_date})</span>`;
                listEl.appendChild(badge);
            });
        }

        const updatedEl = document.getElementById("sblLastUpdated");
        if (updatedEl && data.timestamp) {
            const dt = new Date(data.timestamp);
            updatedEl.innerText = `Last Updated: ${dt.toLocaleString('th-TH')}`;
        }
    }

    async function checkSymbolSblRisk() {
        const input = document.getElementById("sblAuditSymbolInput");
        const badge = document.getElementById("sblAuditResultBadge");
        if (!input || !badge) return;
        const sym = (input.value || "").trim().toUpperCase();
        if (!sym) return;

        badge.innerHTML = "⏳ ตรวจสอบ...";
        badge.style.color = "#94a3b8";

        try {
            const res = await fetch(`/api/v1/simulation/live/probe/krungsri-sbl/check-risk?symbol=${sym}`);
            const data = await res.json();
            const r = data.risk_info;
            if (r.is_blocked) {
                badge.innerHTML = `<span style="color: #ef4444; background: rgba(239,68,68,0.15); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(239,68,68,0.3);">${r.badge}: ${r.reason}</span>`;
            } else {
                badge.innerHTML = `<span style="color: #10b981; background: rgba(16,185,129,0.15); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(16,185,129,0.3);">${r.badge}: ${r.reason}</span>`;
            }
        } catch (e) {
            badge.innerHTML = `<span style="color: #f59e0b;">Error: ${e}</span>`;
        }
    }

    // --------------------------------------------------------------------------
    // Pillar × Broker Feature Matrix + Component Toggles (2026-10-10)
    // --------------------------------------------------------------------------
    async function loadControlPanel() {
        await Promise.all([loadFeatureMatrix(), loadComponents()]);
    }

    async function loadFeatureMatrix() {
        const head = document.getElementById('featureMatrixHead');
        const body = document.getElementById('featureMatrixBody');
        if (!head || !body) return;
        try {
            const res = await fetch(`${API_BASE}/admin/feature-matrix`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const brokers = data.brokers || [];
            const meta = data.status_meta || {};

            let htr = '<tr><th style="text-align:left; padding:8px 10px; color:var(--text-secondary); border-bottom:1px solid var(--border-color);">Pillar</th>';
            brokers.forEach(b => {
                const dim = b.in_use ? '' : 'opacity:0.5;';
                htr += `<th style="text-align:center; padding:8px 10px; color:var(--text-secondary); border-bottom:1px solid var(--border-color); ${dim}">${b.name}</th>`;
            });
            head.innerHTML = htr + '</tr>';

            body.innerHTML = '';
            (data.pillars || []).forEach(p => {
                let row = `<td style="padding:8px 10px; border-bottom:1px solid var(--border-color); vertical-align:top;">
                    <div style="font-weight:700; color:var(--text-primary);">${p.pillar} · ${p.name}</div>
                    <div style="font-size:10.5px; color:var(--text-muted);">${p.notes || ''}</div>
                </td>`;
                brokers.forEach(b => {
                    const status = (p.cells && p.cells[b.key]) || 'na';
                    const m = meta[status] || { icon: '❔', label: status, color: '#94a3b8' };
                    row += `<td style="text-align:center; padding:8px 10px; border-bottom:1px solid var(--border-color);">
                        <span title="${m.label}" style="color:${m.color}; font-weight:700; font-size:14px;">${m.icon}</span>
                        <div style="font-size:9.5px; color:var(--text-muted);">${m.label}</div>
                    </td>`;
                });
                const tr = document.createElement('tr');
                tr.innerHTML = row;
                body.appendChild(tr);
            });
        } catch (e) {
            body.innerHTML = `<tr><td style="color:#f87171; padding:8px;">Feature matrix error: ${e.message}</td></tr>`;
        }
    }

    async function loadComponents() {
        const wrap = document.getElementById('componentToggles');
        if (!wrap) return;
        try {
            const res = await fetch(`${API_BASE}/admin/components`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            const modeBadge = document.getElementById('tradingModeBadge');
            if (modeBadge) {
                const mode = String(data.trading_mode || '?').toUpperCase();
                modeBadge.textContent = `MODE: ${mode}`;
                modeBadge.className = mode === 'LIVE' ? 'badge badge-red' : 'badge badge-blue';
                modeBadge.title = data.trading_mode_note || '';
            }

            const groupLabels = {};
            (data.groups || []).forEach(g => { groupLabels[g.key] = g.label; });

            wrap.innerHTML = '';
            (data.components || []).forEach(c => {
                const enabled = !!c.enabled;
                const card = document.createElement('div');
                card.style.cssText = 'background: var(--bg-secondary); border:1px solid var(--border-color); border-radius:10px; padding:12px 14px;';
                const badgeClass = c.restart_required ? 'badge-amber' : 'badge-green';
                const badgeText = c.restart_required ? '⏳ ต้อง Reload' : '⚡ มีผลทันที';
                card.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
                        <div>
                            <div style="font-size:13px; font-weight:700; color:var(--text-primary);">${c.label}</div>
                            <div style="font-size:10.5px; color:var(--text-muted); font-family:'JetBrains Mono',monospace;">${c.env_key}</div>
                        </div>
                        <input type="checkbox" ${enabled ? 'checked' : ''}
                            onchange="toggleComponent('${c.key}', this.checked, this)"
                            title="${enabled ? 'ON' : 'OFF'}"
                            style="width:20px; height:20px; accent-color:#10b981; cursor:pointer; flex:0 0 auto;">
                    </div>
                    <div style="font-size:11px; color:var(--text-secondary); margin-top:8px;">${c.description}</div>
                    <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
                        <span class="badge ${badgeClass}" style="font-size:10px;">${badgeText}</span>
                        <span class="badge" style="font-size:10px;">${groupLabels[c.group] || c.group}</span>
                    </div>`;
                wrap.appendChild(card);
            });
        } catch (e) {
            wrap.innerHTML = `<div style="color:#f87171; font-size:12px;">Component load error: ${e.message}</div>`;
        }
    }

    async function toggleComponent(key, enabled, el) {
        if (el) el.disabled = true;
        try {
            const res = await fetch(`${API_BASE}/admin/components/${key}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !!enabled })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            showToast(data.message || 'อัปเดตเรียบร้อย');
            appendLog(`[Component] ${data.env_written} (restart_required=${data.restart_required})`, 'success');
            await loadComponents();
        } catch (e) {
            if (el) el.checked = !enabled;  // revert on failure
            showToast(`❌ ${e.message}`);
            appendLog(`Component toggle failed: ${e.message}`, 'error');
        } finally {
            if (el) el.disabled = false;
        }
    }

    function reloadGateway() {
        if (!confirm('🔄 ยืนยันการ Reload Gateway หรือไม่?\n\nโปรเซส uvicorn จะถูก re-exec (os.execv) — คำสั่งจะถูกตัดชั่วครู่ แล้วหน้าเว็บ reconnect เองใน 1-3 วินาที')) return;
        const btn = document.getElementById('btnReloadGateway');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Reloading…'; }
        appendLog('🔄 Reloading gateway process (os.execv)…', 'warn');
        fetch(`${API_BASE}/admin/reload`, { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                showToast(d.message || 'กำลัง reload…');
                appendLog(`Reload scheduled: ${d.command}`, 'warn');
                let tries = 0;
                const iv = setInterval(async () => {
                    tries += 1;
                    try {
                        const h = await fetch('/health', { cache: 'no-store' });
                        if (h.ok) {
                            clearInterval(iv);
                            appendLog('✅ Gateway back online — reloading page', 'success');
                            setTimeout(() => location.reload(), 400);
                        }
                    } catch (e) { /* gateway still restarting */ }
                    if (tries > 40) {
                        clearInterval(iv);
                        appendLog('⚠️ Gateway ไม่กลับมาภายใน ~20 วินาที', 'error');
                        if (btn) { btn.disabled = false; btn.textContent = '🔄 Reload'; }
                    }
                }, 500);
            })
            .catch(e => {
                showToast(`Reload error: ${e.message}`);
                appendLog(`Reload error: ${e.message}`, 'error');
                if (btn) { btn.disabled = false; btn.textContent = '🔄 Reload'; }
            });
    }

    // --------------------------------------------------------------------------
    // Initial Load
    // --------------------------------------------------------------------------
    checkUnifiedHealth();
    loadControlPanel();
    loadOrdersHistory();
    initSSE();
    checkKillSwitchStatus();
    loadSblRealtime();

    // High frequency health refresh
    setInterval(() => {
        checkUnifiedHealth();
        checkKillSwitchStatus();
    }, 3000);
</script>
</body>
</html>
"""
