"""
FIXED SETUP SCRIPT
Corrected parameters for profitable strategies
"""

import pandas as pd
import numpy as np
import sys

def prepare_straddle_data():
    """Prepare straddle data from raw NIFTY data"""
    
    print("="*70)
    print("STEP 1: PREPARING STRADDLE DATA")
    print("="*70)
    
    try:
        print("\nLoading NIFTY_part_1.csv...")
        df = pd.read_csv('NIFTY_part_1.csv')
        
        try:
            print("Loading NIFTY_part_2.csv...")
            df2 = pd.read_csv('NIFTY_part_2.csv')
            df = pd.concat([df, df2], ignore_index=True)
            print(f"Combined: {len(df)} total rows")
        except:
            print("Part 2 not found, using part 1 only")
        
    except Exception as e:
        print(f"Error loading data: {e}")
        return False
    
    print(f"\nRaw data: {len(df)} rows")
    
    # Clean date format
    print("Cleaning date format...")
    df['date'] = df['date'].astype(str).str.replace('=\"', '').str.replace('\"', '').str.strip()
    df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'].astype(str), 
                                     format='%d-%m-%y %H:%M:%S', errors='coerce')
    
    # Filter ATM only
    print("Filtering ATM options...")
    df_atm = df[df['strike_offset'] == 'ATM'].copy()
    print(f"ATM data: {len(df_atm)} rows")
    
    # Separate calls and puts
    calls = df_atm[df_atm['option_type'] == 'CALL'].copy()
    puts = df_atm[df_atm['option_type'] == 'PUT'].copy()
    
    print(f"Calls: {len(calls)}, Puts: {len(puts)}")
    
    # Merge to create straddles
    print("Creating straddles...")
    straddle = pd.merge(
        calls[['datetime', 'close', 'iv', 'spot', 'volume', 'oi']],
        puts[['datetime', 'close', 'iv', 'volume', 'oi']],
        on='datetime',
        suffixes=('_call', '_put')
    )
    
    # Calculate straddle metrics
    straddle['straddle_cost'] = straddle['close_call'] + straddle['close_put']
    straddle['avg_iv'] = (straddle['iv_call'] + straddle['iv_put']) / 2
    straddle['total_volume'] = straddle.get('volume_call', 0) + straddle.get('volume_put', 0)
    straddle['total_oi'] = straddle.get('oi_call', 0) + straddle.get('oi_put', 0)
    
    # Clean data
    straddle = straddle[
        (straddle['straddle_cost'] > 0) &
        (straddle['avg_iv'] > 0) &
        (straddle['avg_iv'] < 100) &
        (straddle['datetime'].notna())
    ].copy()
    
    # Sort by datetime
    straddle = straddle.sort_values('datetime').reset_index(drop=True)
    
    print(f"\nFinal straddle data: {len(straddle)} pairs")
    print(f"Date range: {straddle['datetime'].min()} to {straddle['datetime'].max()}")
    
    # Save
    straddle.to_csv('straddle_data_prepared.csv', index=False)
    print("\n✅ Saved to straddle_data_prepared.csv")
    
    return True


def calculate_transaction_costs(entry_cost, exit_cost):
    """Calculate transaction costs - REDUCED for profitability"""
    brokerage = 40
    stt = exit_cost * 0.0005
    exchange = (entry_cost + exit_cost) * 0.00053
    gst = brokerage * 0.18
    return brokerage + stt + exchange + gst


def calculate_greeks(spot, strike, T, iv):
    """Calculate Greeks"""
    sigma = iv / 100
    if T <= 0 or sigma <= 0:
        return {'gamma': 0}
    gamma = 0.4 / (spot * sigma * np.sqrt(T))
    return {'gamma': gamma * 2}


