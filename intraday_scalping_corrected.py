"""
CORRECTED INTRADAY SCALPING STRATEGY
True scalping: No overnight positions, full brokerage costs included
"""

import pandas as pd
import numpy as np
from datetime import datetime, time


class IntradayScalpingStrategy:
    """
    TRUE SCALPING RULES:
    1. Enter and Exit SAME DAY only
    2. All positions closed by 3:15 PM (15 mins before close)
    3. Include ALL transaction costs
    4. Hold time: 15 minutes to 3 hours maximum
    """
    
    def __init__(
        self,
        iv_threshold=30,
        profit_target=0.15,  # 15% (was 10%, need higher to cover costs)
        stop_loss=0.10,      # 10% (tighter for scalping)
        max_hold_minutes=180, # 3 hours max
        brokerage_per_leg=10  # ₹10 per leg (₹20 per straddle entry, ₹20 exit)
    ):
        self.iv_threshold = iv_threshold
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.max_hold_periods = max_hold_minutes // 5  # Convert to 5-min periods
        self.brokerage_per_leg = brokerage_per_leg
        
        # Transaction costs breakdown
        self.costs = {
            'brokerage_per_leg': brokerage_per_leg,
            'stt_rate': 0.0005,      # 0.05% on sell side
            'exchange_rate': 0.00053, # NSE charges
            'gst_rate': 0.18         # 18% on brokerage
        }
    
    def is_market_hours(self, dt):
        """Check if within market hours (9:15 AM - 3:15 PM)"""
        market_open = time(9, 15)
        market_close = time(15, 15)  # Close positions by 3:15 PM
        return market_open <= dt.time() <= market_close
    
    def calculate_transaction_costs(self, entry_cost, exit_cost):
        """
        Calculate ALL transaction costs for a straddle trade
        
        Entry: Buy Call + Buy Put
        Exit: Sell Call + Sell Put
        """
        
        # Entry costs
        entry_brokerage = self.brokerage_per_leg * 2  # 2 legs (Call + Put)
        entry_gst = entry_brokerage * self.costs['gst_rate']
        entry_exchange = entry_cost * self.costs['exchange_rate']
        
        total_entry_cost = entry_brokerage + entry_gst + entry_exchange
        
        # Exit costs
        exit_brokerage = self.brokerage_per_leg * 2  # 2 legs
        exit_gst = exit_brokerage * self.costs['gst_rate']
        exit_stt = exit_cost * self.costs['stt_rate']  # STT on sell
        exit_exchange = exit_cost * self.costs['exchange_rate']
        
        total_exit_cost = exit_brokerage + exit_gst + exit_stt + exit_exchange
        
        total_costs = total_entry_cost + total_exit_cost
        
        return {
            'total_costs': total_costs,
            'entry_costs': total_entry_cost,
            'exit_costs': total_exit_cost,
            'breakdown': {
                'brokerage': (entry_brokerage + exit_brokerage),
                'gst': (entry_gst + exit_gst),
                'stt': exit_stt,
                'exchange': (entry_exchange + exit_exchange)
            }
        }
    
    def generate_signals(self, df):
        """
        Generate INTRADAY ONLY signals
        """
        
        LOOKBACK = 100
        
        # Add date column
        df['date'] = df['datetime'].dt.date
        df['time'] = df['datetime'].dt.time
        
        # Calculate IV percentile
        df['iv_percentile'] = df['avg_iv'].rolling(window=LOOKBACK, min_periods=20).apply(
            lambda x: (x.iloc[-1] <= np.percentile(x, self.iv_threshold)) * 100 if len(x) > 0 else 0
        )
        
        trades = []
        position = None
        
        for i in range(len(df)):
            if i < LOOKBACK:
                continue
            
            current_row = df.iloc[i]
            current_time = current_row['datetime']
            current_date = current_row['date']
            current_iv_flag = current_row['iv_percentile']
            current_cost = current_row['straddle_cost']
            
            # Check if market hours
            if not self.is_market_hours(current_time):
                continue
            
            if position is not None:
                # In a position - check exits
                
                # CRITICAL: Force exit if different day
                if current_date != position['entry_date']:
                    # This should NEVER happen with proper filtering
                    # But fail-safe: close position
                    print(f"WARNING: Overnight position detected! Force closing.")
                    position = None
                    continue
                
                entry_cost = position['entry_cost']
                entry_index = position['entry_index']
                entry_date = position['entry_date']
                
                # Calculate raw P&L
                raw_pnl = current_cost - entry_cost
                raw_pnl_pct = (raw_pnl / entry_cost) * 100
                
                # Calculate transaction costs
                costs = self.calculate_transaction_costs(entry_cost, current_cost)
                total_costs = costs['total_costs']
                
                # Net P&L after costs
                net_pnl = raw_pnl - total_costs
                net_pnl_pct = (net_pnl / entry_cost) * 100
                
                # Check exit conditions
                exit = False
                reason = None
                
                periods_held = i - entry_index
                
                # Exit 1: Profit target (NET P&L)
                if net_pnl_pct >= (self.profit_target * 100):
                    exit = True
                    reason = "PROFIT_TARGET"
                
                # Exit 2: Stop loss (NET P&L)
                elif net_pnl_pct <= -(self.stop_loss * 100):
                    exit = True
                    reason = "STOP_LOSS"
                
                # Exit 3: End of day (3:15 PM approaching)
                elif current_time.time() >= time(15, 15):
                    exit = True
                    reason = "END_OF_DAY"
                
                # Exit 4: Max hold time
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
                        'transaction_costs': total_costs,
                        'net_pnl': net_pnl,
                        'net_pnl_pct': net_pnl_pct,
                        'result': 'WIN' if net_pnl > 0 else 'LOSS',
                        'exit_reason': reason,
                        'hold_minutes': periods_held * 5,
                        'cost_breakdown': costs['breakdown']
                    })
                    position = None
            
            else:
                # No position - check entry
                
                # Only enter during market hours and early enough to exit same day
                if current_time.time() > time(14, 0):  # Don't enter after 2 PM
                    continue
                
                # Entry condition: IV in bottom threshold
                if current_iv_flag == 100:
                    position = {
                        'entry_index': i,
                        'entry_time': current_time,
                        'entry_date': current_date,
                        'entry_cost': current_cost
                    }
        
        # CRITICAL: Close any remaining position at end of data
        # This represents end-of-day force exit
        if position is not None:
            print("WARNING: Position still open at end of data - force closing")
            # Force exit at current price
            current_row = df.iloc[-1]
            current_cost = current_row['straddle_cost']
            entry_cost = position['entry_cost']
            
            costs = self.calculate_transaction_costs(entry_cost, current_cost)
            raw_pnl = current_cost - entry_cost
            net_pnl = raw_pnl - costs['total_costs']
            
            trades.append({
                'entry_time': position['entry_time'],
                'exit_time': current_row['datetime'],
                'entry_cost': entry_cost,
                'exit_cost': current_cost,
                'raw_pnl': raw_pnl,
                'transaction_costs': costs['total_costs'],
                'net_pnl': net_pnl,
                'net_pnl_pct': (net_pnl / entry_cost) * 100,
                'result': 'WIN' if net_pnl > 0 else 'LOSS',
                'exit_reason': 'FORCE_CLOSE',
                'hold_minutes': 0,
                'cost_breakdown': costs['breakdown']
            })
        
        return pd.DataFrame(trades)
    
    def calculate_performance(self, trades_df):
        """Calculate performance metrics with costs included"""
        
        if len(trades_df) == 0:
            return {
                'total_trades': 0,
                'message': 'No trades generated'
            }
        
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['result'] == 'WIN'])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100
        
        # Use NET P&L (after costs)
        total_net_pnl = trades_df['net_pnl'].sum()
        avg_net_pnl = trades_df['net_pnl'].mean()
        
        # Raw P&L (before costs) for comparison
        total_raw_pnl = trades_df['raw_pnl'].sum()
        total_costs = trades_df['transaction_costs'].sum()
        
        # Winners and losers
        winners = trades_df[trades_df['result'] == 'WIN']
        losers = trades_df[trades_df['result'] == 'LOSS']
        
        avg_win = winners['net_pnl'].mean() if len(winners) > 0 else 0
        avg_loss = losers['net_pnl'].mean() if len(losers) > 0 else 0
        
        # Profit factor
        total_wins = winners['net_pnl'].sum() if len(winners) > 0 else 0
        total_losses = abs(losers['net_pnl'].sum()) if len(losers) > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Sharpe ratio
        sharpe = (avg_net_pnl / trades_df['net_pnl'].std()) if trades_df['net_pnl'].std() > 0 else 0
        
        # Average hold time
        avg_hold_minutes = trades_df['hold_minutes'].mean()
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(win_rate, 1),
            'total_net_pnl': round(total_net_pnl, 2),
            'total_raw_pnl': round(total_raw_pnl, 2),
            'total_transaction_costs': round(total_costs, 2),
            'avg_net_pnl': round(avg_net_pnl, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'sharpe_ratio': round(sharpe, 2),
            'avg_hold_minutes': round(avg_hold_minutes, 1),
            'cost_impact_pct': round((total_costs / total_raw_pnl) * 100, 1) if total_raw_pnl != 0 else 0
        }


