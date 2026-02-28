"""
FastAPI Backend - NIFTY Straddle Scalping System
Complete with all endpoints and optimizations
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

app = FastAPI(
    title="NIFTY Straddle Scalping API",
    description="AI-Powered Options Trading System",
    version="2.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Global variables for data caching
performance_df = None
trades_df = None
signals_df = None
straddle_df = None

# Load data on startup
@app.on_event("startup")
async def load_data():
    global performance_df, trades_df, signals_df, straddle_df
    try:
        performance_df = pd.read_csv("performance_metrics.csv")
        trades_df = pd.read_csv("backtest_results.csv")
        signals_df = pd.read_csv("trading_signals.csv")
        signals_df["datetime"] = pd.to_datetime(signals_df["datetime"])
        straddle_df = pd.read_csv("straddle_data_prepared.csv")
        straddle_df["datetime"] = pd.to_datetime(straddle_df["datetime"])
        print("✅ All data loaded successfully!")
        print(f"   - Performance metrics: {len(performance_df)} rows")
        print(f"   - Trades: {len(trades_df)} rows")
        print(f"   - Signals: {len(signals_df)} rows")
        print(f"   - Straddle data: {len(straddle_df)} rows")
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")


class BacktestParams(BaseModel):
    iv_entry_percentile: int = 30
    profit_target: float = 10.0
    stop_loss: float = 20.0
    max_hold_time: int = 60


@app.get("/")
def root():
    """API root endpoint"""
    return {
        "message": "NIFTY Straddle Scalping API",
        "status": "running",
        "version": "2.0.0",
        "data_loaded": all([
            performance_df is not None,
            trades_df is not None,
            signals_df is not None,
            straddle_df is not None
        ]),
        "endpoints": {
            "/": "API information",
            "/health": "Health check",
            "/current-signal": "Get latest trading signal",
            "/performance": "Get overall performance metrics",
            "/trades": "Get all trades (with filters)",
            "/trades/recent": "Get recent 10 trades",
            "/iv-history": "Get IV history for chart",
            "/pnl-curve": "Get cumulative P&L curve",
            "/run-backtest": "Run custom backtest with parameters (POST)"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "data_loaded": all([
            performance_df is not None,
            trades_df is not None,
            signals_df is not None,
            straddle_df is not None
        ])
    }


@app.get("/current-signal")
def get_current_signal():
    """Get the latest trading signal"""
    if signals_df is None:
        return {"error": "Data not loaded"}

    try:
        last = signals_df.iloc[-1]
        recent = signals_df.tail(100)
        current_iv = float(last["iv"])
        iv_percentile = float((recent["iv"] <= current_iv).sum() / len(recent) * 100)

        return {
            "signal": str(last["signal"]),
            "timestamp": str(last["datetime"]),
            "spot_price": round(float(last["spot"]), 2),
            "current_iv": round(current_iv, 2),
            "iv_percentile": round(iv_percentile, 0),
            "straddle_cost": round(float(last["straddle_cost"]), 2),
            "recommendation": get_recommendation(str(last["signal"]), current_iv, iv_percentile),
            "in_position": bool(last["in_position"]),
            "confidence": calculate_confidence(iv_percentile)
        }
    except Exception as e:
        return {"error": f"Error processing signal: {str(e)}"}


@app.get("/performance")
def get_performance():
    """Get overall performance metrics"""
    if performance_df is None:
        return {"error": "Data not loaded"}

    try:
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
    except Exception as e:
        return {"error": f"Error processing performance: {str(e)}"}


@app.get("/trades")
def get_all_trades(
    limit: int = Query(1000, description="Maximum number of trades to return"),
    filter: str = Query("ALL", description="Filter by result: ALL, WIN, or LOSS")
):
    """Get all trades with optional filtering"""
    if trades_df is None:
        return {"error": "Data not loaded"}

    try:
        # Apply filter
        if filter.upper() == "WIN":
            filtered = trades_df[trades_df["Result"] == "WIN"].copy()
        elif filter.upper() == "LOSS":
            filtered = trades_df[trades_df["Result"] == "LOSS"].copy()
        else:
            filtered = trades_df.copy()

        # Apply limit
        trades_list = filtered.head(limit).copy()

        # Round numeric columns
        numeric_cols = trades_list.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            trades_list[col] = trades_list[col].round(2)

        return {
            "total": len(filtered),
            "returned": len(trades_list),
            "filter": filter.upper(),
            "trades": trades_list.fillna("").to_dict("records")
        }
    except Exception as e:
        return {"error": f"Error processing trades: {str(e)}"}


@app.get("/trades/recent")
def get_recent_trades():
    """Get 10 most recent trades"""
    if trades_df is None:
        return {"error": "Data not loaded"}

    try:
        recent = trades_df.tail(10).copy()

        # Round numeric columns
        numeric_cols = recent.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            recent[col] = recent[col].round(2)

        return {
            "count": len(recent),
            "trades": recent.fillna("").to_dict("records")
        }
    except Exception as e:
        return {"error": f"Error processing recent trades: {str(e)}"}


@app.get("/iv-history")
def get_iv_history(periods: int = Query(50, description="Number of periods to return")):
    """Get IV history for charting"""
    if signals_df is None:
        return {"error": "Data not loaded"}

    try:
        recent = signals_df.tail(periods)
        data = [
            {
                "timestamp": str(row["datetime"]),
                "iv": round(float(row["iv"]), 2),
                "spot": round(float(row["spot"]), 2)
            }
            for _, row in recent.iterrows()
        ]

        return {
            "periods": len(data),
            "data": data
        }
    except Exception as e:
        return {"error": f"Error processing IV history: {str(e)}"}


@app.get("/pnl-curve")
def get_pnl_curve():
    """Get cumulative P&L curve"""
    if trades_df is None:
        return {"error": "Data not loaded"}

    try:
        data = []
        cumulative = 0

        # Find the P&L column (might have different names)
        pnl_col = None
        for col in ["pnl", "P&L (₹)", "P&L"]:
            if col in trades_df.columns:
                pnl_col = col
                break

        if pnl_col is None:
            return {"error": "P&L column not found"}

        for i, row in trades_df.iterrows():
            pnl = float(row[pnl_col]) if pd.notna(row[pnl_col]) else 0
            cumulative += pnl
            data.append({
                "trade_number": i + 1,
                "cumulative_pnl": round(cumulative, 2)
            })

        return {
            "total_trades": len(data),
            "final_pnl": round(cumulative, 2),
            "data": data
        }
    except Exception as e:
        return {"error": f"Error processing P&L curve: {str(e)}"}


@app.post("/run-backtest")
def run_custom_backtest(params: BacktestParams):
    """Run backtest with custom parameters"""
    if straddle_df is None:
        return {"error": "Straddle data not loaded"}

    try:
        # Parameters
        LOOKBACK = 100
        IV_ENTRY = params.iv_entry_percentile
        PROFIT_TARGET = params.profit_target
        STOP_LOSS = params.stop_loss
        MAX_HOLD = int(params.max_hold_time / 5)  # Convert minutes to 5-min periods

        # Copy data
        df = straddle_df.copy()

        # Calculate IV percentile
        df["iv_percentile"] = df["avg_iv"].rolling(window=LOOKBACK, min_periods=20).apply(
            lambda x: (x.iloc[-1] <= pd.Series(x).quantile(IV_ENTRY / 100)) * 100 if len(x) > 0 else 0
        )

        # Simulate trading
        trades = []
        position = None

        for i in range(len(df)):
            current_iv = df.loc[i, "avg_iv"]
            current_cost = df.loc[i, "straddle_cost"]

            if position is not None:
                # Check exit conditions
                entry_cost = position["entry_cost"]
                periods_held = i - position["entry_index"]

                pnl = current_cost - entry_cost
                pnl_pct = (pnl / entry_cost) * 100

                # Exit conditions
                exit = False
                if pnl_pct >= PROFIT_TARGET:
                    exit = True
                elif pnl_pct <= -STOP_LOSS:
                    exit = True
                elif periods_held >= MAX_HOLD:
                    exit = True

                if exit:
                    trades.append({
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "result": "WIN" if pnl > 0 else "LOSS"
                    })
                    position = None
            else:
                # Check entry
                if i >= LOOKBACK and df.loc[i, "iv_percentile"] == 100:
                    position = {
                        "entry_index": i,
                        "entry_cost": current_cost
                    }

        # Calculate metrics
        if len(trades) == 0:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "profit_factor": 0,
                "sharpe_ratio": 0,
                "message": "No trades generated with these parameters"
            }

        trades_df_new = pd.DataFrame(trades)
        total_trades = len(trades_df_new)
        winning_trades = len(trades_df_new[trades_df_new["result"] == "WIN"])
        win_rate = (winning_trades / total_trades) * 100
        total_pnl = trades_df_new["pnl"].sum()

        # Profit factor
        total_profit = trades_df_new[trades_df_new["result"] == "WIN"]["pnl"].sum() if winning_trades > 0 else 0
        total_loss = abs(trades_df_new[trades_df_new["result"] == "LOSS"]["pnl"].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else 0

        # Sharpe ratio
        sharpe = (trades_df_new["pnl"].mean() / trades_df_new["pnl"].std()) if trades_df_new["pnl"].std() > 0 else 0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": total_trades - winning_trades,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_pnl": round(trades_df_new["pnl"].mean(), 2),
            "parameters": {
                "iv_entry_percentile": IV_ENTRY,
                "profit_target": PROFIT_TARGET,
                "stop_loss": STOP_LOSS,
                "max_hold_time": params.max_hold_time
            }
        }

    except Exception as e:
        return {"error": f"Backtest failed: {str(e)}"}


def get_recommendation(signal: str, iv: float, iv_pct: float) -> str:
    """Generate trading recommendation"""
    if signal == "BUY_STRADDLE":
        return f"Buy ATM straddle now. IV at {iv:.1f}% ({iv_pct:.0f}th percentile) - favorable entry!"
    elif signal == "EXIT":
        return "Exit current position. Target conditions met."
    elif iv_pct < 30:
        return f"Watch for entry. IV at {iv_pct:.0f}th percentile - approaching entry zone."
    else:
        return f"Wait. IV at {iv_pct:.0f}th percentile - not in entry zone yet."


def calculate_confidence(iv_percentile: float) -> int:
    """Calculate confidence score based on IV percentile"""
    if iv_percentile <= 20:
        return 85
    elif iv_percentile <= 25:
        return 80
    elif iv_percentile <= 30:
        return 70
    elif iv_percentile <= 35:
        return 60
    elif iv_percentile <= 40:
        return 50
    elif iv_percentile <= 50:
        return 40
    elif iv_percentile <= 70:
        return 30
    else:
        return 20


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