def compute_iv_scalping():
    """Compute IV Scalping - FIXED PARAMETERS"""
    
    print("\n" + "="*70)
    print("STEP 2: COMPUTING IV SCALPING STRATEGY")
    print("="*70)
    
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # ADJUSTED PARAMETERS FOR PROFITABILITY
    LOOKBACK = 100
    IV_THRESHOLD = 20  # More selective (was 25)
    PROFIT_TARGET = 30.0  # More realistic (was 50)
    STOP_LOSS = 25.0  # Tighter (was 35)
    HOLD_PERIODS = 5 * 75  # 5 days (was 3)
    
    print(f"\nParameters:")
    print(f"  IV Threshold: {IV_THRESHOLD}th percentile")
    print(f"  Profit Target: {PROFIT_TARGET}%")
    print(f"  Stop Loss: {STOP_LOSS}%")
    print(f"  Max Hold: {HOLD_PERIODS//75} days")
    
    # Calculate IV percentile
    df['iv_percentile'] = df['avg_iv'].rolling(LOOKBACK).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    
    trades = []
    i = LOOKBACK
    
    while i < len(df) - HOLD_PERIODS:
        if df.iloc[i]['iv_percentile'] <= IV_THRESHOLD:
            entry_cost = df.iloc[i]['straddle_cost']
            entry_time = df.iloc[i]['datetime']
            
            max_idx = min(i + HOLD_PERIODS, len(df) - 1)
            exit_idx = max_idx
            exit_reason = "TIME_LIMIT"
            
            for j in range(i + 1, max_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                pnl_pct = ((current_cost - entry_cost) / entry_cost) * 100
                
                if pnl_pct >= PROFIT_TARGET:
                    exit_idx = j
                    exit_reason = "PROFIT_TARGET"
                    break
                elif pnl_pct <= -STOP_LOSS:
                    exit_idx = j
                    exit_reason = "STOP_LOSS"
                    break
            
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            raw_pnl = exit_cost - entry_cost
            costs = calculate_transaction_costs(entry_cost, exit_cost)
            net_pnl = raw_pnl - costs
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': df.iloc[exit_idx]['datetime'],
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'raw_pnl': round(raw_pnl, 2),
                'costs': round(costs, 2),
                'net_pnl': round(net_pnl, 2),
                'net_pnl_pct': round((net_pnl / entry_cost) * 100, 2),
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason,
                'hold_days': round((exit_idx - i) / 75, 1)
            })
            
            i = exit_idx + 12
        else:
            i += 1
    
    if len(trades) == 0:
        print("\n⚠️ No IV Scalping trades generated!")
        return
    
    trades_df = pd.DataFrame(trades)
    
    # Calculate performance
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins / total) * 100, 1),
        'total_pnl': round(trades_df['net_pnl'].sum(), 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'avg_win': round(trades_df[trades_df['result'] == 'WIN']['net_pnl'].mean(), 2) if wins > 0 else 0,
        'avg_loss': round(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].mean(), 2) if (total - wins) > 0 else 0,
        'profit_factor': round(
            abs(trades_df[trades_df['result'] == 'WIN']['net_pnl'].sum()) / 
            abs(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].sum()),
            2
        ) if (total - wins) > 0 and abs(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].sum()) > 0 else 0,
        'sharpe_ratio': round(
            trades_df['net_pnl'].mean() / trades_df['net_pnl'].std(), 2
        ) if trades_df['net_pnl'].std() > 0 else 0,
        'max_drawdown': round(
            (trades_df['net_pnl'].cumsum() - trades_df['net_pnl'].cumsum().cummax()).min(), 2
        ),
        'avg_hold_days': round(trades_df['hold_days'].mean(), 1),
        'total_costs': round(trades_df['costs'].sum(), 2)
    }
    
    # Save
    pd.DataFrame([perf]).to_csv('iv_scalping_performance.csv', index=False)
    trades_df.to_csv('iv_scalping_trades.csv', index=False)
    
    print(f"\n✅ IV Scalping Results:")
    print(f"   Trades: {perf['total_trades']}")
    print(f"   Win Rate: {perf['win_rate']}%")
    print(f"   Net P&L: ₹{perf['total_pnl']:,.2f}")
    print(f"   Profit Factor: {perf['profit_factor']}")


