// Tick Offset & Stepper helper for SET equities
// Supports calculation of next tick (+/-) per SET spread table and DOM stepper triggering
(() => {
    function getSetTickSize(price) {
        const p = Number(price);
        if (p < 2.00) return 0.01;
        if (p < 5.00) return 0.02;
        if (p < 10.00) return 0.05;
        if (p < 25.00) return 0.10;
        if (p < 100.00) return 0.25;
        if (p < 200.00) return 0.50;
        if (p < 400.00) return 1.00;
        return 2.00;
    }

    function adjustPriceByTicks(price, steps = 0) {
        let p = Number(price);
        if (steps === 0 || isNaN(p) || p <= 0) return Math.round(p * 100) / 100;
        const dir = steps > 0 ? 1 : -1;
        const count = Math.abs(steps);
        for (let i = 0; i < count; i++) {
            if (dir > 0) {
                const tick = getSetTickSize(p);
                p = Math.round((p + tick) * 100) / 100;
            } else {
                const tick = getSetTickSize(p - 0.0001);
                const nextP = Math.round((p - tick) * 100) / 100;
                if (nextP > 0) {
                    p = nextP;
                } else {
                    break;
                }
            }
        }
        return Math.round(p * 100) / 100;
    }

    function calculateOrderPrice({ quote, side = 'BUY', offsetType = 'passive', ticks = 0 }) {
        const cleanSide = (side || 'BUY').toUpperCase();
        let basePrice = null;
        if (cleanSide === 'BUY' || cleanSide === 'COVER') {
            basePrice = offsetType === 'aggressive' ? (quote.ask || quote.last) : (quote.bid || quote.last);
            const stepDir = offsetType === 'aggressive' ? Math.abs(ticks) : -Math.abs(ticks);
            return adjustPriceByTicks(basePrice, stepDir);
        } else {
            basePrice = offsetType === 'aggressive' ? (quote.bid || quote.last) : (quote.ask || quote.last);
            const stepDir = offsetType === 'aggressive' ? -Math.abs(ticks) : Math.abs(ticks);
            return adjustPriceByTicks(basePrice, stepDir);
        }
    }

    function triggerDomStepper(steps = 0) {
        if (!steps) return { success: false, reason: 'Zero steps' };
        const host = location.hostname;
        if (host.includes('liberator.co.th')) {
            const popup = document.querySelector('#popup_price');
            if (!popup) return { success: false, reason: '#popup_price not open' };
            const btn = steps > 0
                ? popup.querySelector('.bg-more-than')
                : popup.querySelector('.bg-less-than');
            if (!btn) return { success: false, reason: 'Stepper button not found in popup' };
            for (let i = 0; i < Math.abs(steps); i++) {
                btn.click();
            }
            const input = document.querySelector('#price');
            return { success: true, steps, newPrice: input ? input.value : null };
        } else if (host.includes('settrade.com')) {
            const container = document.querySelector('.z-index-smart-price-volume, .css-zxyhmd');
            if (!container) return { success: false, reason: 'Streaming stepper container not visible' };
            const btn = steps > 0
                ? container.querySelector('.bg-color-gainer-100')
                : container.querySelector('.bg-color-loser-100');
            if (!btn) return { success: false, reason: 'Streaming stepper button not found' };
            for (let i = 0; i < Math.abs(steps); i++) {
                btn.click();
            }
            const input = document.querySelector('input[name="price-input"]');
            return { success: true, steps, newPrice: input ? input.value : null };
        }
        return { success: false, reason: `Unsupported host: ${host}` };
    }

    return {
        getSetTickSize,
        adjustPriceByTicks,
        calculateOrderPrice,
        triggerDomStepper
    };
})();
