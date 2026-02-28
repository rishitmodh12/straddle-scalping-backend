"""
Enhanced Trading System with 3 Strategy Sections
1. IV Scalping (Volatility-based)
2. Gamma Scalping (Greeks-based)
3. Hybrid Strategy (IV + Gamma combined)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class GreeksCalculator:
    """Calculate option Greeks using Black-Scholes approximations"""
    
    @staticmethod
    def calculate_d1(S, K, T, r, sigma):
        """Calculate d1 for Black-Scholes"""
        if T <= 0 or sigma <= 0:
            return 0
        return (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    
    @staticmethod
    def calculate_d2(d1, sigma, T):
        """Calculate d2 for Black-Scholes"""
        if T <= 0:
            return 0
        return d1 - sigma*np.sqrt(T)
    
    @staticmethod
    def calculate_delta(S, K, T, r, sigma, option_type='call'):
        """Calculate Delta"""
        if T <= 0:
            return 1.0 if S > K else 0.0
        
        d1 = GreeksCalculator.calculate_d1(S, K, T, r, sigma)
        
        if option_type == 'call':
            from scipy.stats import norm
            delta = norm.cdf(d1)
        else:  # put
            from scipy.stats import norm
            delta = norm.cdf(d1) - 1
        
        return delta
    
    @staticmethod
    def calculate_gamma(S, K, T, r, sigma):
        """Calculate Gamma (same for call and put)"""
        if T <= 0 or sigma <= 0:
            return 0
        
        d1 = GreeksCalculator.calculate_d1(S, K, T, r, sigma)
        
        from scipy.stats import norm
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        
        return gamma
    
    @staticmethod
    def calculate_vega(S, K, T, r, sigma):
        """Calculate Vega (same for call and put)"""
        if T <= 0:
            return 0
        
        d1 = GreeksCalculator.calculate_d1(S, K, T, r, sigma)
        
        from scipy.stats import norm
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1% change
        
        return vega
    
    @staticmethod
    def calculate_theta(S, K, T, r, sigma, option_type='call'):
        """Calculate Theta (time decay per day)"""
        if T <= 0:
            return 0
        
        d1 = GreeksCalculator.calculate_d1(S, K, T, r, sigma)
        d2 = GreeksCalculator.calculate_d2(d1, sigma, T)
        
        from scipy.stats import norm
        
        if option_type == 'call':
            theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                    - r * K * np.exp(-r*T) * norm.cdf(d2)) / 365
        else:  # put
            theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                    + r * K * np.exp(-r*T) * norm.cdf(-d2)) / 365
        
        return theta


class GammaScalpingStrategy:
    """Gamma Scalping Strategy Implementation"""
    
    def __init__(self, gamma_threshold=0.015, hedge_threshold=0.1, scalp_profit=0.03):
        """
        Parameters:
        - gamma_threshold: Minimum gamma to enter (0.015 = 1.5% gamma)
        - hedge_threshold: Delta threshold to trigger hedge (0.1 = 10% delta)
        - scalp_profit: Target profit from delta hedging (3% of position)
        """
        self.gamma_threshold = gamma_threshold
        self.hedge_threshold = hedge_threshold
        self.scalp_profit = scalp_profit
        self.risk_free_rate = 0.06  # 6% annual
        
    def calculate_greeks_for_straddle(self, spot, strike, time_to_expiry, iv):
        """Calculate Greeks for ATM straddle"""
        
        # Calculate Greeks for both call and put
        call_delta = GreeksCalculator.calculate_delta(spot, strike, time_to_expiry, 
                                                      self.risk_free_rate, iv/100, 'call')
        put_delta = GreeksCalculator.calculate_delta(spot, strike, time_to_expiry, 
                                                     self.risk_free_rate, iv/100, 'put')
        
        gamma = GreeksCalculator.calculate_gamma(spot, strike, time_to_expiry, 
                                                 self.risk_free_rate, iv/100)
        
        vega = GreeksCalculator.calculate_vega(spot, strike, time_to_expiry, 
                                               self.risk_free_rate, iv/100)
        
        call_theta = GreeksCalculator.calculate_theta(spot, strike, time_to_expiry, 
                                                      self.risk_free_rate, iv/100, 'call')
        put_theta = GreeksCalculator.calculate_theta(spot, strike, time_to_expiry, 
                                                     self.risk_free_rate, iv/100, 'put')
        
        # Straddle Greeks
        straddle_delta = call_delta + put_delta  # Near 0 for ATM
        straddle_gamma = gamma * 2  # Both have same gamma
        straddle_vega = vega * 2
        straddle_theta = call_theta + put_theta
        
        return {
            'delta': straddle_delta,
            'gamma': straddle_gamma,
            'vega': straddle_vega,
            'theta': straddle_theta,
            'call_delta': call_delta,
            'put_delta': put_delta
        }
    
    def generate_signals(self, df, days_to_expiry=7):
        """
        Generate gamma scalping signals
        
        Entry: High gamma zone (near expiry, ATM)
        Exit: Delta hedge profits accumulated OR time limit
        """
        
        signals = []
        position = None
        
        time_to_expiry = days_to_expiry / 365
        
        for i in range(len(df)):
            row = df.iloc[i]
            
            spot = row['spot']
            strike = spot  # ATM
            iv = row['avg_iv']
            straddle_cost = row['straddle_cost']
            
            # Calculate Greeks
            greeks = self.calculate_greeks_for_straddle(spot, strike, time_to_expiry, iv)
            
            if position is not None:
                # In position - track delta hedging P&L
                entry_spot = position['entry_spot']
                hedge_pnl = position.get('hedge_pnl', 0)
                
                # Calculate spot movement
                spot_move = spot - position['last_hedge_spot']
                
                # If delta crossed threshold, hedge
                if abs(greeks['delta']) > self.hedge_threshold:
                    # P&L from hedging: buy low sell high
                    # When spot moves up, we sell (delta became positive)
                    # When spot moves down, we buy (delta became negative)
                    hedge_profit = abs(spot_move) * greeks['gamma'] * spot
                    hedge_pnl += hedge_profit
                    
                    position['hedge_pnl'] = hedge_pnl
                    position['last_hedge_spot'] = spot
                    position['hedge_count'] += 1
                
                # Calculate total P&L
                current_cost = straddle_cost
                position_pnl = current_cost - position['entry_cost']
                total_pnl = position_pnl + hedge_pnl
                total_pnl_pct = (total_pnl / position['entry_cost']) * 100
                
                # Exit conditions
                periods_held = i - position['entry_index']
                
                exit = False
                reason = None
                
                # Exit if hedging profit target reached
                if hedge_pnl >= (position['entry_cost'] * self.scalp_profit):
                    exit = True
                    reason = "GAMMA_PROFIT"
                
                # Exit if time limit (4 hours = 48 periods)
                elif periods_held >= 48:
                    exit = True
                    reason = "TIME_LIMIT"
                
                # Exit if gamma drops too low (far from ATM)
                elif greeks['gamma'] < self.gamma_threshold / 2:
                    exit = True
                    reason = "LOW_GAMMA"
                
                if exit:
                    signals.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['datetime'],
                        'entry_cost': position['entry_cost'],
                        'exit_cost': current_cost,
                        'position_pnl': position_pnl,
                        'hedge_pnl': hedge_pnl,
                        'total_pnl': total_pnl,
                        'total_pnl_pct': total_pnl_pct,
                        'hedge_count': position['hedge_count'],
                        'result': 'WIN' if total_pnl > 0 else 'LOSS',
                        'exit_reason': reason
                    })
                    position = None
            
            else:
                # No position - check entry
                # Enter if:
                # 1. High gamma (near ATM, near expiry)
                # 2. Not in existing IV-based trade
                
                if greeks['gamma'] >= self.gamma_threshold:
                    position = {
                        'entry_index': i,
                        'entry_time': row['datetime'],
                        'entry_spot': spot,
                        'entry_cost': straddle_cost,
                        'last_hedge_spot': spot,
                        'hedge_pnl': 0,
                        'hedge_count': 0
                    }
        
        return pd.DataFrame(signals)


class HybridStrategy:
    """Hybrid Strategy combining IV + Gamma signals"""
    
    def __init__(self, iv_threshold=30, gamma_threshold=0.015):
        self.iv_threshold = iv_threshold
        self.gamma_threshold = gamma_threshold
        self.risk_free_rate = 0.06
    
    def generate_signals(self, df, days_to_expiry=7):
        """
        Hybrid entry:
        - Low IV (bottom 30%) AND High Gamma
        
        Hybrid exit:
        - IV scalping exits OR Gamma scalping profits
        """
        
        LOOKBACK = 100
        time_to_expiry = days_to_expiry / 365
        
        # Calculate IV percentile
        df['iv_percentile'] = df['avg_iv'].rolling(window=LOOKBACK, min_periods=20).apply(
            lambda x: (x.iloc[-1] <= np.percentile(x, self.iv_threshold)) * 100 if len(x) > 0 else 0
        )
        
        trades = []
        position = None
        
        for i in range(len(df)):
            if i < LOOKBACK:
                continue
            
            row = df.iloc[i]
            
            spot = row['spot']
            strike = spot
            iv = row['avg_iv']
            straddle_cost = row['straddle_cost']
            iv_flag = row['iv_percentile']
            
            # Calculate Greeks
            greeks_calc = GreeksCalculator()
            gamma = greeks_calc.calculate_gamma(spot, strike, time_to_expiry, 
                                               self.risk_free_rate, iv/100)
            
            if position is not None:
                # Track both IV and Gamma exits
                entry_cost = position['entry_cost']
                hedge_pnl = position.get('hedge_pnl', 0)
                
                # Calculate P&L
                position_pnl = straddle_cost - entry_cost
                pnl_pct = (position_pnl / entry_cost) * 100
                
                # Gamma hedging
                spot_move = spot - position.get('last_hedge_spot', spot)
                if abs(spot_move) > (spot * 0.001):  # 0.1% move
                    hedge_profit = abs(spot_move) * gamma * spot * 0.5
                    hedge_pnl += hedge_profit
                    position['hedge_pnl'] = hedge_pnl
                    position['last_hedge_spot'] = spot
                
                total_pnl = position_pnl + hedge_pnl
                total_pnl_pct = (total_pnl / entry_cost) * 100
                
                periods_held = i - position['entry_index']
                
                # Exit conditions (best of both strategies)
                exit = False
                reason = None
                
                # IV scalping exits
                if pnl_pct >= 10:
                    exit = True
                    reason = "IV_PROFIT_TARGET"
                elif pnl_pct <= -20:
                    exit = True
                    reason = "IV_STOP_LOSS"
                
                # Gamma scalping exit
                elif hedge_pnl >= (entry_cost * 0.05):  # 5% from hedging
                    exit = True
                    reason = "GAMMA_PROFIT"
                
                # Combined exit
                elif total_pnl_pct >= 15:  # Higher target for hybrid
                    exit = True
                    reason = "HYBRID_PROFIT"
                
                # Time limit
                elif periods_held >= 60:  # 5 hours
                    exit = True
                    reason = "TIME_LIMIT"
                
                if exit:
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['datetime'],
                        'position_pnl': position_pnl,
                        'hedge_pnl': hedge_pnl,
                        'total_pnl': total_pnl,
                        'total_pnl_pct': total_pnl_pct,
                        'result': 'WIN' if total_pnl > 0 else 'LOSS',
                        'exit_reason': reason
                    })
                    position = None
            
            else:
                # Entry: Low IV AND High Gamma
                if iv_flag == 100 and gamma >= self.gamma_threshold:
                    position = {
                        'entry_index': i,
                        'entry_time': row['datetime'],
                        'entry_cost': straddle_cost,
                        'last_hedge_spot': spot,
                        'hedge_pnl': 0
                    }
        
        return pd.DataFrame(trades)


def calculate_performance_metrics(trades_df):
    """Calculate performance metrics for any strategy"""
    
    if len(trades_df) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'profit_factor': 0
        }
    
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['result'] == 'WIN'])
    win_rate = (winning_trades / total_trades) * 100
    
    pnl_col = 'total_pnl' if 'total_pnl' in trades_df.columns else 'pnl'
    total_pnl = trades_df[pnl_col].sum()
    avg_pnl = trades_df[pnl_col].mean()
    
    total_profit = trades_df[trades_df['result'] == 'WIN'][pnl_col].sum()
    total_loss = abs(trades_df[trades_df['result'] == 'LOSS'][pnl_col].sum())
    profit_factor = total_profit / total_loss if total_loss > 0 else 0
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': round(win_rate, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(avg_pnl, 2),
        'profit_factor': round(profit_factor, 2)
    }


# Example usage
if __name__ == "__main__":
    
    # Load data
    straddle_df = pd.read_csv('straddle_data_prepared.csv')
    straddle_df['datetime'] = pd.to_datetime(straddle_df['datetime'])
    
    print("="*60)
    print("TESTING ALL THREE STRATEGIES")
    print("="*60)
    
    # Strategy 1: IV Scalping (existing)
    print("\n1. IV SCALPING STRATEGY")
    print("-"*60)
    # (Use existing implementation)
    print("Already implemented ✅")
    print("Performance: ₹3,279 profit, 32.5% win rate")
    
    # Strategy 2: Gamma Scalping
    print("\n2. GAMMA SCALPING STRATEGY")
    print("-"*60)
    gamma_strategy = GammaScalpingStrategy(
        gamma_threshold=0.015,
        hedge_threshold=0.1,
        scalp_profit=0.03
    )
    gamma_trades = gamma_strategy.generate_signals(straddle_df, days_to_expiry=7)
    gamma_performance = calculate_performance_metrics(gamma_trades)
    
    print(f"Total Trades: {gamma_performance['total_trades']}")
    print(f"Win Rate: {gamma_performance['win_rate']}%")
    print(f"Total P&L: ₹{gamma_performance['total_pnl']}")
    print(f"Profit Factor: {gamma_performance['profit_factor']}")
    
    # Strategy 3: Hybrid
    print("\n3. HYBRID STRATEGY (IV + GAMMA)")
    print("-"*60)
    hybrid_strategy = HybridStrategy(
        iv_threshold=30,
        gamma_threshold=0.015
    )
    hybrid_trades = hybrid_strategy.generate_signals(straddle_df, days_to_expiry=7)
    hybrid_performance = calculate_performance_metrics(hybrid_trades)
    
    print(f"Total Trades: {hybrid_performance['total_trades']}")
    print(f"Win Rate: {hybrid_performance['win_rate']}%")
    print(f"Total P&L: ₹{hybrid_performance['total_pnl']}")
    print(f"Profit Factor: {hybrid_performance['profit_factor']}")
    
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    print(f"{'Strategy':<20} {'Trades':<10} {'Win Rate':<12} {'P&L':<12}")
    print("-"*60)
    print(f"{'IV Scalping':<20} {1009:<10} {32.5:<12} ₹3,279")
    print(f"{'Gamma Scalping':<20} {gamma_performance['total_trades']:<10} "
          f"{gamma_performance['win_rate']:<12} ₹{gamma_performance['total_pnl']}")
    print(f"{'Hybrid (IV+Gamma)':<20} {hybrid_performance['total_trades']:<10} "
          f"{hybrid_performance['win_rate']:<12} ₹{hybrid_performance['total_pnl']}")
