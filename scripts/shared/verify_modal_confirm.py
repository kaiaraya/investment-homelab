import asyncio
from app.browser.click2win_driver import click2win_driver

async def main():
    print("Placing order via click2win_driver...")
    res = await click2win_driver.execute_order(
        symbol="BDMS",
        side="BUY",
        volume=100,
        price=20.00,
        account_type="EQUITY",
        pin="111111"
    )
    print("Execute order result:", res)

    page = click2win_driver.page
    if page:
        shot = "data/screenshots/after_modal_confirm.png"
        await page.screenshot(path=shot)
        print(f"Saved screenshot after confirm to: {shot}")

asyncio.run(main())
