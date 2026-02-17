"""
FastAPI Backend for Straddle Scalping System - CORS FIXED
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
from datetime import datetime

app = FastAPI(title="NIFTY Straddle Scalping API")

# PROPER CORS FIX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Load data
try:
    performance_df = pd.read_csv('performance_metrics.csv')
    trades_df = pd.read_csv('backtest_results.csv')
    signals_df = pd.read_csv('trading_signals.csv')
    signals_df['datetime'] = pd.to_datetime(signals_df['datetime'])
    print("✅ Data loaded!")
except Exception as e:
    print(f"⚠️ Error: {e}")
    performance_df = None
    trades_df = None
    signals_df = None


@app.get("/")
def root():
    return {
        "message": "NIFTY Straddle Scalping API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "/current-signal": "Get latest trading signal",
            "/performance": "Get overall performance metrics",
            "/trades/recent": "Get recent 10 trades",
            "/iv-history": "Get IV history for chart",
            "/pnl-curve": "Get cumulative P&L curve"
        }
    }


@app.get("/current-signal")
def get_current_signal():
    if signals_df is None:
        return {"error": "Data not loaded"}

    last = signals_df.iloc[-1]
    recent = signals_df.tail(100)
    current_iv = float(last['iv'])
    iv_percentile = float((recent['iv'] <= current_iv).sum() / len(recent) * 100)

    return {
        "signal": str(last['signal']),
        "timestamp": str(last['datetime']),
        "spot_price": float(last['spot']),
        "current_iv": current_iv,
        "iv_percentile": iv_percentile,
        "straddle_cost": float(last['straddle_cost']),
        "recommendation": get_rec(str(last['signal']), current_iv, iv_percentile),
        "in_position": bool(last['in_position'])
    }


@app.get("/performance")
def get_performance():
    if performance_df is None:
        return {"error": "Data not loaded"}

    p = performance_df.iloc[0]
    return {
        "total_trades": int(p['total_trades']),
        "winning_trades": int(p['winning_trades']),
        "losing_trades": int(p['losing_trades']),
        "win_rate": float(p['win_rate']),
        "total_pnl": float(p['total_pnl']),
        "avg_pnl": float(p['avg_pnl']),
        "avg_profit": float(p['avg_profit']),
        "avg_loss": float(p['avg_loss']),
        "sharpe_ratio": float(p['sharpe_ratio']),
        "max_drawdown": float(p['max_drawdown']),
        "profit_factor": float(p['profit_factor'])
    }


@app.get("/trades/recent")
def get_recent_trades():
    if trades_df is None:
        return {"error": "Data not loaded"}
    recent = trades_df.tail(10).fillna('').to_dict('records')
    return {"count": len(recent), "trades": recent}


@app.get("/iv-history")
def get_iv_history(periods: int = 50):
    if signals_df is None:
        return {"error": "Data not loaded"}
    recent = signals_df.tail(periods)
    data = [
        {"timestamp": str(row['datetime']), "iv": float(row['iv']), "spot": float(row['spot'])}
        for _, row in recent.iterrows()
    ]
    return {"periods": len(data), "data": data}


@app.get("/pnl-curve")
def get_pnl_curve():
    if trades_df is None:
        return {"error": "Data not loaded"}

    data = []
    cumulative = 0
    pnl_col = 'pnl' if 'pnl' in trades_df.columns else 'P&L (₹)'
    
    for i, row in trades_df.iterrows():
        cumulative += float(row[pnl_col]) if pd.notna(row[pnl_col]) else 0
        data.append({"trade_number": i + 1, "cumulative_pnl": round(cumulative, 2)})

    return {"total_trades": len(data), "final_pnl": round(cumulative, 2), "data": data}


def get_rec(signal, iv, iv_pct):
    if signal == 'BUY_STRADDLE':
        return f"Buy ATM straddle. IV at {iv:.1f}% ({iv_pct:.0f}th percentile) - good entry!"
    elif signal == 'EXIT':
        return "Exit current position. Target conditions met."
    return f"Wait. IV at {iv_pct:.0f}th percentile - not in entry zone yet."


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
