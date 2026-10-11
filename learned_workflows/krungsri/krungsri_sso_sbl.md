# Krungsri SSO SBL Program Navigation Runbook

- **Generated At**: 2026-10-03 12:18:19
- **Platform**: Krungsri Securities Member SSO Portal
- **Authentication**: Pre-authenticated session state (`data/session_state.json`)
- **Methodology**: Watch-and-Learn Interactive Co-pilot Protocol

## Verified Navigation Steps

| Step | Action | Target / Selector | Description |
| :--- | :--- | :--- | :--- |
| 1 | `NAVIGATE` | `https://www.krungsrisecurities.com/th/main/default.aspx` | Open Krungsri Member Portal |
| 2 | `CLICK` | `a.disclaimer[href*='SBL/start.aspx']` | Clicked a.disclaimer[href*='SBL/start.aspx'] on https://www.krungsrisecurities.com/th/discliaimer-sbl/Default.aspx?start=sbl |

## Code Usage Example
```python
# To execute this verified workflow autonomously in production:
from app.browser.auth_driver import auth_driver

# 1. Launch browser with saved session
page = await auth_driver.launch_browser(resume_state=True)
# 2. Navigate to portal
await page.goto('https://www.krungsrisecurities.com/th/main/default.aspx')
```
