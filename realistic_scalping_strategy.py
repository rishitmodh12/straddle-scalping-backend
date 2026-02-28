"""
REALISTIC INTRADAY SCALPING STRATEGY
Proper entry filters to avoid overtrading
Transaction costs optimized
"""

import pandas as pd
import numpy as np
from datetime import datetime, time


class RealisticScalpingStrategy:
    """
    REALISTIC SCALPING:
    1. Selective entries (not every 5 minutes!)
    2. Cooldown period after each trade
    3. Reasonable profit/loss targets considering costs
    4. Volatility confirmation before entry
    """
    
    def __init__(self):
        # Entry filters
        self.iv_threshold = 25  # Bottom 25% (more selective)
        self.min_cooldown_periods = 12  # 60 minutes between trades
        
        # Position management
        self.profit_target_pct = 0.25  # 25% to cover costs (₹50 on ₹200 = 25%)
        self.stop_loss_pct = 0.20      # 20% stop loss
        self.max_hold_periods = 36     # 3 hours max (180 min / 5)
        
        # Transaction costs (realistic for retail)
        self.brokerage_flat = 20  # ₹20 flat per executed order (Zerodha)
        # Total per straddle: Entry (₹20) + Exit (₹20) + taxes ~₹50
        
    def calculate_transaction_costs(self, entry_cost, exit_cost):
        """Calculate realistic transaction costs"""
        
        # Entry: 2 orders (Call + Put) = ₹20 each = ₹40
        # But many brokers charge per executed order, not per leg
        # Zerodha: ₹20 flat per order
        entry_brokerage = 20  # Per order (Call or Put)
        
        # Exit: Same
        exit_brokerage = 20
        
        # STT on sell side (options)
        stt = exit_cost * 0.0005  # 0.05%
        
        # Exchange charges
        exchange_charges = (entry_cost + exit_cost) * 0.00053
        
        # GST on brokerage
        total_brokerage = entry_brokerage + exit_brokerage
        gst = total_brokerage * 0.18
        
        total_costs = total_brokerage + stt + exchange_charges + gst
        
        return {
            'total': total_costs,
            'brokerage': total_brokerage,
            'gst': gst,
            'stt': stt,
            'exchange': exchange_charges
        }
    
    def check_volatility_expansion_setup(self, df, index):
        """
        Additional filter: Check if volatility is actually contracting
        (Setup for expansion)
        """
        if index < 20:
            return False
        
        recent = df.iloc[index-20:index]
        
        # Check if IV is stable/contracting (Bollinger Band squeeze)
        iv_std = recent['avg_iv'].std()
        iv_mean = recent['avg_iv'].mean()
        
        # Relative std should be low (squeeze)
        relative_std = iv_std / iv_mean
        
        # Also check if spot price range is contracting
        spot_range = recent['spot'].max() - recent['spot'].min()
        spot_range_pct = (spot_range / recent['spot'].mean()) * 100
        
        # Entry criteria:
        # 1. IV variation is low (squeeze)
        # 2. Price range is moderate (not dead flat, not wild)
        
        return relative_std < 0.08 and 0.3 < spot_range_pct < 2.0
    
    def generate_signals(self, df):
        """Generate REALISTIC intraday signals"""
        
        LOOKBACK = 100
        
        df['date'] = df['datetime'].dt.date
        df['time'] = df['datetime'].dt.time
        
        # Calculate IV percentile
        df['iv_percentile_value'] = df['avg_iv'].rolling(window=LOOKBACK).apply(
            lambda x: (x <= x.iloc[-1]).sum() / len(x) * 100 if len(x) > 0 else 50
        )
        
        trades = []
        position = None
        last_exit_index = -1000  # Track last exit for cooldown
        
        for i in range(LOOKBACK, len(df)):
            current_row = df.iloc[i]
            current_time = current_row['datetime']
            current_date = current_row['date']
            current_cost = current_row['straddle_cost']
            iv_pct_value = current_row['iv_percentile_value']
            
            # Market hours check (9:15 AM - 3:15 PM)
            if not (time(9, 15) <= current_time.time() <= time(15, 15)):
                continue
            
            if position is not None:
                # In position - check exits
                
                # Force exit if different day
                if current_date != position['entry_date']:
                    position = None
                    continue
                
                entry_cost = position['entry_cost']
                entry_index = position['entry_index']
                
                # Calculate P&L
                raw_pnl = current_cost - entry_cost
                raw_pnl_pct = (raw_pnl / entry_cost) * 100
                
                # Calculate costs
                costs = self.calculate_transaction_costs(entry_cost, current_cost)
                net_pnl = raw_pnl - costs['total']
                net_pnl_pct = (net_pnl / entry_cost) * 100
                
                periods_held = i - entry_index
                
                # Exit conditions
                exit = False
                reason = None
                
                # 1. Profit target (after costs!)
                if net_pnl_pct >= (self.profit_target_pct * 100):
                    exit = True
                    reason = "PROFIT_TARGET"
                
                # 2. Stop loss
                elif net_pnl_pct <= -(self.stop_loss_pct * 100):
                    exit = True
                    reason = "STOP_LOSS"
                
                # 3. End of day
                elif current_time.time() >= time(15, 15):
                    exit = True
                    reason = "END_OF_DAY"
                
                # 4. Max hold time
                elif periods_held >= self.max_hold_periods:
                    exit = True
                    reason = "TIME_LIMIT"
                
                if exit:
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': current_time,
                        'entry_cost': entry_cost,
                        'exit_cost': current_cost,
                        'raw_pnl': raw_pnl,
                        'costs': costs['total'],
                        'net_pnl': net_pnl,
                        'net_pnl_pct': net_pnl_pct,
                        'result': 'WIN' if net_pnl > 0 else 'LOSS',
                        'exit_reason': reason,
                        'hold_minutes': periods_held * 5
                    })
                    position = None
                    last_exit_index = i
            
            else:
                # No position - check entry
                
                # Don't enter too late in day
                if current_time.time() > time(14, 0):
                    continue
                
                # Cooldown period (avoid immediate re-entry)
                if i - last_exit_index < self.min_cooldown_periods:
                    continue
                
                # Entry conditions:
                # 1. IV in bottom 25%
                if iv_pct_value > self.iv_threshold:
                    continue
                
                # 2. Volatility setup (squeeze)
                if not self.check_volatility_expansion_setup(df, i):
                    continue
                
                # 3. Straddle cost reasonable (₹150-400 range)
                if not (150 <= current_cost <= 400):
                    continue
                
                # ALL CONDITIONS MET → ENTER
                position = {
                    'entry_index': i,
                    'entry_time': current_time,
                    'entry_date': current_date,
                    'entry_cost': current_cost
                }
        
        return pd.DataFrame(trades)
    
    def calculate_performance(self, trades_df):
        """Calculate performance metrics"""
        
        if len(trades_df) == 0:
            return None
        
        total = len(trades_df)
        wins = len(trades_df[trades_df['result'] == 'WIN'])
        losses = total - wins
        win_rate = (wins / total) * 100
        
        total_net_pnl = trades_df['net_pnl'].sum()
        total_raw_pnl = trades_df['raw_pnl'].sum()
        total_costs = trades_df['costs'].sum()
        
        avg_net_pnl = trades_df['net_pnl'].mean()
        
        winners = trades_df[trades_df['result'] == 'WIN']
        losers = trades_df[trades_df['result'] == 'LOSS']
        
        avg_win = winners['net_pnl'].mean() if len(winners) > 0 else 0
        avg_loss = losers['net_pnl'].mean() if len(losers) > 0 else 0
        
        total_wins_amt = winners['net_pnl'].sum() if len(winners) > 0 else 0
        total_loss_amt = abs(losers['net_pnl'].sum()) if len(losers) > 0 else 0
        
        profit_factor = total_wins_amt / total_loss_amt if total_loss_amt > 0 else 0
        sharpe = (avg_net_pnl / trades_df['net_pnl'].std()) if trades_df['net_pnl'].std() > 0 else 0
        
        return {
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 1),
            'total_net_pnl': round(total_net_pnl, 2),
            'total_raw_pnl': round(total_raw_pnl, 2),
            'total_costs': round(total_costs, 2),
            'avg_net_pnl': round(avg_net_pnl, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'sharpe_ratio': round(sharpe, 2),
            'avg_hold': round(trades_df['hold_minutes'].mean(), 1),
            'trades_per_day': round(total / 250, 1)  # ~250 trading days
        }