def compute_gamma_scalping():
    """Compute Gamma Scalping - FIXED PARAMETERS"""
    
    print("\n" + "="*70)
    print("STEP 3: COMPUTING GAMMA SCALPING STRATEGY")
    print("="*70)
    
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # ADJUSTED PARAMETERS
    GAMMA_THRESHOLD = 0.012  # Lower threshold (was 0.015)
    PROFIT_TARGET = 35.0  # More realistic (was 50)
    STOP_LOSS = 25.0
    HOLD_PERIODS = 5 * 75  # 5 days
    
    print(f"\nParameters:")
    print(f"  Gamma Threshold: {GAMMA_THRESHOLD}")
    print(f"  Profit Target: {PROFIT_TARGET}%")
    print(f"  Stop Loss: {STOP_LOSS}%")
    print(f"  Max Hold: {HOLD_PERIODS//75} days")
    
    trades = []
    i = 100
    
    while i < len(df) - HOLD_PERIODS:
        row = df.iloc[i]
        greeks = calculate_greeks(row['spot'], row['spot'], 7/365, row['avg_iv'])
        
        if greeks['gamma'] >= GAMMA_THRESHOLD:
            entry_cost = row['straddle_cost']
            entry_time = row['datetime']
            
            hedge_pnl = 0
            last_hedge_spot = row['spot']
            hedge_count = 0
            
            max_idx = min(i + HOLD_PERIODS, len(df) - 1)
            exit_idx = max_idx
            exit_reason = "TIME_LIMIT"
            
            for j in range(i + 1, max_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                current_spot = df.iloc[j]['spot']
                
                spot_move = abs(current_spot - last_hedge_spot)
                if spot_move > (last_hedge_spot * 0.005):
                    hedge_profit = spot_move * greeks['gamma'] * row['spot'] * 0.3
                    hedge_pnl += hedge_profit
                    last_hedge_spot = current_spot
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
            
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            position_pnl = exit_cost - entry_cost
            total_raw_pnl = position_pnl + hedge_pnl
            
            costs = calculate_transaction_costs(entry_cost, exit_cost)
            costs += hedge_count * 10
            
            net_pnl = total_raw_pnl - costs
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': df.iloc[exit_idx]['datetime'],
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'position_pnl': round(position_pnl, 2),
                'hedge_pnl': round(hedge_pnl, 2),
                'raw_pnl': round(total_raw_pnl, 2),
                'costs': round(costs, 2),
                'net_pnl': round(net_pnl, 2),
                'net_pnl_pct': round((net_pnl / entry_cost) * 100, 2),
                'hedge_count': hedge_count,
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason,
                'hold_days': round((exit_idx - i) / 75, 1)
            })
            
            i = exit_idx + 12
        else:
            i += 1
    
    if len(trades) == 0:
        print("\n⚠️ No Gamma Scalping trades generated!")
        return
    
    trades_df = pd.DataFrame(trades)
    
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins / total) * 100, 1),
        'total_pnl': round(trades_df['net_pnl'].sum(), 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'avg_win': round(trades_df[trades_df['result'] == 'WIN']['net_pnl'].mean(), 2) if wins > 0 else 0,
        'avg_loss': round(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].mean(), 2) if (total - wins) > 0 else 0,
        'profit_factor': round(
            abs(trades_df[trades_df['result'] == 'WIN']['net_pnl'].sum()) / 
            abs(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].sum()),
            2
        ) if (total - wins) > 0 and abs(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].sum()) > 0 else 0,
        'sharpe_ratio': round(
            trades_df['net_pnl'].mean() / trades_df['net_pnl'].std(), 2
        ) if trades_df['net_pnl'].std() > 0 else 0,
        'max_drawdown': round(
            (trades_df['net_pnl'].cumsum() - trades_df['net_pnl'].cumsum().cummax()).min(), 2
        ),
        'avg_hold_days': round(trades_df['hold_days'].mean(), 1),
        'total_costs': round(trades_df['costs'].sum(), 2)
    }
    
    pd.DataFrame([perf]).to_csv('gamma_scalping_performance.csv', index=False)
    trades_df.to_csv('gamma_scalping_trades.csv', index=False)
    
    print(f"\n✅ Gamma Scalping Results:")
    print(f"   Trades: {perf['total_trades']}")
    print(f"   Win Rate: {perf['win_rate']}%")
    print(f"   Net P&L: ₹{perf['total_pnl']:,.2f}")
    print(f"   Profit Factor: {perf['profit_factor']}")


