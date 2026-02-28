"""
COMPLETE SETUP - 3 STRATEGIES WITH NEW DATA
Run this ONE file to prepare everything
"""

import pandas as pd
import numpy as np
import sys

def prepare_data():
    """Step 1: Prepare straddle data"""
    
    print("\n" + "="*70)
    print("STEP 1: PREPARING DATA")
    print("="*70)
    
    try:
        df1 = pd.read_csv('NIFTY_part_1.csv')
        print(f"Loaded part 1: {len(df1)} rows")
        
        try:
            df2 = pd.read_csv('NIFTY_part_2.csv')
            df = pd.concat([df1, df2], ignore_index=True)
            print(f"Combined total: {len(df)} rows")
        except:
            df = df1
            
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    # Clean dates
    df['date'] = df['date'].astype(str).str.replace('=\"', '').str.replace('\"', '').str.strip()
    df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'].astype(str), format='%d-%m-%y %H:%M:%S', errors='coerce')
    
    # Filter ATM
    df_atm = df[df['strike_offset'] == 'ATM'].copy()
    calls = df_atm[df_atm['option_type'] == 'CALL'].copy()
    puts = df_atm[df_atm['option_type'] == 'PUT'].copy()
    
    # Merge
    straddle = pd.merge(
        calls[['datetime', 'close', 'iv', 'spot']],
        puts[['datetime', 'close', 'iv']],
        on='datetime',
        suffixes=('_call', '_put')
    )
    
    straddle['straddle_cost'] = straddle['close_call'] + straddle['close_put']
    straddle['avg_iv'] = (straddle['iv_call'] + straddle['iv_put']) / 2
    
    # Clean
    straddle = straddle[
        (straddle['straddle_cost'] > 0) &
        (straddle['avg_iv'] > 0) &
        (straddle['avg_iv'] < 100) &
        (straddle['datetime'].notna())
    ].sort_values('datetime').reset_index(drop=True)
    
    print(f"Final: {len(straddle)} straddle pairs")
    print(f"Period: {straddle['datetime'].min()} to {straddle['datetime'].max()}")
    
    straddle.to_csv('straddle_data_prepared.csv', index=False)
    print("✅ Saved: straddle_data_prepared.csv")
    return True


def costs(entry, exit):
    """Transaction costs"""
    return 50  # Simplified: ₹50 per round trip


def greeks(spot, iv):
    """Calculate gamma"""
    sigma = iv / 100
    T = 7/365
    if T <= 0 or sigma <= 0:
        return 0
    return 0.8 / (spot * sigma * np.sqrt(T))


def compute_iv_scalping():
    """Step 2: IV Scalping"""
    
    print("\n" + "="*70)
    print("STEP 2: IV SCALPING")
    print("="*70)
    
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # OPTIMIZED PARAMETERS
    LOOKBACK = 100
    IV_ENTRY = 30  # 30th percentile
    PROFIT = 20.0  # 20% profit target
    STOP = 15.0    # 15% stop loss
    HOLD = 225     # 3 days (75 periods/day × 3)
    
    print(f"Entry: IV ≤ {IV_ENTRY}th percentile")
    print(f"Exit: +{PROFIT}% profit OR -{STOP}% stop OR {HOLD//75} days")
    
    df['iv_pct'] = df['avg_iv'].rolling(LOOKBACK).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    
    trades = []
    i = LOOKBACK
    
    while i < len(df) - HOLD:
        if df.iloc[i]['iv_pct'] <= IV_ENTRY:
            entry_cost = df.iloc[i]['straddle_cost']
            entry_time = df.iloc[i]['datetime']
            
            exit_idx = min(i + HOLD, len(df) - 1)
            exit_reason = "TIME"
            
            for j in range(i + 1, exit_idx + 1):
                pnl_pct = ((df.iloc[j]['straddle_cost'] - entry_cost) / entry_cost) * 100
                
                if pnl_pct >= PROFIT:
                    exit_idx = j
                    exit_reason = "PROFIT"
                    break
                elif pnl_pct <= -STOP:
                    exit_idx = j
                    exit_reason = "STOP"
                    break
            
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            raw_pnl = exit_cost - entry_cost
            transaction_costs = costs(entry_cost, exit_cost)
            net_pnl = raw_pnl - transaction_costs
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': df.iloc[exit_idx]['datetime'],
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'net_pnl': round(net_pnl, 2),
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason
            })
            
            i = exit_idx + 6  # 30 min gap
        else:
            i += 1
    
    if len(trades) == 0:
        print("⚠️ No trades!")
        return
    
    trades_df = pd.DataFrame(trades)
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    total_pnl = trades_df['net_pnl'].sum()
    
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins/total)*100, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'profit_factor': 0,
        'sharpe_ratio': 0
    }
    
    pd.DataFrame([perf]).to_csv('iv_performance.csv', index=False)
    trades_df.to_csv('iv_trades.csv', index=False)
    
    print(f"✅ Trades: {total} | Win Rate: {perf['win_rate']}% | P&L: ₹{total_pnl:,.2f}")


