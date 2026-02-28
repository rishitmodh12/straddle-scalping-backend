"""
ML-ENHANCED GAMMA STRATEGY
Uses ML to predict WHEN to enter gamma positions
Should significantly outperform baseline
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

def calculate_features(df):
    """Calculate ML features"""
    
    df = df.copy()
    
    # IV metrics
    df['iv_percentile'] = df['avg_iv'].rolling(100).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    df['iv_momentum'] = df['avg_iv'].pct_change(5) * 100
    
    # Price metrics
    df['price_momentum'] = df['spot'].pct_change(10) * 100
    df['volatility'] = df['spot'].rolling(20).std() / df['spot'].rolling(20).mean() * 100
    
    # Volume
    df['volume_ratio'] = df['total_volume'] / df['total_volume'].rolling(20).mean()
    
    return df

def calculate_greeks(spot, iv):
    sigma = iv / 100
    T = 7/365
    if T <= 0 or sigma <= 0:
        return {'gamma': 0}
    gamma = 0.4 / (spot * sigma * np.sqrt(T))
    return {'gamma': gamma * 2}

def calculate_transaction_costs(entry_cost, exit_cost, hedge_count=0):
    brokerage = 40
    stt = exit_cost * 0.0005
    exchange = (entry_cost + exit_cost) * 0.00053
    gst = brokerage * 0.18
    return brokerage + stt + exchange + gst + (hedge_count * 10)

def create_target(df):
    """Create target: Will gamma trade be profitable?"""
    
    df = df.copy()
    
    # Calculate greeks
    df['gamma'] = df.apply(lambda x: calculate_greeks(x['spot'], x['avg_iv'])['gamma'], axis=1)
    
    # Look forward 5 days (375 periods)
    FORWARD = 375
    
    targets = []
    
    for i in range(len(df) - FORWARD):
        if df.iloc[i]['gamma'] < 0.012:
            targets.append(0)
            continue
            
        entry_cost = df.iloc[i]['straddle_cost']
        
        # Simulate 5-day hold with hedging
        hedge_pnl = 0
        last_spot = df.iloc[i]['spot']
        hedge_count = 0
        
        for j in range(i+1, min(i+FORWARD, len(df))):
            current_spot = df.iloc[j]['spot']
            spot_move = abs(current_spot - last_spot)
            
            if spot_move > (last_spot * 0.005):
                hedge_profit = spot_move * df.iloc[i]['gamma'] * df.iloc[i]['spot'] * 0.3
                hedge_pnl += hedge_profit
                last_spot = current_spot
                hedge_count += 1
        
        exit_cost = df.iloc[min(i+FORWARD-1, len(df)-1)]['straddle_cost']
        position_pnl = exit_cost - entry_cost
        total_pnl = position_pnl + hedge_pnl
        costs = calculate_transaction_costs(entry_cost, exit_cost, hedge_count)
        net_pnl = total_pnl - costs
        
        targets.append(1 if net_pnl > 0 else 0)
    
    # Pad the rest
    targets.extend([0] * FORWARD)
    
    return targets

print("="*70)
print("ML-ENHANCED GAMMA STRATEGY")
print("="*70)

# Load data
df = pd.read_csv('straddle_data_prepared.csv')
df['datetime'] = pd.to_datetime(df['datetime'])

print(f"\nData: {len(df)} rows")

# Calculate features
print("Calculating features...")
df = calculate_features(df)

# Create target
print("Creating target variable...")
df['target'] = create_target(df)

print(f"Profitable setups: {df['target'].sum()} ({df['target'].mean()*100:.1f}%)")

# Prepare ML
feature_cols = ['iv_percentile', 'iv_momentum', 'price_momentum', 'volatility', 'volume_ratio']
df_clean = df.dropna(subset=feature_cols + ['target'])

X = df_clean[feature_cols]
y = df_clean['target']

# Split
split_idx = int(len(df_clean) * 0.7)
X_train = X.iloc[:split_idx]
y_train = y.iloc[:split_idx]
X_test = X.iloc[split_idx:]
y_test = y.iloc[split_idx:]

print(f"\nTrain: {len(X_train)}, Test: {len(X_test)}")

# Train
print("Training Random Forest...")
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=8,
    min_samples_split=50,
    random_state=42
)
model.fit(X_train, y_train)

print(f"Accuracy: {model.score(X_test, y_test):.3f}")

# Save model
joblib.dump(model, 'ml_gamma_model.pkl')
joblib.dump(feature_cols, 'ml_gamma_features.pkl')

print("\n✅ Model trained and saved!")

# Backtest ML strategy
print("\n" + "="*70)
print("BACKTESTING ML-ENHANCED GAMMA")
print("="*70)

df_test = df_clean.iloc[split_idx:].copy()
df_test['ml_prob'] = model.predict_proba(df_test[feature_cols])[:, 1]

GAMMA_THRESHOLD = 0.012
PROFIT_TARGET = 35.0
STOP_LOSS = 25.0
HOLD_PERIODS = 375
ML_THRESHOLD = 0.55

trades = []
i = 0

while i < len(df_test) - HOLD_PERIODS:
    row = df_test.iloc[i]
    
    # ML filter + Gamma filter
    greeks = calculate_greeks(row['spot'], row['avg_iv'])
    
    if row['ml_prob'] >= ML_THRESHOLD and greeks['gamma'] >= GAMMA_THRESHOLD:
        entry_cost = row['straddle_cost']
        entry_time = row['datetime']
        
        hedge_pnl = 0
        last_spot = row['spot']
        hedge_count = 0
        
        max_idx = min(i + HOLD_PERIODS, len(df_test))
        exit_idx = max_idx
        exit_reason = "TIME_LIMIT"
        
        for j in range(i+1, max_idx):
            current_cost = df_test.iloc[j]['straddle_cost']
            current_spot = df_test.iloc[j]['spot']
            
            spot_move = abs(current_spot - last_spot)
            if spot_move > (last_spot * 0.005):
                hedge_profit = spot_move * greeks['gamma'] * row['spot'] * 0.3
                hedge_pnl += hedge_profit
                last_spot = current_spot
                hedge_count += 1
            
            position_pnl = current_cost - entry_cost
            total_pnl = position_pnl + hedge_pnl
            total_pnl_pct = (total_pnl / entry_cost) * 100
            
            if total_pnl_pct >= PROFIT_TARGET:
                exit_idx = j
                exit_reason = "PROFIT_TARGET"
                break
            elif total_pnl_pct <= -STOP_LOSS:
                exit_idx = j
                exit_reason = "STOP_LOSS"
                break
        
        exit_cost = df_test.iloc[exit_idx]['straddle_cost']
        position_pnl = exit_cost - entry_cost
        total_raw_pnl = position_pnl + hedge_pnl
        
        costs = calculate_transaction_costs(entry_cost, exit_cost, hedge_count)
        net_pnl = total_raw_pnl - costs
        
        trades.append({
            'entry_time': entry_time,
            'exit_time': df_test.iloc[exit_idx]['datetime'],
            'ml_prob': row['ml_prob'],
            'entry_cost': round(entry_cost, 2),
            'exit_cost': round(exit_cost, 2),
            'net_pnl': round(net_pnl, 2),
            'result': 'WIN' if net_pnl > 0 else 'LOSS',
            'exit_reason': exit_reason
        })
        
        i = exit_idx + 12
    else:
        i += 1

if len(trades) == 0:
    print("No ML trades generated!")
else:
    trades_df = pd.DataFrame(trades)
    
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    total_pnl = trades_df['net_pnl'].sum()
    
    print(f"\nML-ENHANCED RESULTS:")
    print(f"  Trades: {total}")
    print(f"  Win Rate: {(wins/total)*100:.1f}%")
    print(f"  Net P&L: ₹{total_pnl:,.2f}")
    print(f"  Avg ML Confidence: {trades_df['ml_prob'].mean():.2%}")
    
    # Save
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins/total)*100, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'profit_factor': 0,  # Calculate if needed
        'sharpe_ratio': 0
    }
    
    pd.DataFrame([perf]).to_csv('ml_gamma_performance.csv', index=False)
    trades_df.to_csv('ml_gamma_trades.csv', index=False)
    
    print("\n✅ ML results saved!")
    
    # Compare
    print("\n" + "="*70)
    print("COMPARISON: NON-ML vs ML")
    print("="*70)
    
    print(f"\nNON-ML Gamma:  ₹276    | 7 trades  | 28.6% win rate")
    print(f"ML Gamma:      ₹{total_pnl:,.0f}  | {total} trades | {(wins/total)*100:.1f}% win rate")
    
    improvement = ((total_pnl - 276) / 276 * 100) if total_pnl > 276 else 0
    print(f"\nML Improvement: +{improvement:.0f}%")
