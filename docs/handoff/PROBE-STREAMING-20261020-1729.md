# Handoff: DOM Probe Report — STREAMING

- **Date**: 2026-10-20 17:29:01
- **Target**: `streaming`
- **Source URL**: `https://wma2.settrade.com/realtime/streaming7/StreamingPage.jsp`
- **Page Title**: `Settrade Streaming for PC - wwwe15.settrade.com`
- **Raw Probe JSON**: `probe_streaming_20261020_172854.json`

## 1. Discovered Selectors & Elements

| Suggested Selector | Tag | Visible | Sample Text | Role / TestID |
|---|---|---|---|---|
| `#root` | `div` | ✅ | Market Portfolio Quote TFEX Click Bids O | `-` |
| `#streaming-container` | `div` | ✅ | Market Portfolio Quote TFEX Click Bids O | `-` |
| `#equity-place-order-short-radio-button` | `input` | ✅ | H | `placeOrderRadio` |
| `#equity-place-order-cover-radio-button` | `input` | ✅ | C | `placeOrderRadio` |
| `div.outline-none` | `div` | ✅ | Order No. Date Time Symbol Side Price Vo | `-` |
| `div[aria-label="grid"]` | `div` | ✅ | 11009293 20/10 10:20:07 CPF Cover 20.30  | `grid` |

## 2. Recommended Next Steps for Implementation Agent
- Verify element interactions using persistent CDP session without re-authenticating.
- Add scraper/action logic in `app/brokers/streaming/` or `app/browser/` using the verified selectors above.
- Verify changes with: `.venv/bin/python scripts/verify_changes.py <changed_file>`
