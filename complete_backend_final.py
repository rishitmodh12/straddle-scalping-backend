"""
NIFTY STRADDLE TRADING SYSTEM - COMPLETE BACKEND
3 Strategies: IV Scalping, Gamma Scalping, Hybrid
Version: FINAL
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Optional, Literal

app = FastAPI(
    title="NIFTY Straddle Trading System",
    description="Complete 3-Strategy System with Precise Backtesting",
    version="FINAL"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Global data storage
straddle_df = None

# Strategy results storage
iv_results = None
gamma_results = None
hybrid_results = None

iv_trades = None
gamma_trades = None
hybrid_trades = None


@app.on_event("startup")
async def load_data():
    """Load prepared straddle data on startup"""
    global straddle_df
    
    try:
        straddle_df = pd.read_csv("straddle_data_prepared.csv")
        straddle_df['datetime'] = pd.to_datetime(straddle_df['datetime'])
        print(f"✅ Loaded {len(straddle_df)} straddle data points")
        
        # Load pre-computed strategy results if available
        try:
            global iv_results, gamma_results, hybrid_results
            global iv_trades, gamma_trades, hybrid_trades
            
            iv_results = pd.read_csv("iv_scalping_performance.csv").iloc[0].to_dict()
            iv_trades = pd.read_csv("iv_scalping_trades.csv")
            
            gamma_results = pd.read_csv("gamma_scalping_performance.csv").iloc[0].to_dict()
            gamma_trades = pd.read_csv("gamma_scalping_trades.csv")
            
            hybrid_results = pd.read_csv("hybrid_scalping_performance.csv").iloc[0].to_dict()
            hybrid_trades = pd.read_csv("hybrid_scalping_trades.csv")
            
            print("✅ Loaded all strategy results")
        except:
            print("⚠️ Strategy results not found - will compute on demand")
            
    except Exception as e:
        print(f"❌ Error loading data: {e}")


class BacktestParams(BaseModel):
    """Parameters for backtesting"""
    strategy: Literal["iv_scalping", "gamma_scalping", "hybrid"]
    iv_threshold: int = 25
    profit_target: float = 50.0
    stop_loss: float = 35.0
    hold_days: int = 3


def calculate_transaction_costs(entry_cost: float, exit_cost: float) -> float:
    """
    Calculate realistic transaction costs for straddle trade
    Zerodha-style: ₹20 per order + taxes
    """
    # Entry: 2 orders (Call + Put) = ₹40 brokerage
    # Exit: 2 orders = ₹40 brokerage
    brokerage = 40
    
    # STT on sell side (0.05%)
    stt = exit_cost * 0.0005
    
    # Exchange charges (~0.053%)
    exchange = (entry_cost + exit_cost) * 0.00053
    
    # GST on brokerage (18%)
    gst = brokerage * 0.18
    
    total = brokerage + stt + exchange + gst
    return round(total, 2)


def calculate_greeks_simple(spot: float, strike: float, time_to_expiry: float, iv: float):
    """Calculate simplified Greeks for ATM straddle"""
    
    T = time_to_expiry
    sigma = iv / 100
    
    if T <= 0 or sigma <= 0:
        return {'delta': 0, 'gamma': 0, 'vega': 0, 'theta': 0}
    
    # ATM straddle approximations
    gamma = 0.4 / (spot * sigma * np.sqrt(T))
    vega = spot * 0.4 * np.sqrt(T)
    theta = -(spot * sigma * 0.4) / (2 * np.sqrt(T)) / 365
    
    return {
        'delta': 0.02,  # Near 0 for ATM straddle
        'gamma': gamma * 2,  # Both call and put
        'vega': vega * 2,
        'theta': theta * 2
    }


# ==================== STRATEGY 1: IV SCALPING ====================

def backtest_iv_scalping(df: pd.DataFrame, params: dict):
    """
    IV Scalping Strategy
    Entry: IV at bottom X percentile
    Exit: Profit target, Stop loss, Time limit
    Hold: 2-5 days
    """
    
    print(f"\n{'='*60}")
    print("BACKTESTING: IV SCALPING STRATEGY")
    print(f"{'='*60}")
    
    LOOKBACK = 100
    IV_THRESHOLD = params.get('iv_threshold', 25)
    PROFIT_TARGET = params.get('profit_target', 50.0)
    STOP_LOSS = params.get('stop_loss', 35.0)
    HOLD_DAYS = params.get('hold_days', 3)
    HOLD_PERIODS = HOLD_DAYS * 75  # 75 periods per day (5-min intervals)
    
    # Calculate IV percentile
    df['iv_percentile'] = df['avg_iv'].rolling(LOOKBACK).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    
    trades = []
    i = LOOKBACK
    
    while i < len(df) - HOLD_PERIODS:
        
        # Check entry condition
        if df.iloc[i]['iv_percentile'] <= IV_THRESHOLD:
            
            entry_cost = df.iloc[i]['straddle_cost']
            entry_time = df.iloc[i]['datetime']
            entry_idx = i
            
            # Track position for HOLD_PERIODS
            max_idx = min(i + HOLD_PERIODS, len(df) - 1)
            
            exit_idx = max_idx
            exit_reason = "TIME_LIMIT"
            
            for j in range(i + 1, max_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                pnl_pct = ((current_cost - entry_cost) / entry_cost) * 100
                
                # Check exits
                if pnl_pct >= PROFIT_TARGET:
                    exit_idx = j
                    exit_reason = "PROFIT_TARGET"
                    break
                elif pnl_pct <= -STOP_LOSS:
                    exit_idx = j
                    exit_reason = "STOP_LOSS"
                    break
            
            # Calculate final P&L
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            exit_time = df.iloc[exit_idx]['datetime']
            
            raw_pnl = exit_cost - entry_cost
            costs = calculate_transaction_costs(entry_cost, exit_cost)
            net_pnl = raw_pnl - costs
            net_pnl_pct = (net_pnl / entry_cost) * 100
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'raw_pnl': round(raw_pnl, 2),
                'costs': round(costs, 2),
                'net_pnl': round(net_pnl, 2),
                'net_pnl_pct': round(net_pnl_pct, 2),
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason,
                'hold_days': round((exit_idx - entry_idx) / 75, 1)
            })
            
            # Jump past this trade
            i = exit_idx + 12  # Wait 1 hour
        else:
            i += 1
    
    return pd.DataFrame(trades)


# ==================== STRATEGY 2: GAMMA SCALPING ====================

def backtest_gamma_scalping(df: pd.DataFrame, params: dict):
    """
    Gamma Scalping Strategy
    Entry: High gamma zone + volatility setup
    Exit: Delta hedging profits accumulated
    Hold: 2-5 days with continuous hedging
    """
    
    print(f"\n{'='*60}")
    print("BACKTESTING: GAMMA SCALPING STRATEGY")
    print(f"{'='*60}")
    
    GAMMA_THRESHOLD = 0.015
    PROFIT_TARGET = params.get('profit_target', 50.0)
    STOP_LOSS = params.get('stop_loss', 35.0)
    HOLD_DAYS = params.get('hold_days', 3)
    HOLD_PERIODS = HOLD_DAYS * 75
    
    trades = []
    i = 100
    
    while i < len(df) - HOLD_PERIODS:
        
        row = df.iloc[i]
        spot = row['spot']
        iv = row['avg_iv']
        
        # Calculate gamma
        greeks = calculate_greeks_simple(spot, spot, 7/365, iv)
        
        # Entry: High gamma
        if greeks['gamma'] >= GAMMA_THRESHOLD:
            
            entry_cost = row['straddle_cost']
            entry_time = row['datetime']
            entry_spot = spot
            
            # Simulate delta hedging
            hedge_pnl = 0
            last_hedge_spot = spot
            hedge_count = 0
            
            max_idx = min(i + HOLD_PERIODS, len(df) - 1)
            
            exit_idx = max_idx
            exit_reason = "TIME_LIMIT"
            
            for j in range(i + 1, max_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                current_spot = df.iloc[j]['spot']
                
                # Delta hedging simulation
                spot_move = abs(current_spot - last_hedge_spot)
                if spot_move > (last_hedge_spot * 0.005):  # 0.5% move
                    # Hedge profit from scalping gamma
                    hedge_profit = spot_move * greeks['gamma'] * spot * 0.3
                    hedge_pnl += hedge_profit
                    last_hedge_spot = current_spot
                    hedge_count += 1
                
                # Calculate total P&L
                position_pnl = current_cost - entry_cost
                total_pnl = position_pnl + hedge_pnl
                total_pnl_pct = (total_pnl / entry_cost) * 100
                
                # Check exits
                if total_pnl_pct >= PROFIT_TARGET:
                    exit_idx = j
                    exit_reason = "PROFIT_TARGET"
                    break
                elif total_pnl_pct <= -STOP_LOSS:
                    exit_idx = j
                    exit_reason = "STOP_LOSS"
                    break
            
            # Final P&L
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            exit_time = df.iloc[exit_idx]['datetime']
            
            position_pnl = exit_cost - entry_cost
            total_raw_pnl = position_pnl + hedge_pnl
            
            costs = calculate_transaction_costs(entry_cost, exit_cost)
            # Add hedging costs (₹10 per hedge)
            costs += hedge_count * 10
            
            net_pnl = total_raw_pnl - costs
            net_pnl_pct = (net_pnl / entry_cost) * 100
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'position_pnl': round(position_pnl, 2),
                'hedge_pnl': round(hedge_pnl, 2),
                'raw_pnl': round(total_raw_pnl, 2),
                'costs': round(costs, 2),
                'net_pnl': round(net_pnl, 2),
                'net_pnl_pct': round(net_pnl_pct, 2),
                'hedge_count': hedge_count,
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason,
                'hold_days': round((exit_idx - i) / 75, 1)
            })
            
            i = exit_idx + 12
        else:
            i += 1
    
    return pd.DataFrame(trades)


# ==================== STRATEGY 3: HYBRID ====================

def backtest_hybrid(df: pd.DataFrame, params: dict):
    """
    Hybrid Strategy
    Entry: Low IV AND High Gamma (both conditions)
    Exit: Best of both strategies
    Hold: 2-5 days
    """
    
    print(f"\n{'='*60}")
    print("BACKTESTING: HYBRID STRATEGY")
    print(f"{'='*60}")
    
    LOOKBACK = 100
    IV_THRESHOLD = params.get('iv_threshold', 25)
    GAMMA_THRESHOLD = 0.015
    PROFIT_TARGET = params.get('profit_target', 50.0)
    STOP_LOSS = params.get('stop_loss', 35.0)
    HOLD_DAYS = params.get('hold_days', 3)
    HOLD_PERIODS = HOLD_DAYS * 75
    
    # Calculate IV percentile
    df['iv_percentile'] = df['avg_iv'].rolling(LOOKBACK).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    
    trades = []
    i = LOOKBACK
    
    while i < len(df) - HOLD_PERIODS:
        
        row = df.iloc[i]
        iv_pct = row['iv_percentile']
        
        # Calculate gamma
        greeks = calculate_greeks_simple(row['spot'], row['spot'], 7/365, row['avg_iv'])
        
        # Entry: BOTH conditions must be met
        if iv_pct <= IV_THRESHOLD and greeks['gamma'] >= GAMMA_THRESHOLD:
            
            entry_cost = row['straddle_cost']
            entry_time = row['datetime']
            
            # Track both position and hedging
            hedge_pnl = 0
            last_hedge_spot = row['spot']
            hedge_count = 0
            
            max_idx = min(i + HOLD_PERIODS, len(df) - 1)
            
            exit_idx = max_idx
            exit_reason = "TIME_LIMIT"
            
            for j in range(i + 1, max_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                current_spot = df.iloc[j]['spot']
                
                # Hedging
                spot_move = abs(current_spot - last_hedge_spot)
                if spot_move > (last_hedge_spot * 0.005):
                    hedge_profit = spot_move * greeks['gamma'] * row['spot'] * 0.3
                    hedge_pnl += hedge_profit
                    last_hedge_spot = current_spot
                    hedge_count += 1
                
                # Total P&L
                position_pnl = current_cost - entry_cost
                total_pnl = position_pnl + hedge_pnl
                total_pnl_pct = (total_pnl / entry_cost) * 100
                
                # Exits
                if total_pnl_pct >= PROFIT_TARGET:
                    exit_idx = j
                    exit_reason = "PROFIT_TARGET"
                    break
                elif total_pnl_pct <= -STOP_LOSS:
                    exit_idx = j
                    exit_reason = "STOP_LOSS"
                    break
            
            # Final
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            exit_time = df.iloc[exit_idx]['datetime']
            
            position_pnl = exit_cost - entry_cost
            total_raw_pnl = position_pnl + hedge_pnl
            
            costs = calculate_transaction_costs(entry_cost, exit_cost)
            costs += hedge_count * 10
            
            net_pnl = total_raw_pnl - costs
            net_pnl_pct = (net_pnl / entry_cost) * 100
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'position_pnl': round(position_pnl, 2),
                'hedge_pnl': round(hedge_pnl, 2),
                'raw_pnl': round(total_raw_pnl, 2),
                'costs': round(costs, 2),
                'net_pnl': round(net_pnl, 2),
                'net_pnl_pct': round(net_pnl_pct, 2),
                'hedge_count': hedge_count,
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason,
                'hold_days': round((exit_idx - i) / 75, 1)
            })
            
            i = exit_idx + 12
        else:
            i += 1
    
    return pd.DataFrame(trades)


def calculate_performance_metrics(trades_df: pd.DataFrame):
    """Calculate comprehensive performance metrics"""
    
    if len(trades_df) == 0:
        return None
    
    total_trades = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100
    
    total_pnl = trades_df['net_pnl'].sum()
    avg_pnl = trades_df['net_pnl'].mean()
    
    winners = trades_df[trades_df['result'] == 'WIN']
    losers = trades_df[trades_df['result'] == 'LOSS']
    
    avg_win = winners['net_pnl'].mean() if len(winners) > 0 else 0
    avg_loss = losers['net_pnl'].mean() if len(losers) > 0 else 0
    
    total_wins_amt = winners['net_pnl'].sum() if len(winners) > 0 else 0
    total_loss_amt = abs(losers['net_pnl'].sum()) if len(losers) > 0 else 0
    
    profit_factor = total_wins_amt / total_loss_amt if total_loss_amt > 0 else 0
    
    # Sharpe ratio
    sharpe = (avg_pnl / trades_df['net_pnl'].std()) if trades_df['net_pnl'].std() > 0 else 0
    
    # Max drawdown
    cumulative = trades_df['net_pnl'].cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    max_drawdown = drawdown.min()
    
    return {
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': round(win_rate, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(avg_pnl, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'sharpe_ratio': round(sharpe, 2),
        'max_drawdown': round(max_drawdown, 2),
        'avg_hold_days': round(trades_df['hold_days'].mean(), 1),
        'total_costs': round(trades_df['costs'].sum(), 2)
    }


# ==================== API ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "message": "NIFTY Straddle Trading System",
        "version": "FINAL",
        "strategies": ["iv_scalping", "gamma_scalping", "hybrid"],
        "status": "operational"
    }


@app.get("/dashboard/iv_scalping")
def get_iv_scalping_data():
    """Get IV Scalping strategy data for dashboard"""
    
    if iv_results is None:
        return {"error": "IV scalping data not computed yet"}
    
    return {
        "strategy": "IV Scalping",
        "description": "Entry when IV is in bottom 25%, exit on profit/stop/time",
        "performance": iv_results,
        "recent_trades": iv_trades.tail(10).to_dict('records') if iv_trades is not None else []
    }


@app.get("/dashboard/gamma_scalping")
def get_gamma_scalping_data():
    """Get Gamma Scalping strategy data for dashboard"""
    
    if gamma_results is None:
        return {"error": "Gamma scalping data not computed yet"}
    
    return {
        "strategy": "Gamma Scalping",
        "description": "High gamma positions with continuous delta hedging",
        "performance": gamma_results,
        "recent_trades": gamma_trades.tail(10).to_dict('records') if gamma_trades is not None else []
    }


@app.get("/dashboard/hybrid")
def get_hybrid_data():
    """Get Hybrid strategy data for dashboard"""
    
    if hybrid_results is None:
        return {"error": "Hybrid data not computed yet"}
    
    return {
        "strategy": "Hybrid",
        "description": "Combines low IV entry with gamma scalping hedging",
        "performance": hybrid_results,
        "recent_trades": hybrid_trades.tail(10).to_dict('records') if hybrid_trades is not None else []
    }


@app.post("/backtest")
def run_backtest(params: BacktestParams):
    """Run precise backtest with custom parameters"""
    
    if straddle_df is None:
        return {"error": "Data not loaded"}
    
    params_dict = {
        'iv_threshold': params.iv_threshold,
        'profit_target': params.profit_target,
        'stop_loss': params.stop_loss,
        'hold_days': params.hold_days
    }
    
    # Run appropriate strategy
    if params.strategy == "iv_scalping":
        trades_df = backtest_iv_scalping(straddle_df, params_dict)
    elif params.strategy == "gamma_scalping":
        trades_df = backtest_gamma_scalping(straddle_df, params_dict)
    elif params.strategy == "hybrid":
        trades_df = backtest_hybrid(straddle_df, params_dict)
    else:
        return {"error": "Invalid strategy"}
    
    if len(trades_df) == 0:
        return {
            "strategy": params.strategy,
            "total_trades": 0,
            "message": "No trades generated with these parameters"
        }
    
    # Calculate performance
    performance = calculate_performance_metrics(trades_df)
    
    return {
        "strategy": params.strategy,
        "parameters": params_dict,
        "performance": performance,
        "sample_trades": trades_df.head(5).to_dict('records')
    }


@app.get("/compare")
def compare_all_strategies():
    """Compare all three strategies"""
    
    if not all([iv_results, gamma_results, hybrid_results]):
        return {"error": "Not all strategies have been computed"}
    
    strategies = [
        {"name": "IV Scalping", "data": iv_results},
        {"name": "Gamma Scalping", "data": gamma_results},
        {"name": "Hybrid", "data": hybrid_results}
    ]
    
    # Determine winners
    best_pnl = max(strategies, key=lambda x: x['data']['total_pnl'])
    best_win_rate = max(strategies, key=lambda x: x['data']['win_rate'])
    best_sharpe = max(strategies, key=lambda x: x['data']['sharpe_ratio'])
    best_pf = max(strategies, key=lambda x: x['data']['profit_factor'])
    
    return {
        "strategies": [
            {
                "name": s['name'],
                "total_trades": s['data']['total_trades'],
                "win_rate": s['data']['win_rate'],
                "total_pnl": s['data']['total_pnl'],
                "profit_factor": s['data']['profit_factor'],
                "sharpe_ratio": s['data']['sharpe_ratio']
            }
            for s in strategies
        ],
        "winners": {
            "best_pnl": best_pnl['name'],
            "best_win_rate": best_win_rate['name'],
            "best_sharpe": best_sharpe['name'],
            "best_profit_factor": best_pf['name']
        },
        "recommendation": best_pnl['name']  # Recommend based on total P&L
    }


@app.get("/strategy_info")
def get_strategy_information():
    """Get detailed information about each strategy"""
    
    return {
        "iv_scalping": {
            "name": "IV Scalping",
            "principle": "Buy when volatility is cheap, sell when expensive",
            "entry": "IV in bottom 25th percentile (historically low volatility)",
            "exit": [
                "50% profit target reached",
                "35% stop loss hit",
                "3 days time limit"
            ],
            "advantages": [
                "Simple to understand and implement",
                "Works well in mean-reverting volatility",
                "Lower transaction costs (no hedging)"
            ],
            "disadvantages": [
                "Misses opportunities during normal IV",
                "No active risk management",
                "Purely directional bet on volatility"
            ],
            "best_for": "Steady, conservative traders"
        },
        "gamma_scalping": {
            "name": "Gamma Scalping",
            "principle": "Profit from price swings via continuous delta hedging",
            "entry": "High gamma positions (near ATM, near expiry)",
            "exit": [
                "Accumulated hedging profits reach target",
                "Position P&L hits stop loss",
                "Time limit reached"
            ],
            "advantages": [
                "Profits from volatility, not direction",
                "Active risk management via hedging",
                "Can profit even if spot doesn't move much"
            ],
            "disadvantages": [
                "Higher transaction costs (hedging fees)",
                "Requires active monitoring",
                "Complex execution"
            ],
            "best_for": "Active traders with technical knowledge"
        },
        "hybrid": {
            "name": "Hybrid Strategy",
            "principle": "Combines best of both: cheap IV + gamma scalping",
            "entry": "Low IV AND high gamma (both conditions must be met)",
            "exit": [
                "Either strategy's profit target",
                "Either strategy's stop loss",
                "Time limit"
            ],
            "advantages": [
                "Most selective (highest quality setups)",
                "Dual profit sources (IV + gamma)",
                "Best risk-reward profile"
            ],
            "disadvantages": [
                "Fewer trading opportunities",
                "Still has hedging costs",
                "Requires both conditions to align"
            ],
            "best_for": "Patient traders seeking best setups"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Change in both files:
def calculate_transaction_costs(entry_cost, exit_cost):
    return 30  # Was 50, now 30 (aggressive broker pricing)