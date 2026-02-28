"""
FastAPI Backend with Interactive Backtesting
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from datetime import datetime

app = FastAPI(title="NIFTY Straddle Scalping API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Load data
try:
    performance_df = pd.read_csv("performance_metrics.csv")
    trades_df = pd.read_csv("backtest_results.csv")
    signals_df = pd.read_csv("trading_signals.csv")
    signals_df["datetime"] = pd.to_datetime(signals_df["datetime"])
    straddle_df = pd.read_csv("straddle_data_prepared.csv")
    straddle_df["datetime"] = pd.to_datetime(straddle_df["datetime"])
    print("✅ Data loaded!")
except Exception as e:
    print(f"⚠️ Error: {e}")
    performance_df = None
    trades_df = None
    signals_df = None
    straddle_df = None


class BacktestParams(BaseModel):
    iv_entry_percentile: int = 30
    profit_target: float = 10.0
    stop_loss: float = 20.0
    max_hold_time: int = 60


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
            "/pnl-curve": "Get cumulative P&L curve",
            "/run-backtest": "Run custom backtest with parameters"
        }
    }


@app.get("/current-signal")
def get_current_signal():
    if signals_df is None:
        return {"error": "Data not loaded"}

    last = signals_df.iloc[-1]
    recent = signals_df.tail(100)
    current_iv = float(last["iv"])
    iv_percentile = float((recent["iv"] <= current_iv).sum() / len(recent) * 100)

    return {
        "signal": str(last["signal"]),
        "timestamp": str(last["datetime"]),
        "spot_price": float(last["spot"]),
        "current_iv": round(current_iv, 2),
        "iv_percentile": round(iv_percentile, 0),
        "straddle_cost": round(float(last["straddle_cost"]), 2),
        "recommendation": get_rec(str(last["signal"]), current_iv, iv_percentile),
        "in_position": bool(last["in_position"])
    }


@app.get("/performance")
def get_performance():
    if performance_df is None:
        return {"error": "Data not loaded"}

    p = performance_df.iloc[0]
    return {
        "total_trades": int(p["total_trades"]),
        "winning_trades": int(p["winning_trades"]),
        "losing_trades": int(p["losing_trades"]),
        "win_rate": round(float(p["win_rate"]), 1),
        "total_pnl": round(float(p["total_pnl"]), 2),
        "avg_pnl": round(float(p["avg_pnl"]), 2),
        "avg_profit": round(float(p["avg_profit"]), 2),
        "avg_loss": round(float(p["avg_loss"]), 2),
        "sharpe_ratio": round(float(p["sharpe_ratio"]), 2),
        "max_drawdown": round(float(p["max_drawdown"]), 2),
        "profit_factor": round(float(p["profit_factor"]), 2)
    }


@app.get("/trades/recent")
def get_recent_trades():
    if trades_df is None:
        return {"error": "Data not loaded"}
    
    recent = trades_df.tail(10).copy()
    for col in recent.columns:
        if "P&L" in col or "Cost" in col or "Price" in col:
            recent[col] = recent[col].round(2)
    
    return {"count": len(recent), "trades": recent.fillna("").to_dict("records")}


@app.get("/iv-history")
def get_iv_history(periods: int = 50):
    if signals_df is None:
        return {"error": "Data not loaded"}
    recent = signals_df.tail(periods)
    data = [
        {"timestamp": str(row["datetime"]), "iv": round(float(row["iv"]), 2), "spot": round(float(row["spot"]), 2)}
        for _, row in recent.iterrows()
    ]
    return {"periods": len(data), "data": data}


@app.get("/pnl-curve")
def get_pnl_curve():
    if trades_df is None:
        return {"error": "Data not loaded"}

    data = []
    cumulative = 0
    pnl_col = "pnl" if "pnl" in trades_df.columns else "P&L (₹)"
    
    for i, row in trades_df.iterrows():
        cumulative += float(row[pnl_col]) if pd.notna(row[pnl_col]) else 0
        data.append({"trade_number": i + 1, "cumulative_pnl": round(cumulative, 2)})

    return {"total_trades": len(data), "final_pnl": round(cumulative, 2), "data": data}


@app.post("/run-backtest")
def run_custom_backtest(params: BacktestParams):
    if straddle_df is None:
        return {"error": "Data not loaded"}
    
    try:
        LOOKBACK = 100
        IV_ENTRY = params.iv_entry_percentile
        PROFIT_TARGET = params.profit_target
        STOP_LOSS = params.stop_loss
        MAX_HOLD = int(params.max_hold_time / 5)
        
        df = straddle_df.copy()
        df["iv_percentile"] = df["avg_iv"].rolling(window=LOOKBACK, min_periods=20).apply(
            lambda x: (x.iloc[-1] <= pd.Series(x).quantile(IV_ENTRY/100)) * 100 if len(x) > 0 else 0
        )
        
        trades = []
        position = None
        
        for i in range(len(df)):
            current_iv = df.loc[i, "avg_iv"]
            current_cost = df.loc[i, "straddle_cost"]
            
            if position is not None:
                entry_cost = position["entry_cost"]
                periods_held = i - position["entry_index"]
                
                pnl = current_cost - entry_cost
                pnl_pct = (pnl / entry_cost) * 100
                
                if pnl_pct >= PROFIT_TARGET:
                    trades.append({"pnl": pnl, "result": "WIN"})
                    position = None
                elif pnl_pct <= -STOP_LOSS:
                    trades.append({"pnl": pnl, "result": "LOSS"})
                    position = None
                elif periods_held >= MAX_HOLD:
                    trades.append({"pnl": pnl, "result": "WIN" if pnl > 0 else "LOSS"})
                    position = None
            else:
                if i >= LOOKBACK and df.loc[i, "iv_percentile"] == 100:
                    position = {"entry_index": i, "entry_cost": current_cost}
        
        if len(trades) == 0:
            return {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "profit_factor": 0, "sharpe_ratio": 0}
        
        trades_df_new = pd.DataFrame(trades)
        total_trades = len(trades_df_new)
        winning_trades = len(trades_df_new[trades_df_new["result"] == "WIN"])
        win_rate = (winning_trades / total_trades) * 100
        total_pnl = trades_df_new["pnl"].sum()
        
        total_profit = trades_df_new[trades_df_new["result"] == "WIN"]["pnl"].sum() if winning_trades > 0 else 0
        total_loss = abs(trades_df_new[trades_df_new["result"] == "LOSS"]["pnl"].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else 0
        
        sharpe = (trades_df_new["pnl"].mean() / trades_df_new["pnl"].std()) if trades_df_new["pnl"].std() > 0 else 0
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": total_trades - winning_trades,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_pnl": round(trades_df_new["pnl"].mean(), 2)
        }
        
    except Exception as e:
        return {"error": str(e)}


def get_rec(signal, iv, iv_pct):
    if signal == "BUY_STRADDLE":
        return f"Buy ATM straddle. IV at {iv:.1f}% ({iv_pct:.0f}th percentile) - good entry!"
    elif signal == "EXIT":
        return "Exit current position. Target conditions met."
    return f"Wait. IV at {iv_pct:.0f}th percentile - not in entry zone yet."


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