if __name__ == "__main__":
    
    print("="*70)
    print("REALISTIC INTRADAY SCALPING STRATEGY")
    print("Selective Entry | Proper Filters | Transaction Costs Included")
    print("="*70)
    
    # Load data
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    print(f"\nData: {len(df)} rows")
    
    # Run strategy
    strategy = RealisticScalpingStrategy()
    
    print("\nRunning realistic backtest...")
    print("Entry filters:")
    print("  ✓ IV ≤ 25th percentile")
    print("  ✓ Volatility squeeze detected")
    print("  ✓ 60-min cooldown between trades")
    print("  ✓ Straddle cost ₹150-400")
    print()
    
    trades_df = strategy.generate_signals(df)
    
    if len(trades_df) > 0:
        trades_df.to_csv('realistic_scalping_results.csv', index=False)
        
        perf = strategy.calculate_performance(trades_df)
        
        print("="*70)
        print("RESULTS")
        print("="*70)
        
        print(f"\nTotal Trades:        {perf['total_trades']}")
        print(f"Trades per Day:      {perf['trades_per_day']}")
        print(f"Win Rate:            {perf['win_rate']}%")
        print(f"Avg Hold Time:       {perf['avg_hold']} minutes")
        
        print(f"\nBEFORE COSTS:")
        print(f"  Raw P&L:           ₹{perf['total_raw_pnl']:,.2f}")
        
        print(f"\nCOSTS:")
        print(f"  Total Costs:       ₹{perf['total_costs']:,.2f}")
        print(f"  Cost per Trade:    ₹{perf['total_costs']/perf['total_trades']:.2f}")
        
        print(f"\nAFTER COSTS (REAL):")
        print(f"  Net P&L:           ₹{perf['total_net_pnl']:,.2f}")
        print(f"  Avg P&L/Trade:     ₹{perf['avg_net_pnl']:.2f}")
        print(f"  Avg Win:           ₹{perf['avg_win']:.2f}")
        print(f"  Avg Loss:          ₹{perf['avg_loss']:.2f}")
        
        print(f"\nRISK METRICS:")
        print(f"  Profit Factor:     {perf['profit_factor']}")
        print(f"  Sharpe Ratio:      {perf['sharpe_ratio']}")
        
        # Sample trades
        print("\n" + "="*70)
        print("SAMPLE TRADES")
        print("="*70)
        
        for idx in range(min(3, len(trades_df))):
            t = trades_df.iloc[idx]
            print(f"\nTrade #{idx+1}:")
            print(f"  Entry:  {t['entry_time']}")
            print(f"  Exit:   {t['exit_time']} ({t['exit_reason']})")
            print(f"  Hold:   {t['hold_minutes']} min")
            print(f"  Raw:    ₹{t['raw_pnl']:.2f}")
            print(f"  Costs:  ₹{t['costs']:.2f}")
            print(f"  Net:    ₹{t['net_pnl']:.2f} ({t['net_pnl_pct']:.1f}%)")
            print(f"  Result: {t['result']}")
        
        # Save performance
        perf_df = pd.DataFrame([perf])
        perf_df.to_csv('realistic_scalping_performance.csv', index=False)
        
        print("\n✅ Results saved!")
        
        # Final verdict
        print("\n" + "="*70)
        if perf['total_net_pnl'] > 0:
            print(f"✅ PROFITABLE: ₹{perf['total_net_pnl']:,.2f} net profit")
            print(f"   Average ₹{perf['avg_net_pnl']:.2f} per trade")
        else:
            print(f"❌ NOT PROFITABLE: ₹{perf['total_net_pnl']:,.2f} net loss")
            print("   Strategy needs further optimization")
        print("="*70)
        
    else:
        print("⚠️ No trades generated!")
        print("\nStrategy is TOO SELECTIVE. Try:")
        print("  - Increase IV threshold to 30-35")
        print("  - Remove volatility squeeze filter")
        print("  - Reduce cooldown period")
