import pandas as pd
import numpy as np

def calculate_transaction_costs(entry_cost, exit_cost):
    brokerage = 40
    stt = entry_cost * 0.0005
    exchange = (entry_cost + exit_cost) * 0.00053
    gst = brokerage * 0.18
    return brokerage + stt + exchange + gst


print("=" * 70)
print("SHORT STRADDLE STRATEGY (SELLER SIDE)")
print("=" * 70)

# Load data
df = pd.read_csv("straddle_data_prepared.csv")
df["datetime"] = pd.to_datetime(df["datetime"])

print(f"Data: {len(df)} rows")

# Strategy Parameters
LOOKBACK = 100
IV_THRESHOLD = 75
PROFIT_TARGET = 50.0
STOP_LOSS = 100.0
HOLD_PERIODS = 3 * 75

print("Strategy: SELL straddles when IV is expensive")
print(f"IV Threshold: {IV_THRESHOLD}th percentile")
print(f"Profit Target: {PROFIT_TARGET}%")
print(f"Stop Loss: {STOP_LOSS}%")
print(f"Hold: {HOLD_PERIODS // 75} days")

# IV Percentile
df["iv_percentile"] = df["avg_iv"].rolling(LOOKBACK).apply(
    lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100
)

trades = []
i = LOOKBACK

while i < len(df) - HOLD_PERIODS:

    if df.iloc[i]["iv_percentile"] >= IV_THRESHOLD:

        entry_cost = df.iloc[i]["straddle_cost"]
        entry_time = df.iloc[i]["datetime"]

        max_idx = min(i + HOLD_PERIODS, len(df) - 1)
        exit_idx = max_idx
        exit_reason = "TIME_LIMIT"

        for j in range(i + 1, max_idx + 1):

            current_cost = df.iloc[j]["straddle_cost"]
            pnl = entry_cost - current_cost
            pnl_pct = (pnl / entry_cost) * 100

            if pnl_pct >= PROFIT_TARGET:
                exit_idx = j
                exit_reason = "PROFIT_TARGET"
                break

            elif pnl_pct <= -STOP_LOSS:
                exit_idx = j
                exit_reason = "STOP_LOSS"
                break

        exit_cost = df.iloc[exit_idx]["straddle_cost"]
        raw_pnl = entry_cost - exit_cost
        costs = calculate_transaction_costs(entry_cost, exit_cost)
        net_pnl = raw_pnl - costs

        trades.append({
            "entry_time": entry_time,
            "exit_time": df.iloc[exit_idx]["datetime"],
            "entry_credit": round(entry_cost, 2),
            "exit_cost": round(exit_cost, 2),
            "raw_pnl": round(raw_pnl, 2),
            "costs": round(costs, 2),
            "net_pnl": round(net_pnl, 2),
            "net_pnl_pct": round((net_pnl / entry_cost) * 100, 2),
            "result": "WIN" if net_pnl > 0 else "LOSS",
            "exit_reason": exit_reason,
            "hold_days": round((exit_idx - i) / 75, 1)
        })

        i = exit_idx + 12
    else:
        i += 1


# ================= RESULTS =================

if len(trades) == 0:
    print("No SHORT trades generated!")
    print("Try lowering IV threshold to 70 or 65")

else:
    trades_df = pd.DataFrame(trades)

    total = len(trades_df)
    wins = len(trades_df[trades_df["result"] == "WIN"])
    total_pnl = trades_df["net_pnl"].sum()
    win_rate = (wins / total) * 100

    print("=" * 70)
    print("SHORT STRADDLE RESULTS (SELLER)")
    print("=" * 70)

    print(f"Total Trades: {total}")
    print(f"Wins: {wins}")
    print(f"Losses: {total - wins}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total P&L: ₹{total_pnl:,.2f}")
    print(f"Avg P&L: ₹{trades_df['net_pnl'].mean():.2f}")

    avg_win = 0
    avg_loss = 0

    if wins > 0:
        avg_win = trades_df[trades_df["result"] == "WIN"]["net_pnl"].mean()
        print(f"Avg Win: ₹{avg_win:.2f}")

    if (total - wins) > 0:
        avg_loss = trades_df[trades_df["result"] == "LOSS"]["net_pnl"].mean()
        print(f"Avg Loss: ₹{avg_loss:.2f}")

    perf = {
        "strategy": "short_straddle",
        "total_trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(trades_df["net_pnl"].mean(), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_hold_days": round(trades_df["hold_days"].mean(), 1),
        "total_costs": round(trades_df["costs"].sum(), 2)
    }

    pd.DataFrame([perf]).to_csv("short_straddle_performance.csv", index=False)
    trades_df.to_csv("short_straddle_trades.csv", index=False)

    print("Results saved to CSV files.")
    print("=" * 70)
    print("BUYER vs SELLER COMPARISON")
    print("=" * 70)
    print("LONG Straddle (Buyer):  -₹11,828")
    print(f"SHORT Straddle (Seller): ₹{total_pnl:,.2f}")
    print("Key Insight: In low volatility environments, SELLERS benefit from theta decay.")