def compute_gamma_scalping():
    """Step 3: Gamma Scalping"""
    
    print("\n" + "="*70)
    print("STEP 3: GAMMA SCALPING")
    print("="*70)
    
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    GAMMA_MIN = 0.01
    PROFIT = 25.0
    STOP = 15.0
    HOLD = 225
    
    print(f"Entry: Gamma ≥ {GAMMA_MIN}")
    print(f"Exit: +{PROFIT}% profit OR -{STOP}% stop OR 3 days")
    
    trades = []
    i = 100
    
    while i < len(df) - HOLD:
        row = df.iloc[i]
        gamma = greeks(row['spot'], row['avg_iv'])
        
        if gamma >= GAMMA_MIN:
            entry_cost = row['straddle_cost']
            entry_time = row['datetime']
            
            # Simulate hedging
            hedge_pnl = 0
            last_spot = row['spot']
            hedge_count = 0
            
            exit_idx = min(i + HOLD, len(df) - 1)
            exit_reason = "TIME"
            
            for j in range(i + 1, exit_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                current_spot = df.iloc[j]['spot']
                
                # Hedge on 0.5% move
                if abs(current_spot - last_spot) > (last_spot * 0.005):
                    hedge_pnl += abs(current_spot - last_spot) * gamma * row['spot'] * 0.2
                    last_spot = current_spot
                    hedge_count += 1
                
                total_pnl = (current_cost - entry_cost) + hedge_pnl
                total_pct = (total_pnl / entry_cost) * 100
                
                if total_pct >= PROFIT:
                    exit_idx = j
                    exit_reason = "PROFIT"
                    break
                elif total_pct <= -STOP:
                    exit_idx = j
                    exit_reason = "STOP"
                    break
            
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            raw_pnl = (exit_cost - entry_cost) + hedge_pnl
            transaction_costs = costs(entry_cost, exit_cost) + (hedge_count * 5)
            net_pnl = raw_pnl - transaction_costs
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': df.iloc[exit_idx]['datetime'],
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'net_pnl': round(net_pnl, 2),
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason
            })
            
            i = exit_idx + 6
        else:
            i += 1
    
    if len(trades) == 0:
        print("⚠️ No trades!")
        return
    
    trades_df = pd.DataFrame(trades)
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    total_pnl = trades_df['net_pnl'].sum()
    
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins/total)*100, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'profit_factor': 0,
        'sharpe_ratio': 0
    }
    
    pd.DataFrame([perf]).to_csv('gamma_performance.csv', index=False)
    trades_df.to_csv('gamma_trades.csv', index=False)
    
    print(f"✅ Trades: {total} | Win Rate: {perf['win_rate']}% | P&L: ₹{total_pnl:,.2f}")


