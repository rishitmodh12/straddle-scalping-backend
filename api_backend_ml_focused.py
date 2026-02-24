"""
ML-FOCUSED API - Simple and Clean
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

app = FastAPI(title="ML Trading API", version="6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data on startup
ml_performance = None
ml_trades = None
baseline_performance = None
baseline_trades = None

@app.on_event("startup")
async def load_data():
    global ml_performance, ml_trades, baseline_performance, baseline_trades
    
    ml_perf_df = pd.read_csv("ml_swing_performance.csv")
    ml_performance = ml_perf_df.iloc[0].to_dict()
    
    ml_trades = pd.read_csv("ml_swing_trades.csv")
    
    base_perf_df = pd.read_csv("realistic_scalping_performance.csv")
    baseline_performance = base_perf_df.iloc[0].to_dict()
    
    baseline_trades = pd.read_csv("realistic_scalping_results.csv")
    
    print("✅ All data loaded!")


@app.get("/")
def root():
    return {
        "message": "ML-Focused Trading API",
        "version": "6.0",
        "strategies": {
            "ml_strategy": "Main strategy - ML-powered",
            "baseline": "Rule-based comparison"
        }
    }


@app.get("/ml/performance")
def get_ml_performance():
    """Get ML strategy performance"""
    return {
        "strategy": "ML Swing Trading",
        "total_trades": int(ml_performance['total_trades']),
        "wins": int(ml_performance['wins']),
        "losses": int(ml_performance['losses']),
        "win_rate": float(ml_performance['win_rate']),
        "total_pnl": float(ml_performance['total_net_pnl']),
        "avg_pnl": float(ml_performance['avg_net_pnl']),
        "profit_factor": float(ml_performance['profit_factor']),
        "sharpe_ratio": float(ml_performance['sharpe_ratio'])
    }


@app.get("/ml/trades")
def get_ml_trades():
    """Get ML trade history"""
    return {
        "total": len(ml_trades),
        "trades": ml_trades.head(20).to_dict('records')
    }


@app.get("/baseline/performance")
def get_baseline_performance():
    """Get baseline (non-ML) performance"""
    return {
        "strategy": "Rule-Based Baseline",
        "total_trades": int(baseline_performance['total_trades']),
        "wins": int(baseline_performance['wins']),
        "win_rate": float(baseline_performance['win_rate']),
        "total_pnl": float(baseline_performance['total_net_pnl']),
        "avg_pnl": float(baseline_performance['avg_net_pnl']),
        "profit_factor": float(baseline_performance['profit_factor']),
        "sharpe_ratio": float(baseline_performance['sharpe_ratio'])
    }


@app.get("/compare")
def compare_strategies():
    """Compare ML vs Baseline"""
    
    ml_pnl = float(ml_performance['total_net_pnl'])
    base_pnl = float(baseline_performance['total_net_pnl'])
    
    return {
        "ml": {
            "trades": int(ml_performance['total_trades']),
            "win_rate": float(ml_performance['win_rate']),
            "pnl": ml_pnl,
            "profit_factor": float(ml_performance['profit_factor'])
        },
        "baseline": {
            "trades": int(baseline_performance['total_trades']),
            "win_rate": float(baseline_performance['win_rate']),
            "pnl": base_pnl,
            "profit_factor": float(baseline_performance['profit_factor'])
        },
        "improvement": {
            "win_rate_delta": round(float(ml_performance['win_rate']) - float(baseline_performance['win_rate']), 1),
            "pnl_delta": round(ml_pnl - base_pnl, 2),
            "pnl_improvement_pct": round((ml_pnl - base_pnl) / base_pnl * 100, 1) if base_pnl != 0 else 0
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)