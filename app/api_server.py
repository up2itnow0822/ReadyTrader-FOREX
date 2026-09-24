import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Set

if __package__ in (None, ""):
    # `python app/api_server.py` puts app/ on sys.path, not the repository root the packages live in.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.core.config import settings  # noqa: E402

# Import core components from the main server
from app.core.container import global_container  # noqa: E402
from app.tools.execution import PAPER_USER, execute_order, live_order_refusal, pre_trade_check  # noqa: E402
from marketdata.store import TickerSnapshot  # noqa: E402
from observability import build_log_context, log_event  # noqa: E402

# Initial context
API_CTX = build_log_context(tool="api_server")

app = FastAPI(title="ReadyTrader-FOREX Modern API")

# Enable CORS for Next.js frontend
# Only the dashboard may call this API from a browser. A wildcard would let any web page the
# operator visits read the account and post approvals to 127.0.0.1.
CORS_ORIGINS = [
    o.strip()
    for o in (os.getenv("API_CORS_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip() and o.strip() != "*"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)

# Active WebSocket connections
active_connections: Set[WebSocket] = set()


def broadcast_tick(snap: TickerSnapshot):
    """
    Callback for marketdata_ws_store updates.
    """
    if not active_connections:
        return

    payload = {"type": "TICKER_UPDATE", "data": snap.to_dict()}

    # We need to run this in the event loop of the FastAPI app
    # Since this callback might be triggered from a background thread
    # We use a global loop reference or call_soon_threadsafe
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(broadcast_all(payload))


async def broadcast_all(payload: dict):
    if not active_connections:
        return
    message = json.dumps(payload)
    disconnected = set()
    for websocket in active_connections:
        try:
            await websocket.send_text(message)
        except Exception:
            disconnected.add(websocket)

    for ws in disconnected:
        active_connections.remove(ws)


# Subscribe to ticker updates from the WebSocket store
global_container.marketdata_ws_store.subscribe(broadcast_tick)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # CORS does not cover WebSockets: a browser sends the page's Origin, and only the dashboard's
    # origins may subscribe. Clients without an Origin (scripts, not browsers) are allowed.
    origin = websocket.headers.get("origin")
    if origin and origin not in CORS_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    active_connections.add(websocket)
    log_event("api_client_connected", ctx=API_CTX, data={"active_connections": len(active_connections)})
    try:
        while True:
            # Keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        log_event("api_client_disconnected", ctx=API_CTX, data={"active_connections": len(active_connections)})


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "mode": "paper" if settings.PAPER_MODE else "live"}


@app.get("/api/pending-approvals")
async def get_pending_approvals():
    """
    Return list of trades awaiting manual approval.
    """
    return global_container.execution_store.list_pending()


class ApprovalRequest(BaseModel):
    request_id: str
    confirm_token: str
    approve: bool


@app.post("/api/approve-trade")
async def approve_trade(req: ApprovalRequest):
    """
    Approve or cancel a pending trade proposal. An approval re-runs the Risk Guardian with fresh
    market data and, in live mode, the operator switches and live policy, then executes exactly as
    the order tools do (app/tools/execution.execute_order): in the shared paper account, or at the
    brokerage. Cancelling needs the proposal's confirm_token too.
    """
    if not req.approve:
        return {"ok": global_container.execution_store.cancel(req.request_id, req.confirm_token)}
    try:
        proposal = global_container.execution_store.confirm(req.request_id, req.confirm_token)
    except ValueError as ve:
        # 404 for an id the store has never seen, 403 for a wrong token, 409 for a proposal that can
        # no longer be approved (expired, cancelled, already approved).
        reason = str(ve)
        status = 404 if reason.startswith("Unknown") else 403 if "confirm_token" in reason else 409
        raise HTTPException(status_code=status, detail=reason)
    if proposal.kind != "stock_order":
        return {"ok": False, "error": "Unknown proposal kind"}

    p = proposal.payload
    if p.get("paper_mode") is not settings.PAPER_MODE:
        made_in = {True: "paper", False: "live"}.get(p.get("paper_mode"), "an unrecorded")
        runs_in = "paper" if settings.PAPER_MODE else "live"
        message = f"This proposal was made in {made_in} mode and this API runs in {runs_in} mode; nothing was executed."
        raise HTTPException(status_code=409, detail={"code": "mode_mismatch", "message": message})
    exchange = p.get("exchange", "oanda")
    # A proposal can wait until it expires while the market moves: re-run the Risk Guardian, with
    # fresh daily bars, before anything executes. The volatility halt applies to both sides, so a
    # SELL can be refused here too.
    check = pre_trade_check(p["symbol"], p["side"], p["amount"], p.get("price", 0.0), p.get("sentiment_score"), exchange)
    if not check["allowed"]:
        log_event("api_approval_risk_blocked", ctx=API_CTX, data={"request_id": req.request_id, "reason": check["reason"]})
        raise HTTPException(status_code=409, detail={"code": "risk_blocked", "reason": check["reason"], "market": check["market"]})
    if not settings.PAPER_MODE:
        # The switches and the live policy may have changed while the proposal waited.
        refusal = live_order_refusal(exchange, p["symbol"], p["side"], p["amount"], p.get("order_type", "market"), p.get("price") or 0.0)
        if refusal:
            raise HTTPException(status_code=409, detail=refusal)

    out = execute_order(
        p["symbol"], p["side"], p["amount"], p.get("price") or 0.0, p.get("order_type", "market"), exchange,
        p.get("rationale") or "api_approved", check["market_price"],
    )
    if not out["ok"]:
        raise HTTPException(status_code=out.get("status", 409), detail={"code": out["code"], "message": out["message"], "data": out.get("data", {})})
    return {"ok": True, **out["data"]}


@app.get("/api/portfolio")
async def get_portfolio():
    """
    The paper account the agent trades (cash, equity, positions, margin and today's P&L), shared
    with the MCP server through the paper database. Live mode is not implemented here.
    """
    if not settings.PAPER_MODE:
        return {"error": "Live portfolio view not yet implemented in API"}
    account = global_container.paper_engine
    try:
        state = account.account(PAPER_USER)
    except ValueError as e:
        raise HTTPException(status_code=503, detail={"code": "market_data_error", "message": str(e)})
    metrics = account.get_risk_metrics(PAPER_USER)
    return {
        "balances": account.get_balances(PAPER_USER),
        "positions": state["positions"],
        "metrics": {
            "equity": state["equity_usd"],
            "cash": state["cash_usd"],
            "unrealized_pnl": state["unrealized_usd"],
            "margin_used": state["margin_used_usd"],
            "free_margin": state["free_margin_usd"],
            "leverage": state["leverage"],
            "daily_pnl_pct": metrics["daily_pnl_pct"],
            "drawdown_pct": metrics["drawdown_pct"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", 8000))
    host = os.getenv("API_HOST", "127.0.0.1")
    log_event("api_server_started", ctx=API_CTX, data={"port": port, "host": host})
    uvicorn.run(app, host=host, port=port)
