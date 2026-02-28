"""
SIMPLE 3-STRATEGY BACKEND
IV Scalping | Gamma Scalping | Hybrid
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

app = FastAPI(title="NIFTY 3-Strategy System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data storage
iv_perf = None
iv_trades = None
gamma_perf = None
gamma_trades = None
hybrid_perf = None
hybrid_trades = None


@app.on_event("startup")
async def load():
    global iv_perf, iv_trades, gamma_perf, gamma_trades, hybrid_perf, hybrid_trades
    
    try:
        iv_perf = pd.read_csv("iv_performance.csv").iloc[0].to_dict()
        iv_trades = pd.read_csv("iv_trades.csv")
        print("✅ IV Scalping loaded")
    except:
        print("⚠️ IV Scalping not found")
    
    try:
        gamma_perf = pd.read_csv("gamma_performance.csv").iloc[0].to_dict()
        gamma_trades = pd.read_csv("gamma_trades.csv")
        print("✅ Gamma Scalping loaded")
    except:
        print("⚠️ Gamma Scalping not found")
    
    try:
        hybrid_perf = pd.read_csv("hybrid_performance.csv").iloc[0].to_dict()
        hybrid_trades = pd.read_csv("hybrid_trades.csv")
        print("✅ Hybrid loaded")
    except:
        print("⚠️ Hybrid not found")


@app.get("/")
def root():
    return {
        "message": "NIFTY 3-Strategy System",
        "strategies": ["iv_scalping", "gamma_scalping", "hybrid"]
    }


@app.get("/strategy/iv_scalping")
def get_iv():
    if not iv_perf:
        return {"error": "Data not available"}
    
    return {
        "name": "IV Scalping",
        "description": "Buy straddle when IV is low (≤30th percentile)",
        "performance": {
            "total_trades": int(iv_perf['total_trades']),
            "wins": int(iv_perf['wins']),
            "losses": int(iv_perf['losses']),
            "win_rate": float(iv_perf['win_rate']),
            "total_pnl": float(iv_perf['total_pnl']),
            "avg_pnl": float(iv_perf['avg_pnl'])
        },
        "recent_trades": iv_trades.tail(10).to_dict('records') if iv_trades is not None else []
    }


@app.get("/strategy/gamma_scalping")
def get_gamma():
    if not gamma_perf:
        return {"error": "Data not available"}
    
    return {
        "name": "Gamma Scalping",
        "description": "Buy high-gamma straddle and hedge continuously",
        "performance": {
            "total_trades": int(gamma_perf['total_trades']),
            "wins": int(gamma_perf['wins']),
            "losses": int(gamma_perf['losses']),
            "win_rate": float(gamma_perf['win_rate']),
            "total_pnl": float(gamma_perf['total_pnl']),
            "avg_pnl": float(gamma_perf['avg_pnl'])
        },
        "recent_trades": gamma_trades.tail(10).to_dict('records') if gamma_trades is not None else []
    }


@app.get("/strategy/hybrid")
def get_hybrid():
    if not hybrid_perf:
        return {"error": "Data not available"}
    
    return {
        "name": "Hybrid",
        "description": "Combines IV + Gamma (both conditions required)",
        "performance": {
            "total_trades": int(hybrid_perf['total_trades']),
            "wins": int(hybrid_perf['wins']),
            "losses": int(hybrid_perf['losses']),
            "win_rate": float(hybrid_perf['win_rate']),
            "total_pnl": float(hybrid_perf['total_pnl']),
            "avg_pnl": float(hybrid_perf['avg_pnl'])
        },
        "recent_trades": hybrid_trades.tail(10).to_dict('records') if hybrid_trades is not None and len(hybrid_trades) > 0 else []
    }


@app.get("/compare")
def compare():
    strategies = []
    
    if iv_perf:
        strategies.append({
            "name": "IV Scalping",
            "total_trades": int(iv_perf['total_trades']),
            "win_rate": float(iv_perf['win_rate']),
            "total_pnl": float(iv_perf['total_pnl'])
        })
    
    if gamma_perf:
        strategies.append({
            "name": "Gamma Scalping",
            "total_trades": int(gamma_perf['total_trades']),
            "win_rate": float(gamma_perf['win_rate']),
            "total_pnl": float(gamma_perf['total_pnl'])
        })
    
    if hybrid_perf:
        strategies.append({
            "name": "Hybrid",
            "total_trades": int(hybrid_perf['total_trades']),
            "win_rate": float(hybrid_perf['win_rate']),
            "total_pnl": float(hybrid_perf['total_pnl'])
        })
    
    if strategies:
        best = max(strategies, key=lambda x: x['total_pnl'])
        return {
            "strategies": strategies,
            "winner": best['name']
        }
    
    return {"error": "No data"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