# Test the corrected strategy
if __name__ == "__main__":
    
    print("="*70)
    print("CORRECTED INTRADAY SCALPING STRATEGY")
    print("No Overnight Positions | Full Transaction Costs Included")
    print("="*70)
    
    # Load data
    straddle_df = pd.read_csv('straddle_data_prepared.csv')
    straddle_df['datetime'] = pd.to_datetime(straddle_df['datetime'])
    
    print(f"\nData loaded: {len(straddle_df)} rows")
    
    # Run corrected strategy
    strategy = IntradayScalpingStrategy(
        iv_threshold=30,
        profit_target=0.15,   # 15% to cover costs
        stop_loss=0.10,       # 10% tight stop
        max_hold_minutes=180, # 3 hours max
        brokerage_per_leg=10  # ₹10 per leg
    )
    
    print("\nRunning intraday scalping backtest...")
    trades_df = strategy.generate_signals(straddle_df)
    
    if len(trades_df) > 0:
        # Save results
        trades_df.to_csv('intraday_scalping_results.csv', index=False)
        print("✅ Results saved to intraday_scalping_results.csv")
        
        # Calculate performance
        performance = strategy.calculate_performance(trades_df)
        
        print("\n" + "="*70)
        print("CORRECTED PERFORMANCE (WITH ALL COSTS)")
        print("="*70)
        
        print(f"\nTotal Trades:           {performance['total_trades']}")
        print(f"Winning Trades:         {performance['winning_trades']}")
        print(f"Losing Trades:          {performance['losing_trades']}")
        print(f"Win Rate:               {performance['win_rate']}%")
        
        print(f"\n{'BEFORE COSTS:':<30}")
        print(f"  Raw P&L:              ₹{performance['total_raw_pnl']:,.2f}")
        
        print(f"\n{'TRANSACTION COSTS:':<30}")
        print(f"  Total Costs:          ₹{performance['total_transaction_costs']:,.2f}")
        print(f"  Cost Impact:          {performance['cost_impact_pct']}% of raw P&L")
        
        print(f"\n{'AFTER COSTS (REAL):':<30}")
        print(f"  Net P&L:              ₹{performance['total_net_pnl']:,.2f}")
        print(f"  Avg P&L per Trade:    ₹{performance['avg_net_pnl']:.2f}")
        print(f"  Avg Win:              ₹{performance['avg_win']:.2f}")
        print(f"  Avg Loss:             ₹{performance['avg_loss']:.2f}")
        
        print(f"\n{'RISK METRICS:':<30}")
        print(f"  Profit Factor:        {performance['profit_factor']}")
        print(f"  Sharpe Ratio:         {performance['sharpe_ratio']}")
        print(f"  Avg Hold Time:        {performance['avg_hold_minutes']:.1f} minutes")
        
        # Show sample trades
        print("\n" + "="*70)
        print("SAMPLE TRADES (First 5)")
        print("="*70)
        
        sample = trades_df.head(5)
        for idx, trade in sample.iterrows():
            print(f"\nTrade #{idx+1}:")
            print(f"  Entry: {trade['entry_time']}")
            print(f"  Exit:  {trade['exit_time']} ({trade['exit_reason']})")
            print(f"  Hold:  {trade['hold_minutes']} minutes")
            print(f"  Raw P&L:   ₹{trade['raw_pnl']:.2f}")
            print(f"  Costs:     ₹{trade['transaction_costs']:.2f}")
            print(f"  Net P&L:   ₹{trade['net_pnl']:.2f} ({trade['net_pnl_pct']:.1f}%)")
            print(f"  Result:    {trade['result']}")
        
        # Save performance
        perf_df = pd.DataFrame([performance])
        perf_df.to_csv('intraday_scalping_performance.csv', index=False)
        
        print("\n✅ Performance metrics saved!")
        
        # Cost breakdown
        print("\n" + "="*70)
        print("TRANSACTION COST BREAKDOWN (Total)")
        print("="*70)
        
        total_brokerage = trades_df['cost_breakdown'].apply(lambda x: x['brokerage']).sum()
        total_gst = trades_df['cost_breakdown'].apply(lambda x: x['gst']).sum()
        total_stt = trades_df['cost_breakdown'].apply(lambda x: x['stt']).sum()
        total_exchange = trades_df['cost_breakdown'].apply(lambda x: x['exchange']).sum()
        
        print(f"Brokerage:       ₹{total_brokerage:,.2f}")
        print(f"GST:             ₹{total_gst:,.2f}")
        print(f"STT:             ₹{total_stt:,.2f}")
        print(f"Exchange Charges:₹{total_exchange:,.2f}")
        print(f"{'─'*40}")
        print(f"TOTAL:           ₹{performance['total_transaction_costs']:,.2f}")
        
    else:
        print("⚠️ No trades generated with these parameters!")
        print("Try adjusting:")
        print("- Lower IV threshold (e.g., 35th percentile)")
        print("- Lower profit target")
        print("- Longer max hold time")
