"""
NIFTY Trading System - Complete Backend v4.0
3 Strategies: IV Scalping, Gamma Scalping, Hybrid

All strategies integrated with comparison features
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Literal
import json

app = FastAPI(
    title="NIFTY Multi-Strategy Trading System",
    description="Three Trading Strategies: IV Scalping, Gamma Scalping, and Hybrid",
    version="4.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Global data storage
performance_data = {
    'iv_scalping': None,
    'gamma_scalping': None,
    'hybrid': None
}

trades_data = {
    'iv_scalping': None,
    'gamma_scalping': None,
    'hybrid': None
}

signals_df = None
straddle_df = None


@app.on_event("startup")
async def load_data():
    """Load all strategy data on startup"""
    global signals_df, straddle_df, performance_data, trades_data
    
    try:
        # Load original data
        signals_df = pd.read_csv("trading_signals.csv")
        signals_df["datetime"] = pd.to_datetime(signals_df["datetime"])
        straddle_df = pd.read_csv("straddle_data_prepared.csv")
        straddle_df["datetime"] = pd.to_datetime(straddle_df["datetime"])
        
        # Load IV scalping performance (existing)
        iv_perf = pd.read_csv("performance_metrics.csv")
        performance_data['iv_scalping'] = iv_perf.iloc[0].to_dict()
        
        iv_trades = pd.read_csv("backtest_results.csv")
        trades_data['iv_scalping'] = iv_trades
        
        # Load gamma and hybrid if they exist
        try:
            gamma_perf = pd.read_csv("gamma_performance_metrics.csv")
            performance_data['gamma_scalping'] = gamma_perf.iloc[0].to_dict()
            gamma_trades = pd.read_csv("gamma_backtest_results.csv")
            trades_data['gamma_scalping'] = gamma_trades
        except:
            print("⚠️ Gamma strategy data not found - will generate on first request")
        
        try:
            hybrid_perf = pd.read_csv("hybrid_performance_metrics.csv")
            performance_data['hybrid'] = hybrid_perf.iloc[0].to_dict()
            hybrid_trades = pd.read_csv("hybrid_backtest_results.csv")
            trades_data['hybrid'] = hybrid_trades
        except:
            print("⚠️ Hybrid strategy data not found - will generate on first request")
        
        print("✅ Data loaded successfully!")
        
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")


class BacktestParams(BaseModel):
    strategy: Literal["iv_scalping", "gamma_scalping", "hybrid"]
    iv_entry_percentile: int = 30
    profit_target: float = 10.0
    stop_loss: float = 20.0
    max_hold_time: int = 60
    gamma_threshold: float = 0.015
    hedge_threshold: float = 0.1


def calculate_realized_volatility(spot_prices, window=20):
    """Calculate realized volatility"""
    returns = np.log(spot_prices / spot_prices.shift(1))
    realized_vol = returns.rolling(window=window).std() * np.sqrt(252) * 100
    return realized_vol


def get_volatility_regime(current_iv, recent_ivs):
    """Determine volatility regime"""
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
    """Simplified Greeks calculation (approximate)"""
    # Simplified ATM Greeks approximation
    T = time_to_expiry
    sigma = iv / 100
    
    if T <= 0:
        return {'delta': 0, 'gamma': 0, 'vega': 0, 'theta': 0}
    
    # ATM approximations
    delta_call = 0.5
    delta_put = -0.5
    gamma = 0.4 / (spot * sigma * np.sqrt(T))
    vega = spot * 0.4 * np.sqrt(T)
    theta = -(spot * sigma * 0.4) / (2 * np.sqrt(T)) / 365
    
    return {
        'delta': delta_call + delta_put,  # Straddle delta ≈ 0
        'gamma': gamma * 2,  # Both call and put
        'vega': vega * 2,
        'theta': theta * 2
    }


@app.get("/")
def root():
    """API root with all available strategies"""
    return {
        "message": "NIFTY Multi-Strategy Trading System",
        "version": "4.0.0",
        "strategies": {
            "iv_scalping": "Volatility-based scalping (Original)",
            "gamma_scalping": "Greeks-based delta hedging (NEW)",
            "hybrid": "Combined IV + Gamma strategy (NEW)"
        },
        "endpoints": {
            "/strategies": "List all strategies",
            "/strategy/{name}/performance": "Get strategy performance",
            "/strategy/{name}/signal": "Get current signal for strategy",
            "/strategy/compare": "Compare all strategies",
            "/volatility-analysis": "IV vs RV analysis",
            "/greeks": "Current Greeks values"
        }
    }


@app.get("/strategies")
def list_strategies():
    """List all available strategies with brief descriptions"""
    return {
        "strategies": [
            {
                "id": "iv_scalping",
                "name": "IV Scalping",
                "description": "Buys straddles when IV is low, exits on profit target or IV expansion",
                "type": "Volatility-based",
                "risk_level": "Medium",
                "best_for": "Steady returns, proven strategy"
            },
            {
                "id": "gamma_scalping",
                "name": "Gamma Scalping",
                "description": "Delta hedges continuously to profit from realized volatility",
                "type": "Greeks-based",
                "risk_level": "Medium-High",
                "best_for": "Active scalping, high-frequency trading"
            },
            {
                "id": "hybrid",
                "name": "Hybrid (IV + Gamma)",
                "description": "Combines both strategies for highest win rate",
                "type": "Combined",
                "risk_level": "Medium",
                "best_for": "Best signals, quality over quantity"
            }
        ]
    }


@app.get("/strategy/{strategy_name}/performance")
def get_strategy_performance(strategy_name: str):
    """Get performance metrics for a specific strategy"""
    
    if strategy_name not in ['iv_scalping', 'gamma_scalping', 'hybrid']:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    perf = performance_data.get(strategy_name)
    
    if perf is None:
        return {
            "strategy": strategy_name,
            "status": "not_computed",
            "message": "Run backtest to generate performance data"
        }
    
    return {
        "strategy": strategy_name,
        "total_trades": int(perf.get('total_trades', 0)),
        "winning_trades": int(perf.get('winning_trades', 0)),
        "losing_trades": int(perf.get('losing_trades', 0)),
        "win_rate": round(float(perf.get('win_rate', 0)), 1),
        "total_pnl": round(float(perf.get('total_pnl', 0)), 2),
        "avg_pnl": round(float(perf.get('avg_pnl', 0)), 2),
        "profit_factor": round(float(perf.get('profit_factor', 0)), 2),
        "sharpe_ratio": round(float(perf.get('sharpe_ratio', 0)), 2),
        "max_drawdown": round(float(perf.get('max_drawdown', 0)), 2)
    }


@app.get("/strategy/{strategy_name}/signal")
def get_strategy_signal(strategy_name: str):
    """Get current trading signal for a specific strategy"""
    
    if signals_df is None or straddle_df is None:
        return {"error": "Data not loaded"}
    
    try:
        last = signals_df.iloc[-1]
        recent = signals_df.tail(100)
        current_iv = float(last["iv"])
        
        spot = float(last["spot"])
        straddle_cost = float(straddle_df.iloc[-1]["straddle_cost"])
        
        # Calculate IV percentile
        iv_percentile = float((recent["iv"] <= current_iv).sum() / len(recent) * 100)
        
        # Calculate Greeks
        greeks = calculate_greeks_simple(spot, spot, 7/365, current_iv)
        
        # Get volatility regime
        regime = get_volatility_regime(current_iv, recent["iv"])
        
        # Strategy-specific signals
        if strategy_name == "iv_scalping":
            # IV-based signal
            if iv_percentile <= 30:
                signal = "BUY"
                confidence = 70 if iv_percentile <= 20 else 60
                reasoning = f"IV at {iv_percentile:.0f}th percentile - ENTRY ZONE"
            else:
                signal = "HOLD"
                confidence = 30
                reasoning = f"IV at {iv_percentile:.0f}th percentile - WAIT"
        
        elif strategy_name == "gamma_scalping":
            # Gamma-based signal
            if greeks['gamma'] >= 0.015:
                signal = "BUY"
                confidence = 75
                reasoning = f"Gamma {greeks['gamma']:.4f} - HIGH GAMMA ZONE"
            else:
                signal = "HOLD"
                confidence = 35
                reasoning = f"Gamma {greeks['gamma']:.4f} - LOW GAMMA"
        
        elif strategy_name == "hybrid":
            # Combined signal
            if iv_percentile <= 30 and greeks['gamma'] >= 0.015:
                signal = "BUY"
                confidence = 85
                reasoning = "LOW IV + HIGH GAMMA - BEST SIGNAL!"
            elif iv_percentile <= 30:
                signal = "HOLD"
                confidence = 50
                reasoning = "Low IV but Gamma not optimal"
            elif greeks['gamma'] >= 0.015:
                signal = "HOLD"
                confidence = 50
                reasoning = "High Gamma but IV not low enough"
            else:
                signal = "HOLD"
                confidence = 20
                reasoning = "Neither condition met - WAIT"
        
        else:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        return {
            "strategy": strategy_name,
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "timestamp": str(last["datetime"]),
            "spot_price": round(spot, 2),
            "straddle_cost": round(straddle_cost, 2),
            "current_iv": round(current_iv, 2),
            "iv_percentile": round(iv_percentile, 0),
            "greeks": {
                "delta": round(greeks['delta'], 3),
                "gamma": round(greeks['gamma'], 4),
                "vega": round(greeks['vega'], 2),
                "theta": round(greeks['theta'], 2)
            },
            "volatility_regime": regime
        }
    
    except Exception as e:
        return {"error": f"Error generating signal: {str(e)}"}


@app.get("/strategy/compare")
def compare_strategies():
    """Compare all three strategies side-by-side"""
    
    comparison = {
        "strategies": []
    }
    
    for strategy_name in ['iv_scalping', 'gamma_scalping', 'hybrid']:
        perf = performance_data.get(strategy_name)
        
        if perf:
            comparison["strategies"].append({
                "name": strategy_name,
                "total_trades": int(perf.get('total_trades', 0)),
                "win_rate": round(float(perf.get('win_rate', 0)), 1),
                "total_pnl": round(float(perf.get('total_pnl', 0)), 2),
                "profit_factor": round(float(perf.get('profit_factor', 0)), 2),
                "sharpe_ratio": round(float(perf.get('sharpe_ratio', 0)), 2)
            })
        else:
            comparison["strategies"].append({
                "name": strategy_name,
                "status": "not_computed",
                "message": "Run backtest to generate data"
            })
    
    # Determine best strategy for each metric
    if all(perf is not None for perf in performance_data.values()):
        pnls = [s['total_pnl'] for s in comparison['strategies'] if 'total_pnl' in s]
        win_rates = [s['win_rate'] for s in comparison['strategies'] if 'win_rate' in s]
        pfs = [s['profit_factor'] for s in comparison['strategies'] if 'profit_factor' in s]
        
        comparison["best"] = {
            "highest_pnl": comparison['strategies'][pnls.index(max(pnls))]['name'] if pnls else None,
            "highest_win_rate": comparison['strategies'][win_rates.index(max(win_rates))]['name'] if win_rates else None,
            "highest_profit_factor": comparison['strategies'][pfs.index(max(pfs))]['name'] if pfs else None
        }
    
    return comparison


@app.get("/greeks")
def get_current_greeks():
    """Get current Greeks values for ATM straddle"""
    
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
            },
            "interpretation": {
                "delta": "Near 0 (neutral position)" if abs(greeks['delta']) < 0.1 else "Directional bias",
                "gamma": "HIGH - Good for scalping" if greeks['gamma'] > 0.015 else "LOW - Scalping difficult",
                "vega": f"₹{greeks['vega']:.0f} gain per 1% IV increase",
                "theta": f"₹{abs(greeks['theta']):.0f} daily time decay"
            }
        }
    
    except Exception as e:
        return {"error": f"Error calculating Greeks: {str(e)}"}


@app.get("/volatility-analysis")
def get_volatility_analysis(periods: int = Query(50, description="Number of periods")):
    """Get IV vs RV comparison"""
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
            message = "Options cheaper than realized movement - good buying opportunity!"
        elif iv_rv_ratio > 1.2:
            assessment = "EXPENSIVE"
            color = "red"
            message = "Options expensive - avoid buying!"
        else:
            assessment = "FAIR"
            color = "yellow"
            message = "Options fairly priced."
        
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


# Maintain existing endpoints for backward compatibility
@app.get("/current-signal")
def get_current_signal():
    """Legacy endpoint - returns IV scalping signal"""
    return get_strategy_signal("iv_scalping")


@app.get("/performance")
def get_performance():
    """Legacy endpoint - returns IV scalping performance"""
    return get_strategy_performance("iv_scalping")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
