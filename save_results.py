import pandas as pd
from gamma_strategy_complete import *

# Load data
straddle_df = pd.read_csv('straddle_data_prepared.csv')
straddle_df['datetime'] = pd.to_datetime(straddle_df['datetime'])

# Run Gamma Strategy
gamma_strategy = GammaScalpingStrategy()
gamma_trades = gamma_strategy.generate_signals(straddle_df, days_to_expiry=7)

# Run Hybrid Strategy
hybrid_strategy = HybridStrategy()
hybrid_trades = hybrid_strategy.generate_signals(straddle_df, days_to_expiry=7)

# Calculate performance
gamma_perf = calculate_performance_metrics(gamma_trades)
hybrid_perf = calculate_performance_metrics(hybrid_trades)

# Save Gamma results
gamma_perf_df = pd.DataFrame([gamma_perf])
gamma_perf_df.to_csv('gamma_performance_metrics.csv', index=False)
gamma_trades.to_csv('gamma_backtest_results.csv', index=False)

# Save Hybrid results
hybrid_perf_df = pd.DataFrame([hybrid_perf])
hybrid_perf_df.to_csv('hybrid_performance_metrics.csv', index=False)
hybrid_trades.to_csv('hybrid_backtest_results.csv', index=False)

print("✅ Files saved!")
print(f"Gamma: {gamma_perf['total_trades']} trades, ₹{gamma_perf['total_pnl']}")
print(f"Hybrid: {hybrid_perf['total_trades']} trades, ₹{hybrid_perf['total_pnl']}")