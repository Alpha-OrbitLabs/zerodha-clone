# backend/app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from kiteconnect import KiteConnect, KiteTicker
import os
from dotenv import load_dotenv
import threading

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN_FILE = os.getenv("ACCESS_TOKEN_FILE", "access_token.txt")

if not API_KEY or not API_SECRET:
    raise RuntimeError("Set API_KEY and API_SECRET in environment or .env file")

# Initialize kite client
kite = KiteConnect(api_key=API_KEY)
if os.path.exists(ACCESS_TOKEN_FILE):
    with open(ACCESS_TOKEN_FILE, "r") as f:
        token = f.read().strip()
        kite.set_access_token(token)
else:
    print("⚠️ Warning: access token file not found. Run the login flow before using endpoints.")

app = FastAPI()

# WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for conn in list(self.active_connections):
            try:
                await conn.send_json(message)
            except:
                self.disconnect(conn)

manager = ConnectionManager()

# WebSocket endpoint
@app.websocket("/ws/ticks")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background KiteTicker thread
def start_kiteticker(instrument_tokens: list[int]):
    kws = KiteTicker(API_KEY, kite._access_token)

    def on_ticks(ws, ticks):
        # Send ticks to frontend via websocket manager
        import asyncio
        asyncio.run(manager.broadcast({"type": "ticks", "data": ticks}))

    def on_connect(ws, response):
        print("✅ KiteTicker connected")
        ws.subscribe(instrument_tokens)
        ws.set_mode(ws.MODE_FULL, instrument_tokens)

    kws.on_ticks = on_ticks
    kws.on_connect = on_connect

    t = threading.Thread(target=kws.connect, daemon=True)
    t.start()
    return kws, t

# Example endpoint to start ticker
@app.get("/start_ticker")
def start_ticker():
    tokens = [256265]  # NIFTY 50 for example
    start_kiteticker(tokens)
    return {"status": "ticker started"}
