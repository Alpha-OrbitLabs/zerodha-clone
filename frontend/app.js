// frontend/app.js

let ws;
function connectWs() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    ws = new WebSocket(
        (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.hostname + ':8000/ws/ticks'
    );

    ws.onopen = () => console.log('WS opened');
    ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'ticks') {
            const ticks = msg.data;
            // take first tick and update seriesssssssssssg
            if (ticks && ticks.length) {
                const t = Math.floor(ticks[0].timestamp / 1000);
                const p =
                    ticks[0].last_price ||
                    ticks[0].lastTradedPrice ||
                    ticks[0].last_price;
                if (p) lineSeries.update({ time: t, value: p });
            }
        }
    };
    ws.onclose = () => console.log('WS closed');
}

// Place order
async function placeOrder(side) {
    const symbol = document.getElementById('order-symbol').value;
    const qty = parseInt(document.getElementById('order-qty').value, 10) || 1;
    const body = { symbol, qty, side };
    try {
        const res = await fetch(`${apiBase}/api/place_order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        alert('Order result: ' + JSON.stringify(data));
    } catch (e) {
        alert('Order error: ' + e.message);
    }
}

// Get LTP
async function getLtp() {
    const symbol = document.getElementById('ltp-symbol').value;
    try {
        const res = await fetch(`${apiBase}/api/ltp/${symbol}`);
        const data = await res.json();
        document.getElementById('ltp-output').innerText =
            JSON.stringify(data, null, 2);
    } catch (e) {
        alert('LTP error: ' + e.message);
    }
}

// DOM hooks
document.getElementById('btn-get-ltp').addEventListener('click', getLtp);
document.getElementById('btn-connect-ws').addEventListener('click', connectWs);
document.getElementById('buy').addEventListener('click', () => placeOrder('BUY'));
document.getElementById('sell').addEventListener('click', () => placeOrder('SELL'));