def compute_hybrid():
    """Step 4: Hybrid (Both conditions)"""
    
    print("\n" + "="*70)
    print("STEP 4: HYBRID")
    print("="*70)
    
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    LOOKBACK = 100
    IV_ENTRY = 30
    GAMMA_MIN = 0.01
    PROFIT = 25.0
    STOP = 15.0
    HOLD = 225
    
    print("Entry: IV ≤ 30th percentile AND Gamma ≥ 0.01")
    
    df['iv_pct'] = df['avg_iv'].rolling(LOOKBACK).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    
    trades = []
    i = LOOKBACK
    
    while i < len(df) - HOLD:
        row = df.iloc[i]
        gamma = greeks(row['spot'], row['avg_iv'])
        
        # BOTH conditions
        if row['iv_pct'] <= IV_ENTRY and gamma >= GAMMA_MIN:
            entry_cost = row['straddle_cost']
            entry_time = row['datetime']
            
            hedge_pnl = 0
            last_spot = row['spot']
            hedge_count = 0
            
            exit_idx = min(i + HOLD, len(df) - 1)
            exit_reason = "TIME"
            
            for j in range(i + 1, exit_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                current_spot = df.iloc[j]['spot']
                
                if abs(current_spot - last_spot) > (last_spot * 0.005):
                    hedge_pnl += abs(current_spot - last_spot) * gamma * row['spot'] * 0.2
                    last_spot = current_spot
                    hedge_count += 1
                
                total_pnl = (current_cost - entry_cost) + hedge_pnl
                total_pct = (total_pnl / entry_cost) * 100
                
                if total_pct >= PROFIT:
                    exit_idx = j
                    exit_reason = "PROFIT"
                    break
                elif total_pct <= -STOP:
                    exit_idx = j
                    exit_reason = "STOP"
                    break
            
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            raw_pnl = (exit_cost - entry_cost) + hedge_pnl
            transaction_costs = costs(entry_cost, exit_cost) + (hedge_count * 5)
            net_pnl = raw_pnl - transaction_costs
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': df.iloc[exit_idx]['datetime'],
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'net_pnl': round(net_pnl, 2),
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason
            })
            
            i = exit_idx + 6
        else:
            i += 1
    
    if len(trades) == 0:
        print("⚠️ No trades (too selective)")
        # Create empty files
        perf = {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'total_pnl': 0, 'avg_pnl': 0, 'profit_factor': 0, 'sharpe_ratio': 0}
        pd.DataFrame([perf]).to_csv('hybrid_performance.csv', index=False)
        pd.DataFrame().to_csv('hybrid_trades.csv', index=False)
        return
    
    trades_df = pd.DataFrame(trades)
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    total_pnl = trades_df['net_pnl'].sum()
    
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins/total)*100, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'profit_factor': 0,
        'sharpe_ratio': 0
    }
    
    pd.DataFrame([perf]).to_csv('hybrid_performance.csv', index=False)
    trades_df.to_csv('hybrid_trades.csv', index=False)
    
    print(f"✅ Trades: {total} | Win Rate: {perf['win_rate']}% | P&L: ₹{total_pnl:,.2f}")


if __name__ == "__main__":
    
    print("="*70)
    print("3-STRATEGY SYSTEM SETUP")
    print("="*70)
    
    if not prepare_data():
        sys.exit(1)
    
    compute_iv_scalping()
    compute_gamma_scalping()
    compute_hybrid()
    
    print("\n" + "="*70)
    print("✅ ALL DONE!")
    print("="*70)
    print("\nFiles created:")
    print("  - straddle_data_prepared.csv")
    print("  - iv_performance.csv, iv_trades.csv")
    print("  - gamma_performance.csv, gamma_trades.csv")
    print("  - hybrid_performance.csv, hybrid_trades.csv")
    print("\nNext: Run backend → python simple_backend.py")