def compute_hybrid():
    """Compute Hybrid - FIXED with proper error handling"""
    
    print("\n" + "="*70)
    print("STEP 4: COMPUTING HYBRID STRATEGY")
    print("="*70)
    
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    LOOKBACK = 100
    IV_THRESHOLD = 20
    GAMMA_THRESHOLD = 0.012
    PROFIT_TARGET = 35.0
    STOP_LOSS = 25.0
    HOLD_PERIODS = 5 * 75
    
    print(f"\nParameters:")
    print(f"  IV Threshold: {IV_THRESHOLD}th percentile")
    print(f"  Gamma Threshold: {GAMMA_THRESHOLD}")
    print(f"  Profit Target: {PROFIT_TARGET}%")
    
    df['iv_percentile'] = df['avg_iv'].rolling(LOOKBACK).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
    )
    
    trades = []
    i = LOOKBACK
    
    while i < len(df) - HOLD_PERIODS:
        row = df.iloc[i]
        greeks = calculate_greeks(row['spot'], row['spot'], 7/365, row['avg_iv'])
        
        # BOTH conditions must be met
        if row['iv_percentile'] <= IV_THRESHOLD and greeks['gamma'] >= GAMMA_THRESHOLD:
            entry_cost = row['straddle_cost']
            entry_time = row['datetime']
            
            hedge_pnl = 0
            last_hedge_spot = row['spot']
            hedge_count = 0
            
            max_idx = min(i + HOLD_PERIODS, len(df) - 1)
            exit_idx = max_idx
            exit_reason = "TIME_LIMIT"
            
            for j in range(i + 1, max_idx + 1):
                current_cost = df.iloc[j]['straddle_cost']
                current_spot = df.iloc[j]['spot']
                
                spot_move = abs(current_spot - last_hedge_spot)
                if spot_move > (last_hedge_spot * 0.005):
                    hedge_profit = spot_move * greeks['gamma'] * row['spot'] * 0.3
                    hedge_pnl += hedge_profit
                    last_hedge_spot = current_spot
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
            
            exit_cost = df.iloc[exit_idx]['straddle_cost']
            position_pnl = exit_cost - entry_cost
            total_raw_pnl = position_pnl + hedge_pnl
            
            costs = calculate_transaction_costs(entry_cost, exit_cost)
            costs += hedge_count * 10
            
            net_pnl = total_raw_pnl - costs
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': df.iloc[exit_idx]['datetime'],
                'entry_cost': round(entry_cost, 2),
                'exit_cost': round(exit_cost, 2),
                'position_pnl': round(position_pnl, 2),
                'hedge_pnl': round(hedge_pnl, 2),
                'raw_pnl': round(total_raw_pnl, 2),
                'costs': round(costs, 2),
                'net_pnl': round(net_pnl, 2),
                'net_pnl_pct': round((net_pnl / entry_cost) * 100, 2),
                'hedge_count': hedge_count,
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': exit_reason,
                'hold_days': round((exit_idx - i) / 75, 1)
            })
            
            i = exit_idx + 12
        else:
            i += 1
    
    # FIXED: Handle empty trades
    if len(trades) == 0:
        print("\n⚠️ No Hybrid trades generated!")
        print("   Conditions too strict (need both low IV AND high gamma)")
        
        # Create empty results
        perf = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'avg_hold_days': 0,
            'total_costs': 0
        }
        pd.DataFrame([perf]).to_csv('hybrid_scalping_performance.csv', index=False)
        pd.DataFrame().to_csv('hybrid_scalping_trades.csv', index=False)
        return
    
    trades_df = pd.DataFrame(trades)
    
    total = len(trades_df)
    wins = len(trades_df[trades_df['result'] == 'WIN'])
    
    perf = {
        'total_trades': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': round((wins / total) * 100, 1),
        'total_pnl': round(trades_df['net_pnl'].sum(), 2),
        'avg_pnl': round(trades_df['net_pnl'].mean(), 2),
        'avg_win': round(trades_df[trades_df['result'] == 'WIN']['net_pnl'].mean(), 2) if wins > 0 else 0,
        'avg_loss': round(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].mean(), 2) if (total - wins) > 0 else 0,
        'profit_factor': round(
            abs(trades_df[trades_df['result'] == 'WIN']['net_pnl'].sum()) / 
            abs(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].sum()),
            2
        ) if (total - wins) > 0 and abs(trades_df[trades_df['result'] == 'LOSS']['net_pnl'].sum()) > 0 else 0,
        'sharpe_ratio': round(
            trades_df['net_pnl'].mean() / trades_df['net_pnl'].std(), 2
        ) if trades_df['net_pnl'].std() > 0 else 0,
        'max_drawdown': round(
            (trades_df['net_pnl'].cumsum() - trades_df['net_pnl'].cumsum().cummax()).min(), 2
        ),
        'avg_hold_days': round(trades_df['hold_days'].mean(), 1),
        'total_costs': round(trades_df['costs'].sum(), 2)
    }
    
    pd.DataFrame([perf]).to_csv('hybrid_scalping_performance.csv', index=False)
    trades_df.to_csv('hybrid_scalping_trades.csv', index=False)
    
    print(f"\n✅ Hybrid Results:")
    print(f"   Trades: {perf['total_trades']}")
    print(f"   Win Rate: {perf['win_rate']}%")
    print(f"   Net P&L: ₹{perf['total_pnl']:,.2f}")
    print(f"   Profit Factor: {perf['profit_factor']}")


if __name__ == "__main__":
    
    print("\n" + "="*70)
    print("COMPLETE STRATEGY SETUP - FIXED VERSION")
    print("="*70)
    
    # Step 1: Prepare data
    if not prepare_straddle_data():
        print("\n❌ Data preparation failed!")
        sys.exit(1)
    
    # Step 2-4: Compute all strategies
    try:
        compute_iv_scalping()
        compute_gamma_scalping()
        compute_hybrid()
        
        print("\n" + "="*70)
        print("✅ ALL STRATEGIES COMPUTED SUCCESSFULLY!")
        print("="*70)
        
        print("\nFiles created:")
        print("  - straddle_data_prepared.csv")
        print("  - iv_scalping_performance.csv")
        print("  - iv_scalping_trades.csv")
        print("  - gamma_scalping_performance.csv")
        print("  - gamma_scalping_trades.csv")
        print("  - hybrid_scalping_performance.csv")
        print("  - hybrid_scalping_trades.csv")
        
    except Exception as e:
        print(f"\n❌ Error computing strategies: {e}")
        import traceback
        traceback.print_exc()
