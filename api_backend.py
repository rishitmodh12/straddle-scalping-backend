"""
NIFTY Trading System - COMPLETE Backend v5.0
ALL ENDPOINTS: Old + New + Strategy Comparison
Ready for ML Integration
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Literal

app = FastAPI(
    title="NIFTY Multi-Strategy Trading System",
    description="Rule-Based + Gamma Scalping + ML Ready",
    version="5.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Global data
performance_df = None
trades_df = None
signals_df = None
straddle_df = None

# Strategy-specific data
gamma_performance = None
gamma_trades = None
hybrid_performance = None
hybrid_trades = None


@app.on_event("startup")
async def load_data():
    global performance_df, trades_df, signals_df, straddle_df
    global gamma_performance, gamma_trades, hybrid_performance, hybrid_trades
    
    try:
        # Load IV scalping data (original)
        performance_df = pd.read_csv("performance_metrics.csv")
        trades_df = pd.read_csv("backtest_results.csv")
        signals_df = pd.read_csv("trading_signals.csv")
        signals_df["datetime"] = pd.to_datetime(signals_df["datetime"])
        straddle_df = pd.read_csv("straddle_data_prepared.csv")
        straddle_df["datetime"] = pd.to_datetime(straddle_df["datetime"])
        
        # Load Gamma scalping data
        try:
            gamma_perf_df = pd.read_csv("gamma_performance_metrics.csv")
            gamma_performance = gamma_perf_df.iloc[0].to_dict()
            gamma_trades = pd.read_csv("gamma_backtest_results.csv")
        except:
            print("⚠️ Gamma data not found")
        
        # Load Hybrid data
        try:
            hybrid_perf_df = pd.read_csv("hybrid_performance_metrics.csv")
            hybrid_performance = hybrid_perf_df.iloc[0].to_dict()
            hybrid_trades = pd.read_csv("hybrid_backtest_results.csv")
        except:
            print("⚠️ Hybrid data not found")
        
        print("✅ Data loaded successfully!")
        
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")


class BacktestParams(BaseModel):
    iv_entry_percentile: int = 30
    profit_target: float = 10.0
    stop_loss: float = 20.0
    max_hold_time: int = 60


def calculate_realized_volatility(spot_prices, window=20):
    returns = np.log(spot_prices / spot_prices.shift(1))
    realized_vol = returns.rolling(window=window).std() * np.sqrt(252) * 100
    return realized_vol


def get_volatility_regime(current_iv, recent_ivs):
    avg = recent_ivs.mean()
    std = recent_ivs.std()
    
    if current_iv < (avg - 0.5 * std):
        regime = "LOW"
        color = "green"
        description = "Favorable for straddle entry"
    elif current_iv > (avg + 0.5 * std):
        regime = "HIGH"
        color = "red"
        description = "Options are expensive"
    else:
        regime = "NORMAL"
        color = "yellow"
        description = "Neutral conditions"
    
    deviation_pct = ((current_iv - avg) / avg) * 100
    
    return {
        "regime": regime,
        "color": color,
        "description": description,
        "current_iv": round(current_iv, 2),
        "average_iv": round(avg, 2),
        "deviation_pct": round(deviation_pct, 1)
    }


def calculate_greeks_simple(spot, strike, time_to_expiry, iv):
    T = time_to_expiry
    sigma = iv / 100
    
    if T <= 0:
        return {'delta': 0, 'gamma': 0, 'vega': 0, 'theta': 0}
    
    # ATM approximations
    gamma = 0.4 / (spot * sigma * np.sqrt(T))
    vega = spot * 0.4 * np.sqrt(T)
    theta = -(spot * sigma * 0.4) / (2 * np.sqrt(T)) / 365
    
    return {
        'delta': 0.02,  # Near 0 for ATM straddle
        'gamma': gamma * 2,
        'vega': vega * 2,
        'theta': theta * 2
    }


def calculate_confidence(iv_percentile: float) -> int:
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
    else:
        return max(20, int(100 - iv_percentile))


# ============ ROOT & INFO ENDPOINTS ============

@app.get("/")
def root():
    return {
        "message": "NIFTY Multi-Strategy Trading System",
        "version": "5.0.0",
        "strategies": {
            "iv_scalping": "Volatility-based scalping (Original)",
            "gamma_scalping": "Greeks-based delta hedging (NEW)",
            "hybrid": "Combined IV + Gamma (NEW)",
            "ml_prediction": "ML-based volatility prediction (COMING SOON)"
        },
        "endpoints": {
            "/current-signal": "Latest trading signal",
            "/performance": "Overall performance",
            "/trades/recent": "Recent 10 trades",
            "/iv-history": "IV history for charts",
            "/pnl-curve": "Cumulative P&L",
            "/run-backtest": "Custom backtest",
            "/strategies": "List all strategies",
            "/strategy/{name}/performance": "Strategy performance",
            "/strategy/compare": "Compare strategies",
            "/greeks": "Current Greeks",
            "/volatility-analysis": "IV vs RV"
        }
    }


@app.get("/health")
def health_check():
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


# ============ LEGACY ENDPOINTS (Original System) ============

@app.get("/current-signal")
def get_current_signal():
    if signals_df is None:
        return {"error": "Data not loaded"}

    try:
        last = signals_df.iloc[-1]
        recent = signals_df.tail(100)
        current_iv = float(last["iv"])
        iv_percentile = float((recent["iv"] <= current_iv).sum() / len(recent) * 100)
        
        regime_info = get_volatility_regime(current_iv, recent["iv"])

        return {
            "signal": str(last["signal"]),
            "timestamp": str(last["datetime"]),
            "spot_price": round(float(last["spot"]), 2),
            "current_iv": round(current_iv, 2),
            "iv_percentile": round(iv_percentile, 0),
            "straddle_cost": round(float(last["straddle_cost"]), 2),
            "recommendation": get_recommendation(str(last["signal"]), current_iv, iv_percentile),
            "in_position": bool(last["in_position"]),
            "confidence": calculate_confidence(iv_percentile),
            "volatility_regime": regime_info
        }
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


@app.get("/performance")
def get_performance():
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
        return {"error": f"Error: {str(e)}"}


@app.get("/trades/recent")
def get_recent_trades():
    if trades_df is None:
        return {"error": "Data not loaded"}

    try:
        recent = trades_df.tail(10).copy()
        numeric_cols = recent.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            recent[col] = recent[col].round(2)

        return {
            "count": len(recent),
            "trades": recent.fillna("").to_dict("records")
        }
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


@app.get("/trades")
def get_all_trades(
    limit: int = Query(1000, description="Max trades"),
    filter: str = Query("ALL", description="ALL, WIN, or LOSS")
):
    if trades_df is None:
        return {"error": "Data not loaded"}

    try:
        result_col = None
        for col in ["Result", "result", "RESULT"]:
            if col in trades_df.columns:
                result_col = col
                break
        
        if result_col and filter.upper() == "WIN":
            filtered = trades_df[trades_df[result_col] == "WIN"].copy()
        elif result_col and filter.upper() == "LOSS":
            filtered = trades_df[trades_df[result_col] == "LOSS"].copy()
        else:
            filtered = trades_df.copy()

        trades_list = filtered.head(limit).copy()
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
        return {"error": f"Error: {str(e)}"}


@app.get("/iv-history")
def get_iv_history(periods: int = Query(50, description="Number of periods")):
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

        return {"periods": len(data), "data": data}
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


@app.get("/pnl-curve")
def get_pnl_curve():
    if trades_df is None:
        return {"error": "Data not loaded"}

    try:
        data = []
        cumulative = 0
        
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
        return {"error": f"Error: {str(e)}"}


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
            lambda x: (x.iloc[-1] <= np.percentile(x, IV_ENTRY)) * 100 if len(x) > 0 else 0
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
                        "result": "WIN" if pnl > 0 else "LOSS"
                    })
                    position = None
            else:
                if i >= LOOKBACK and df.loc[i, "iv_percentile"] == 100:
                    position = {
                        "entry_index": i,
                        "entry_cost": current_cost
                    }

        if len(trades) == 0:
            return {"total_trades": 0, "message": "No trades generated"}

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
        return {"error": f"Backtest failed: {str(e)}"}


# ============ NEW ENDPOINTS (Multi-Strategy) ============

@app.get("/strategies")
def list_strategies():
    return {
        "strategies": [
            {
                "id": "iv_scalping",
                "name": "IV Scalping",
                "description": "Rule-based volatility scalping",
                "type": "Volatility-based",
                "status": "production"
            },
            {
                "id": "gamma_scalping",
                "name": "Gamma Scalping",
                "description": "Greeks-based delta hedging",
                "type": "Greeks-based",
                "status": "theoretical"
            },
            {
                "id": "hybrid",
                "name": "Hybrid (IV + Gamma)",
                "description": "Combined approach",
                "type": "Combined",
                "status": "development"
            }
        ]
    }


@app.get("/strategy/{strategy_name}/performance")
def get_strategy_performance(strategy_name: str):
    if strategy_name == "iv_scalping":
        return get_performance()
    
    elif strategy_name == "gamma_scalping":
        if gamma_performance:
            return {
                "strategy": "gamma_scalping",
                "total_trades": int(gamma_performance.get('total_trades', 0)),
                "win_rate": round(float(gamma_performance.get('win_rate', 0)), 1),
                "total_pnl": round(float(gamma_performance.get('total_pnl', 0)), 2),
                "profit_factor": round(float(gamma_performance.get('profit_factor', 0)), 2)
            }
        return {"status": "not_computed", "message": "Run backtest to generate data"}
    
    elif strategy_name == "hybrid":
        if hybrid_performance:
            return {
                "strategy": "hybrid",
                "total_trades": int(hybrid_performance.get('total_trades', 0)),
                "win_rate": round(float(hybrid_performance.get('win_rate', 0)), 1),
                "total_pnl": round(float(hybrid_performance.get('total_pnl', 0)), 2),
                "profit_factor": round(float(hybrid_performance.get('profit_factor', 0)), 2)
            }
        return {"status": "not_computed", "message": "Run backtest to generate data"}


@app.get("/strategy/compare")
def compare_strategies():
    strategies = []
    
    # IV Scalping
    if performance_df is not None:
        p = performance_df.iloc[0]
        strategies.append({
            "name": "iv_scalping",
            "total_trades": int(p["total_trades"]),
            "win_rate": round(float(p["win_rate"]), 1),
            "total_pnl": round(float(p["total_pnl"]), 2),
            "profit_factor": round(float(p["profit_factor"]), 2)
        })
    
    # Gamma Scalping
    if gamma_performance:
        strategies.append({
            "name": "gamma_scalping",
            "total_trades": int(gamma_performance['total_trades']),
            "win_rate": round(float(gamma_performance['win_rate']), 1),
            "total_pnl": round(float(gamma_performance['total_pnl']), 2),
            "profit_factor": round(float(gamma_performance['profit_factor']), 2)
        })
    else:
        strategies.append({
            "name": "gamma_scalping",
            "status": "not_computed"
        })
    
    # Hybrid
    if hybrid_performance:
        strategies.append({
            "name": "hybrid",
            "total_trades": int(hybrid_performance['total_trades']),
            "win_rate": round(float(hybrid_performance['win_rate']), 1),
            "total_pnl": round(float(hybrid_performance['total_pnl']), 2),
            "profit_factor": round(float(hybrid_performance['profit_factor']), 2)
        })
    else:
        strategies.append({
            "name": "hybrid",
            "status": "not_computed"
        })
    
    return {"strategies": strategies}


@app.get("/greeks")
def get_current_greeks():
    if straddle_df is None:
        return {"error": "Data not loaded"}
    
    try:
        last = straddle_df.iloc[-1]
        spot = float(last['spot'])
        iv = float(last['avg_iv'])
        
        greeks = calculate_greeks_simple(spot, spot, 7/365, iv)
        
        return {
            "timestamp": str(last['datetime']),
            "spot": round(spot, 2),
            "current_iv": round(iv, 2),
            "greeks": {
                "delta": round(greeks['delta'], 3),
                "gamma": round(greeks['gamma'], 4),
                "vega": round(greeks['vega'], 2),
                "theta": round(greeks['theta'], 2)
            }
        }
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


@app.get("/volatility-analysis")
def get_volatility_analysis(periods: int = Query(50, description="Number of periods")):
    if straddle_df is None:
        return {"error": "Data not loaded"}
    
    try:
        recent = straddle_df.tail(periods + 20).copy()
        recent['realized_vol'] = calculate_realized_volatility(recent['spot'], window=20)
        
        data = []
        for _, row in recent.tail(periods).iterrows():
            if pd.notna(row['realized_vol']):
                data.append({
                    "timestamp": str(row['datetime']),
                    "implied_vol": round(float(row['avg_iv']), 2),
                    "realized_vol": round(float(row['realized_vol']), 2),
                    "iv_rv_ratio": round(float(row['avg_iv'] / row['realized_vol']), 2)
                })
        
        current = recent.iloc[-1]
        current_iv = float(current['avg_iv'])
        current_rv = float(current['realized_vol']) if pd.notna(current['realized_vol']) else current_iv
        iv_rv_ratio = current_iv / current_rv
        
        if iv_rv_ratio < 0.9:
            assessment = "CHEAP"
            color = "green"
            message = "Options cheaper than realized movement"
        elif iv_rv_ratio > 1.2:
            assessment = "EXPENSIVE"
            color = "red"
            message = "Options expensive"
        else:
            assessment = "FAIR"
            color = "yellow"
            message = "Options fairly priced"
        
        return {
            "current": {
                "implied_vol": round(current_iv, 2),
                "realized_vol": round(current_rv, 2),
                "iv_rv_ratio": round(iv_rv_ratio, 2),
                "assessment": assessment,
                "color": color,
                "message": message
            },
            "periods": len(data),
            "data": data
        }
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


def get_recommendation(signal: str, iv: float, iv_pct: float) -> str:
    if signal == "BUY_STRADDLE":
        return f"Buy ATM straddle. IV at {iv:.1f}% ({iv_pct:.0f}th percentile)"
    elif signal == "EXIT":
        return "Exit position. Target met."
    return f"Wait. IV at {iv_pct:.0f}th percentile"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
