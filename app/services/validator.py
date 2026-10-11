from decimal import Decimal, ROUND_HALF_UP
import time
from typing import Tuple, Dict, Optional
from app.core.config import settings


class PreTradeValidator:
    """
    Pre-trade Risk & Board Lot Validation Engine for the Stock Exchange of Thailand (SET).
    Enforces Odd-lot rules, official SET tick sizes, max order value ceilings, and duplicate guards.
    """
    def __init__(self):
        # Cache for idempotency: key -> timestamp
        self._recent_orders: Dict[str, float] = {}

    def get_set_tick_size(self, price: float) -> Decimal:
        """
        Returns official SET Tick Size for a given price band:
        - Price < 2.00 -> 0.01
        - 2.00 <= Price < 5.00 -> 0.02
        - 5.00 <= Price < 10.00 -> 0.05
        - 10.00 <= Price < 25.00 -> 0.10
        - 25.00 <= Price < 100.00 -> 0.25
        - 100.00 <= Price < 200.00 -> 0.50
        - 200.00 <= Price < 400.00 -> 1.00
        - Price >= 400.00 -> 2.00
        """
        p = Decimal(str(price))
        if p < Decimal("2.00"):
            return Decimal("0.01")
        elif p < Decimal("5.00"):
            return Decimal("0.02")
        elif p < Decimal("10.00"):
            return Decimal("0.05")
        elif p < Decimal("25.00"):
            return Decimal("0.10")
        elif p < Decimal("100.00"):
            return Decimal("0.25")
        elif p < Decimal("200.00"):
            return Decimal("0.50")
        elif p < Decimal("400.00"):
            return Decimal("1.00")
        else:
            return Decimal("2.00")

    def is_tfex_symbol(self, symbol: Optional[str]) -> bool:
        """Determines if a symbol is a TFEX derivative (Futures, Options)."""
        if not symbol:
            return False
        import re
        s = symbol.upper().strip()
        return bool(re.search(r'^[A-Z0-9]+[HMUZ]\d{2}$', s) or s.startswith("S50") or "TFEX" in s)

    def validate_board_lot(self, volume: int, symbol: Optional[str] = None) -> Tuple[bool, str | None]:
        """
        Board Lot enforcement:
        - TFEX Derivatives: Traded in units of 1 contract (volume >= 1).
        - SET Equity: Requires volume % 100 == 0 (Board lot required).
        """
        if volume <= 0:
            return False, f"Volume must be positive, got {volume}"
        if symbol and self.is_tfex_symbol(symbol):
            return True, None
        if volume % 100 != 0:
            return False, f"Odd-lot rejected: Volume {volume} is not a multiple of 100 (Board lot required)"
        return True, None

    def validate_tick_size(self, price: float) -> Tuple[bool, str | None]:
        """
        Verifies that the price conforms to the official SET spread tick size.
        """
        if price <= 0:
            return False, f"Price must be positive, got {price}"
            
        p = Decimal(str(price))
        tick = self.get_set_tick_size(price)
        
        # Check remainder using Decimal division
        remainder = (p / tick) % Decimal("1")
        if remainder != Decimal("0"):
            return False, (
                f"Tick size violation: Price {price:.2f} THB does not match SET tick size "
                f"{tick} for this price bracket"
            )
        return True, None

    def validate_order_value(self, volume: int, price: float) -> Tuple[bool, str | None]:
        """
        Ceiling safeguard against massive accidental typo orders.
        """
        total_value = volume * price
        if total_value > settings.MAX_ORDER_VALUE_THB:
            return False, (
                f"Risk ceiling exceeded: Order value ฿{total_value:,.2f} exceeds "
                f"maximum allowed ฿{settings.MAX_ORDER_VALUE_THB:,.2f}"
            )
        return True, None

    def check_idempotency(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        record: bool = True
    ) -> Tuple[bool, str | None]:
        """
        Deduplication guard preventing duplicate orders fired within a short window.
        """
        now = time.time()
        order_key = f"{symbol.upper()}:{side.upper()}:{volume}:{price:.2f}"
        
        # Clean expired keys
        window = settings.ORDER_IDEMPOTENCY_WINDOW_SEC
        self._recent_orders = {
            k: t for k, t in self._recent_orders.items() if now - t < window
        }
        
        if order_key in self._recent_orders:
            elapsed = now - self._recent_orders[order_key]
            return False, (
                f"Duplicate order blocked: Identical order for {symbol} {side} was submitted "
                f"{elapsed:.1f}s ago (Cooldown window is {window}s)"
            )
            
        # Record this order only if requested
        if record:
            self._recent_orders[order_key] = now
        return True, None

    def clear_idempotency_cache(self) -> None:
        """Clears idempotency cache for testing or maintenance."""
        self._recent_orders.clear()

    def get_next_tick(self, price: float, steps: int = 1) -> float:
        """
        Calculates the next price tick up (+steps) or down (-steps) according to SET tick size rules.
        """
        current_p = Decimal(str(price))
        if steps == 0:
            return float(current_p)
            
        direction = 1 if steps > 0 else -1
        for _ in range(abs(steps)):
            if direction > 0:
                tick = self.get_set_tick_size(float(current_p))
                current_p += tick
            else:
                # When stepping down, tick depends on the bracket below
                tick = self.get_set_tick_size(float(current_p))
                test_p = current_p - tick
                if test_p > 0:
                    current_p = test_p
                else:
                    break
        return float(current_p)

    def validate_short_uptick(self, price: float, last_trade_price: Optional[float]) -> Tuple[bool, str | None]:
        """
        SET Short Sale Uptick rule (STRICT):

        A short sale price must be STRICTLY ABOVE the last traded price.
        Equality is NOT accepted (no "zero-plus tick") - to short you must move
        the price at least one tick above the last trade. The minimum legal
        price is therefore ``get_next_tick(last_trade_price, steps=1)``.
        """
        if last_trade_price is None or last_trade_price <= 0:
            return True, None
            
        if price <= last_trade_price:
            minimum = self.get_next_tick(last_trade_price, steps=1)
            return False, (
                f"SET Short Sale Rule Violation: Short price {price:.2f} must be strictly "
                f"above the last trading price {last_trade_price:.2f} (minimum ฿{minimum:.2f}) "
                f"- the zero-plus tick (equal price) is not accepted"
            )
        return True, None

    def validate_asset_action(
        self,
        symbol: str,
        side: str,
        position: Optional[str] = None
    ) -> Tuple[bool, str | None]:
        """
        Enforces strict TypeSafe asset segregation between SET Equity and TFEX Derivatives:
        - TFEX: side must be 'LONG' or 'SHORT'. Position must be in ['OPEN', 'CLOSE', 'AUTO'].
          Legacy terms ('BUY', 'SELL', 'COVER', 'OPEN_SHORT') are rejected.
        - Equity: side must be in ['BUY', 'SELL', 'OPEN_SHORT', 'COVER'].
          Derivatives terms ('LONG') are rejected.
        """
        s = side.strip().upper()
        pos = position.strip().upper() if position else None
        is_tfex = self.is_tfex_symbol(symbol)

        if is_tfex:
            if s not in ["LONG", "SHORT"]:
                return False, (
                    f"Strict TypeSafe Rejection: TFEX symbol '{symbol}' requires side in ['LONG', 'SHORT']. "
                    f"Action '{side}' is an Equity action and is rejected under Strict Asset Segregation."
                )
            if pos and pos not in ["OPEN", "CLOSE", "AUTO"]:
                return False, (
                    f"Strict TypeSafe Rejection: TFEX position must be in ['OPEN', 'CLOSE', 'AUTO'], got '{position}'."
                )
        else:
            if s in ["LONG"]:
                return False, (
                    f"Strict TypeSafe Rejection: Equity symbol '{symbol}' requires side in ['BUY', 'SELL', 'OPEN_SHORT', 'COVER']. "
                    f"Action '{side}' is a TFEX action and cannot be used for Equity."
                )
            if s not in ["BUY", "SELL", "OPEN_SHORT", "COVER", "SHORT"]:
                return False, (
                    f"Strict TypeSafe Rejection: Unknown Equity side '{side}'."
                )

        return True, None

    def validate_all(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        position: Optional[str] = None,
        record_idempotency: bool = True,
        last_trade_price: Optional[float] = None
    ) -> Tuple[bool, str | None]:
        """
        Runs all pre-trade validations sequentially.
        """
        # 0. Asset Action TypeSafe Validation (Equity vs TFEX segregation)
        ok, err = self.validate_asset_action(symbol=symbol, side=side, position=position)
        if not ok:
            return False, err

        # 1. Odd-lot check (Asset-aware: 1 contract for TFEX, 100 shares for SET Equity)
        ok, err = self.validate_board_lot(volume, symbol=symbol)
        if not ok:
            return False, err
            
        # 2. Tick size check
        ok, err = self.validate_tick_size(price)
        if not ok:
            return False, err
            
        # 3. Order value limit check
        ok, err = self.validate_order_value(volume, price)
        if not ok:
            return False, err

        # 4. Short sale Uptick check (if side is SHORT)
        if side.upper() == "SHORT" and last_trade_price is not None:
            ok, err = self.validate_short_uptick(price, last_trade_price)
            if not ok:
                return False, err
            
        # 5. Idempotency duplicate check
        ok, err = self.check_idempotency(symbol, side, volume, price, record=record_idempotency)
        if not ok:
            return False, err
            
        return True, None

    def reconcile_orders_against_portfolio(
        self,
        orders: list,
        portfolio_holdings: dict
    ) -> list:
        """
        Reconciles orders against actual portfolio holdings:
        1. Translates relative volumes (e.g. 50% for 'half') into actual share count.
        2. Auto-clamps volume down to actual portfolio holding if requested volume exceeds holding.
        3. Rejects sell/cover orders if symbol is not in portfolio.
        4. Calculates Price Advantage if market price is more favorable than target price.
        5. Validates SET Board Lot (volume % 100 == 0).
        """
        reconciled = []
        for order in orders:
            sym = order.symbol.upper()
            holding = portfolio_holdings.get(sym)

            if order.side.value in ["SELL", "COVER"]:
                if not holding or holding.get("volume", 0) <= 0:
                    order.is_valid_lot = False
                    order.validation_error = f"ไม่พบหุ้น {sym} ในพอร์ตคงค้าง (ไม่มีสถานะให้ขาย/ปิด)"
                    reconciled.append(order)
                    continue

                held_vol = int(holding.get("volume", 0))

                # Handle relative volume (e.g. 50% or 100%)
                if getattr(order, "is_relative_volume", False) and getattr(order, "volume_pct", None):
                    pct = float(order.volume_pct)
                    calc_vol = int(held_vol * (pct / 100.0))
                    # Round down to nearest 100 if >= 100
                    if calc_vol >= 100:
                        calc_vol = (calc_vol // 100) * 100
                    elif calc_vol > 0:
                        calc_vol = min(held_vol, 100)
                    order.volume = calc_vol
                    order.reason = (order.reason or "") + f" [คำนวณ {pct:.0f}% จาก {held_vol:,} หุ้นในพอร์ต]"
                elif order.volume > held_vol:
                    # Auto-clamp down to actual holding
                    order.clamped_from_volume = order.volume
                    order.volume = held_vol
                    order.reason = (order.reason or "") + f" [ปรับจาก {order.clamped_from_volume:,} เหลือ {held_vol:,} ตามพอร์ตจริง]"

                # Check board lot
                ok, err = self.validate_board_lot(order.volume)
                order.is_valid_lot = ok
                if not ok:
                    order.validation_error = err

                # Calculate Price Advantage
                current_mkt_px = holding.get("current_price") or holding.get("market_price")
                if current_mkt_px and order.price > 0:
                    if order.side.value in ["SELL", "SHORT"] and current_mkt_px > order.price:
                        diff_pct = ((current_mkt_px - order.price) / order.price) * 100.0
                        order.price_advantage_pct = round(diff_pct, 2)
                        order.price_advantage_label = f"🔥 ราคาตลาดดีกว่าเป้า! ฿{current_mkt_px:.2f} (เป้า ฿{order.price:.2f} | +{diff_pct:.2f}%)"
                    elif order.side.value in ["BUY", "COVER"] and current_mkt_px < order.price:
                        diff_pct = ((order.price - current_mkt_px) / order.price) * 100.0
                        order.price_advantage_pct = round(diff_pct, 2)
                        order.price_advantage_label = f"🔥 ซื้อได้ถูกกว่าเป้า! ฿{current_mkt_px:.2f} (เป้า ฿{order.price:.2f} | ประหยัด +{diff_pct:.2f}%)"

            else:
                # BUY or SHORT order
                ok, err = self.validate_all(sym, order.side.value, order.volume, order.price, record_idempotency=False)
                order.is_valid_lot = ok
                if not ok:
                    order.validation_error = err

            reconciled.append(order)
        return reconciled


validator = PreTradeValidator()

