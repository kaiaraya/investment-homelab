#!/usr/bin/env python3
"""
Python-Native Playwright Model Context Protocol (MCP) Server.
Enables AI Agents (such as Antigravity IDE) to interactively control a visible
Google Chrome browser window, inspect live TradeMan DOM, co-pilot workflows with the user,
and compile verified procedures into `learned_workflows/*.md` for autonomous execution.
"""

import sys
import os
import re
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure logging to STDERR (CRITICAL: STDOUT is strictly reserved for JSON-RPC messages!)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [MCP] [%(levelname)s] %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("PlaywrightMCPServer")

from app.core.config import settings
from app.browser.broker_factory import get_broker_driver, get_auth_driver
from app.browser.popup_manager import popup_manager
from app.services.workflow_engine import workflow_engine

RECORDED_BUFFER: Dict[str, List[Dict[str, Any]]] = {}


# ==============================================================================
# TOOL DEFINITIONS (Model Context Protocol Schema)
# ==============================================================================

TOOLS = [
    {
        "name": "browser_open",
        "description": "Opens or attaches to the visible Google Chrome browser window on desktop, restoring saved TradeMan session cookies if available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL to open (default: https://trademan.in.th)", "default": "https://trademan.in.th"},
                "headed": {"type": "boolean", "description": "Run in visible headed window so user can watch (default: true)", "default": True}
            }
        }
    },
    {
        "name": "browser_navigate",
        "description": "Navigates the active browser page to a specific URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The destination URL to navigate to."}
            },
            "required": ["url"]
        }
    },
    {
        "name": "browser_screenshot",
        "description": "Captures a high-resolution screenshot of the visible browser window for visual verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Descriptive name for the screenshot file."}
            }
        }
    },
    {
        "name": "browser_snapshot",
        "description": "Extracts interactive DOM elements (buttons, inputs, links, tables) with clean CSS selectors and visible text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_elements": {"type": "integer", "description": "Maximum interactive elements to return (default: 50)", "default": 50}
            }
        }
    },
    {
        "name": "browser_click",
        "description": "Clicks on an element specified by CSS selector or text with automatic popup dismiss checks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector or text selector (e.g. 'button:has-text(\"Login\")')."}
            },
            "required": ["selector"]
        }
    },
    {
        "name": "browser_type",
        "description": "Types text into an input field with human-like anti-bot keystroke delays.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector for the input element."},
                "text": {"type": "string", "description": "Text to type."},
                "delay_ms": {"type": "integer", "description": "Delay between keystrokes in ms (default: 70)", "default": 70}
            },
            "required": ["selector", "text"]
        }
    },
    {
        "name": "browser_evaluate",
        "description": "Executes a JavaScript expression in the context of the active browser page and returns the result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "JavaScript code to execute."}
            },
            "required": ["script"]
        }
    },
    {
        "name": "browser_wait_for",
        "description": "Waits for a selector to become visible or for a specified duration in milliseconds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to wait for (optional)."},
                "timeout_ms": {"type": "integer", "description": "Time in ms to wait (default: 3000)", "default": 3000}
            }
        }
    },
    {
        "name": "trademan_check_session",
        "description": "Checks the active broker session status, account equity, and market values.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "switch_platform",
        "description": "Switches the active trading platform between 'CLICK2WIN' (Settrade sandbox) and 'TRADEMAN' (Krungsri live).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["CLICK2WIN", "TRADEMAN"],
                    "description": "Target platform ('CLICK2WIN' or 'TRADEMAN')"
                }
            },
            "required": ["platform"]
        }
    },
    {
        "name": "broker_login",
        "description": "Performs automated login for the active platform (Click2Win username/pwd, or Krungsri TradeMan login + OTP prompt).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["CLICK2WIN", "TRADEMAN"],
                    "description": "Optional platform to login to (defaults to active platform)."
                }
            }
        }
    },
    {
        "name": "scrape_portfolio",
        "description": "Scrapes current portfolio holdings (Symbol, Volume, Avg Cost, Market Price, Unrealized PnL) from the active platform.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "scrape_sbl_inventory",
        "description": "Scrapes SBL borrowable inventory and loan pool availability (TradeMan Krungsri only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Optional stock symbol to filter (e.g. 'DELTA', 'AOT')."
                }
            }
        }
    },
    {
        "name": "scrape_orders",
        "description": "Lists ALL orders sent to the broker (Krungsri TradeMan / Liberator), each classified as Matched / Partially-Matched / Unmatched / Cancelled / Rejected.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "description": "Target platform: 'KRUNGSRI' or 'LIBERATOR'. Defaults to the active platform."},
                "account_type": {"type": "string", "description": "Krungsri account type: 'CASH' or 'MARGIN' (ignored for Liberator)."},
                "include_closed": {"type": "boolean", "description": "Include terminal Cancelled/Rejected rows (default: true).", "default": True}
            }
        }
    },
    {
        "name": "record_workflow_step",
        "description": "Buffers an interactive interaction step into the current learning session before saving to .md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_name": {"type": "string", "description": "Name of the workflow being learned."},
                "action": {"type": "string", "description": "Action type (CLICK, TYPE, WAIT, NAVIGATE, CHECK)."},
                "selector": {"type": "string", "description": "Target CSS/Text selector."},
                "value": {"type": "string", "description": "Optional value or parameter for this step."},
                "description": {"type": "string", "description": "Human-readable description of what this step accomplishes."}
            },
            "required": ["workflow_name", "action", "selector"]
        }
    },
    {
        "name": "save_learned_workflow",
        "description": "Compiles buffered or provided steps into a clean markdown runbook in `learned_workflows/<name>.md`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Identifier name for the workflow (e.g. 'sbl_borrow_inquiry')."},
                "title": {"type": "string", "description": "Title of the workflow."},
                "description": {"type": "string", "description": "Detailed explanation of what this workflow accomplishes."},
                "steps": {
                    "type": "array",
                    "description": "Optional explicit list of step dicts; if omitted, uses buffered steps.",
                    "items": {"type": "object"}
                },
                "validation_rules": {
                    "type": "array",
                    "description": "List of health verification conditions.",
                    "items": {"type": "string"}
                }
            },
            "required": ["name", "title", "description"]
        }
    },
    {
        "name": "workflow_run_autonomous",
        "description": "Executes a learned workflow autonomously from its `.md` specification, detecting anomalies and notifying LINE if UI changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the workflow to run."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "workflow_list",
        "description": "Lists all available learned workflows (.md files) and their statuses.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "workflow_get_anomalies",
        "description": "Retrieves any workflows flagged with NEEDS_RELEARN due to UI shifts or broken selectors.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


# ==============================================================================
# TOOL IMPLEMENTATIONS
# ==============================================================================

async def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    """Executes the requested tool and returns a human/agent readable text response."""
    logger.info(f"Invoking tool '{name}' with args: {args}")

    auth = get_auth_driver()
    broker = get_broker_driver()
    platform = getattr(settings, "TRADING_PLATFORM", "CLICK2WIN").upper().strip()

    if name == "browser_open":
        default_url = settings.CLICK2WIN_URL if platform == "CLICK2WIN" else settings.TRADEMAN_URL
        target_url = args.get("url") or default_url
        headed = args.get("headed", True)
        settings.PLAYWRIGHT_HEADLESS = not headed

        page = await auth.launch_browser(resume_state=True)
        if target_url and page.url != target_url:
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                logger.warning(f"Initial navigation notice: {e}")

        await popup_manager.dismiss_popups(page)
        title = await page.title()
        return (
            f"Browser opened successfully in Headed mode (Visible on desktop screen).\n"
            f"• Platform: {platform}\n"
            f"• Current URL: {page.url}\n"
            f"• Page Title: '{title}'\n"
            f"• Session Authenticated: {auth.is_authenticated}"
        )

    if name == "switch_platform":
        target_platform = args["platform"].upper().strip()
        settings.TRADING_PLATFORM = target_platform
        return f"✅ Switched active trading platform to: {target_platform}\nNext browser operations will use {target_platform} drivers."

    page = auth.page
    is_closed = False
    if page and hasattr(page, "is_closed"):
        res = page.is_closed() if callable(page.is_closed) else page.is_closed
        if asyncio.iscoroutine(res):
            is_closed = await res
        else:
            is_closed = bool(res)

    if not page or is_closed:
        # Auto-launch browser if not active
        page = await auth.launch_browser(resume_state=True)

    if name == "browser_navigate":
        url = args["url"]
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await popup_manager.dismiss_popups(page)
        return f"Navigated to {url}. Title: '{await page.title()}'"

    elif name == "browser_screenshot":
        base_name = args.get("name") or f"screenshot_{int(datetime.now().timestamp())}"
        clean_name = re.sub(r'[^\w\-]', '_', base_name)
        out_dir = os.path.join(PROJECT_ROOT, "data", "screenshots")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{clean_name}.png")
        await page.screenshot(path=out_path, full_page=False)
        return f"Screenshot saved successfully:\nPath: {out_path}\nURL: {page.url}"

    elif name == "browser_snapshot":
        max_elem = args.get("max_elements", 50)
        await popup_manager.dismiss_popups(page)

        # Extract interactive elements from DOM
        elements = await page.evaluate("""() => {
            const items = [];
            const interactive = document.querySelectorAll('button, a, input, select, [role="button"], tr[data-symbol], th');
            for (let i = 0; i < interactive.length; i++) {
                const el = interactive[i];
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden') {
                    let selector = el.id ? '#' + el.id : (el.name ? `input[name="${el.name}"]` : el.tagName.toLowerCase());
                    if (el.innerText && el.innerText.trim().length > 0 && el.innerText.trim().length < 30) {
                        selector += `:has-text("${el.innerText.trim()}")`;
                    }
                    items.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || '').trim().replace(/\\s+/g, ' ').slice(0, 50),
                        selector: selector,
                        type: el.type || ''
                    });
                }
            }
            return items;
        }""")

        limited = elements[:max_elem]
        lines = [f"Found {len(elements)} visible elements (showing first {len(limited)}):"]
        for i, el in enumerate(limited, 1):
            txt = f" (text: '{el['text']}')" if el['text'] else ""
            lines.append(f"{i:2d}. <{el['tag']}> {el['selector']}{txt}")

        return "\n".join(lines)

    elif name == "browser_click":
        sel = args["selector"]
        await popup_manager.dismiss_popups(page)
        el = await page.wait_for_selector(sel, state="visible", timeout=8000)
        if not el:
            return f"Error: Element '{sel}' not found or not visible."
        await el.click()
        await page.wait_for_timeout(600)
        await popup_manager.dismiss_popups(page)
        return f"Successfully clicked element: {sel}"

    elif name == "browser_type":
        sel = args["selector"]
        text = args["text"]
        delay = args.get("delay_ms", 70)
        el = await page.wait_for_selector(sel, state="visible", timeout=8000)
        if not el:
            return f"Error: Input element '{sel}' not found."
        await el.fill("")
        await el.type(text, delay=delay)
        return f"Typed '{text}' into {sel} (delay={delay}ms/char)."

    elif name == "browser_evaluate":
        res = await page.evaluate(args["script"])
        return f"JavaScript execution result:\n{json.dumps(res, default=str, indent=2)}"

    elif name == "browser_wait_for":
        sel = args.get("selector")
        timeout = args.get("timeout_ms", 3000)
        if sel:
            await page.wait_for_selector(sel, state="visible", timeout=timeout)
            return f"Finished waiting for visible selector: {sel}"
        else:
            await page.wait_for_timeout(timeout)
            return f"Finished waiting for {timeout}ms."

    elif name in ("trademan_check_session", "broker_check_session"):
        is_auth = await auth.verify_saved_session()
        acc = await broker.scrape_account_summary()
        market_str = ""
        if hasattr(broker, "scrape_set_index_summary"):
            try:
                market = await broker.scrape_set_index_summary()
                market_str = f"\n• SET Index: {market.get('current_index', 0):,.2f} ({market.get('pct_change', 0):+.2f}%)"
            except Exception:
                pass
        return (
            f"Broker Session State ({platform}):\n"
            f"• Authenticated: {is_auth}\n"
            f"• Active URL: {page.url}\n"
            f"• Account: EE ฿{acc.get('excess_equity', 0):,.2f} | Cash ฿{acc.get('cash_balance', 0):,.2f}{market_str}"
        )

    elif name == "broker_login":
        target_plat = args.get("platform", platform).upper().strip()
        if target_plat != platform:
            settings.TRADING_PLATFORM = target_plat
            auth = get_auth_driver()
            broker = get_broker_driver()
            platform = target_plat

        if platform == "CLICK2WIN":
            success = await auth.login(
                username=settings.CLICK2WIN_USERNAME,
                password=settings.CLICK2WIN_PASSWORD,
                pin=settings.CLICK2WIN_PIN
            )
            return (
                f"Click2Win Login: {'SUCCESS ✅' if success else 'FAILED ❌'}\n"
                f"• URL: {auth.current_url}\n"
                f"• Authenticated: {auth.is_authenticated}"
            )
        else:
            login_result = await auth.login(
                username=settings.KRUNGSRI_USERNAME,
                password=settings.KRUNGSRI_PASSWORD
            )
            return (
                f"Krungsri TradeMan Login Result: {json.dumps(login_result, default=str)}\n"
                f"• Authenticated: {auth.is_authenticated}"
            )

    elif name == "scrape_portfolio":
        holdings = await broker.scrape_portfolio()
        if not holdings:
            return f"Portfolio Holdings on {platform}: 0 positions found (empty or table not visible)."
        lines = [f"📊 Portfolio Holdings on {platform} ({len(holdings)} positions):"]
        for i, pos in enumerate(holdings, 1):
            sym = pos.get("symbol", "N/A")
            vol = pos.get("volume") or pos.get("actual_volume") or 0
            avg = pos.get("avg_cost") or pos.get("avg_price") or 0
            curr = pos.get("market_price") or pos.get("current_price") or 0
            pnl = pos.get("unrealized_pnl_pct", 0)
            lines.append(f"{i}. {sym}: {vol:,} shares @ ฿{avg:.2f} (Current: ฿{curr:.2f}, PnL: {pnl:+.2f}%)")
        return "\n".join(lines)

    elif name == "scrape_sbl_inventory":
        if platform != "TRADEMAN":
            return f"Notice: SBL Borrow Inventory is only available on Krungsri TradeMan (Current platform: {platform}). Switch to TRADEMAN to inspect SBL."
        sym = args.get("symbol")
        lots = await broker.scrape_sbl_borrow_inventory(symbol=sym) if hasattr(broker, "scrape_sbl_borrow_inventory") else await broker.scrape_sbl_lots()
        return f"📈 SBL Borrow Inventory ({len(lots)} items):\n{json.dumps(lots, indent=2, default=str)}"

    elif name == "scrape_orders":
        # Order Ledger: all orders sent to the broker with Matched/Unmatched split.
        # Routes through Pillar 2 which handles KRUNGSRI (TradeMan) and LIBERATOR.
        from app.mcp.pillars.pillar2_portfolio import current_orders
        tgt_platform = str(args.get("platform") or platform).upper().strip()
        res = await current_orders(
            platform=tgt_platform,
            account_type=args.get("account_type"),
            include_closed=args.get("include_closed", True),
        )
        if not res.get("success"):
            return f"⚠️ Order Ledger unavailable: {res.get('message') or res.get('error') or 'unknown error'}"
        lines = [
            f"📋 Order Ledger — {res['platform']} ({res['account_type']})",
            f"• Total: {res['total']} | Matched: {res['matched_count']} | Partial: {res['partially_matched_count']} "
            f"| Unmatched: {res['unmatched_count']} | Cancelled: {res['cancelled_count']} | Rejected: {res['rejected_count']}",
        ]
        if not res["orders"]:
            lines.append("(no orders found)")
        for i, o in enumerate(res["orders"], 1):
            mv = o.get("matched_volume", 0)
            vol = o.get("volume", 0)
            bal = o.get("balance", 0)
            row = (
                f"{i}. [{o['status_category']}] {o.get('side','')} {o.get('symbol','')} "
                f"{mv}/{vol} filled (bal {bal}) @ ฿{float(o.get('price', 0) or 0):.2f} "
                f"#{o.get('broker_order_no','')}"
            )
            if o.get("time"):
                row += f" {o['time']}"
            lines.append(row)
        return "\n".join(lines)

    elif name == "record_workflow_step":
        wf_name = args["workflow_name"]
        step_item = {
            "action": args["action"].upper(),
            "selector": args["selector"],
            "value": args.get("value", ""),
            "description": args.get("description", "")
        }
        if wf_name not in RECORDED_BUFFER:
            RECORDED_BUFFER[wf_name] = []
        RECORDED_BUFFER[wf_name].append(step_item)
        idx = len(RECORDED_BUFFER[wf_name])
        return f"Buffered step {idx} for '{wf_name}': {step_item['action']} on `{step_item['selector']}`"

    elif name == "save_learned_workflow":
        wf_name = args["name"]
        title = args["title"]
        desc = args["description"]
        steps = args.get("steps") or RECORDED_BUFFER.get(wf_name, [])
        validations = args.get("validation_rules")

        if not steps:
            return f"Error: No steps provided and no steps buffered for workflow '{wf_name}'."

        saved_path = workflow_engine.save_workflow_spec(
            name=wf_name,
            title=title,
            description=desc,
            steps=steps,
            validation_rules=validations
        )
        if wf_name in RECORDED_BUFFER:
            del RECORDED_BUFFER[wf_name]

        return f"Successfully compiled and saved workflow spec:\nPath: {saved_path}\nTotal Steps: {len(steps)}"

    elif name == "workflow_run_autonomous":
        res = await workflow_engine.execute_workflow(args["name"])
        return f"Workflow Execution Result:\n{json.dumps(res, indent=2, default=str)}"

    elif name == "workflow_list":
        wfs = workflow_engine.list_workflows()
        return f"Available Learned Workflows in `learned_workflows/`:\n" + "\n".join(f"• {w}.md" for w in wfs)

    elif name == "workflow_get_anomalies":
        anomalies = await workflow_engine.get_active_anomalies()
        if not anomalies:
            return "No active workflow anomalies found. All workflows are in healthy state."
        return f"Active Workflow Anomalies (Require Re-learning):\n{json.dumps(anomalies, indent=2)}"

    return f"Error: Unknown tool name '{name}'"


# ==============================================================================
# JSON-RPC 2.0 PROTOCOL LOOP (STDIO)
# ==============================================================================

async def main():
    logger.info("Playwright MCP Server starting (listening on STDIN/STDOUT)...")
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line_bytes = await reader.readline()
            if not line_bytes:
                break

            line_str = line_bytes.decode("utf-8").strip()
            if not line_str:
                continue

            try:
                req = json.loads(line_str)
            except json.JSONDecodeError as err:
                logger.error(f"Malformed JSON-RPC: {err}")
                continue

            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            # 1. Initialize Handshake
            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "playwright-homelab",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()

            # 2. Notifications (e.g. notifications/initialized)
            elif method == "notifications/initialized":
                logger.info("Client handshake initialized successfully.")

            # 3. List Tools
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()

            # 4. Call Tool
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                try:
                    tool_output = await handle_tool_call(tool_name, tool_args)
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": tool_output
                                }
                            ]
                        }
                    }
                except Exception as ex:
                    logger.error(f"Tool execution error ({tool_name}): {ex}", exc_info=True)
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error executing tool '{tool_name}': {str(ex)}"
                                }
                            ],
                            "isError": True
                        }
                    }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()

            # 5. Ping
            elif method == "ping":
                res = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()

            else:
                # Unsupported method
                if req_id is not None:
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method '{method}' not found"
                        }
                    }
                    sys.stdout.write(json.dumps(res) + "\n")
                    sys.stdout.flush()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in MCP main loop: {e}", exc_info=True)

    logger.info("Playwright MCP Server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
