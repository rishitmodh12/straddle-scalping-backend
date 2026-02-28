"""
ML-BASED VOLATILITY SWING TRADING
Realistic approach: Predict 2-5 day moves, not scalping
Based on what actually works in real markets
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
import joblib
from datetime import datetime, timedelta


class MLVolatilitySwingTrader:
    """
    REALISTIC ML STRATEGY:
    
    1. Predict if 2-5 day move will be profitable for straddle
    2. Hold positions 2-5 days (not minutes!)
    3. Costs become manageable (5% not 25%)
    4. Target 50-80% profits
    5. ML focuses on ENTRY TIMING (when to wait vs when to enter)
    """
    
    def __init__(self):
        self.model = None
        self.feature_cols = []
        
        # Strategy parameters
        self.hold_days = 3  # Hold for 3 days
        self.profit_target = 0.50  # 50% profit target
        self.stop_loss = 0.35  # 35% stop loss
        self.ml_probability_threshold = 0.55  # Only enter if ML says 55%+ chance
        
    def calculate_features(self, df):
        """
        Calculate 15 features that predict multi-day volatility
        Based on academic research and practitioner experience
        """
        
        df = df.copy()
        
        # ===== CATEGORY 1: IV METRICS =====
        
        # 1. IV Percentile (classic)
        df['iv_percentile'] = df['avg_iv'].rolling(100).apply(
            lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50
        )
        
        # 2. IV Rank (min-max normalized)
        df['iv_rank'] = df['avg_iv'].rolling(252).apply(
            lambda x: ((x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100) 
            if (x.max() > x.min()) else 50
        )
        
        # 3. IV Momentum (5-day change)
        df['iv_momentum'] = df['avg_iv'].pct_change(5) * 100
        
        # 4. IV Acceleration (change in momentum)
        df['iv_acceleration'] = df['iv_momentum'].diff(5)
        
        # ===== CATEGORY 2: REALIZED VOLATILITY =====
        
        # 5. Historical Vol 20-day
        returns = np.log(df['spot'] / df['spot'].shift(1))
        df['hv_20'] = returns.rolling(20).std() * np.sqrt(252) * 100
        
        # 6. Historical Vol 60-day
        df['hv_60'] = returns.rolling(60).std() * np.sqrt(252) * 100
        
        # 7. IV vs HV Spread (key predictor!)
        df['iv_hv_spread'] = df['avg_iv'] - df['hv_20']
        
        # 8. HV Ratio (recent vs long-term)
        df['hv_ratio'] = df['hv_20'] / df['hv_60']
        
        # ===== CATEGORY 3: PRICE ACTION =====
        
        # 9. ATR (Average True Range) as % of spot
        df['price_range'] = df['spot'].rolling(14).apply(
            lambda x: (x.max() - x.min()) / x.mean() * 100
        )
        
        # 10. Bollinger Band Width
        sma = df['spot'].rolling(20).mean()
        std = df['spot'].rolling(20).std()
        df['bb_width'] = (std * 2 / sma) * 100
        
        # 11. Price Momentum (10-day)
        df['price_momentum_10'] = df['spot'].pct_change(10) * 100
        
        # 12. Price Momentum (20-day)
        df['price_momentum_20'] = df['spot'].pct_change(20) * 100
        
        # ===== CATEGORY 4: VOLUME/LIQUIDITY =====
        
        # 13. Volume Surge (vs 20-day average)
        avg_volume = df['total_volume'].rolling(20).mean()
        df['volume_ratio'] = df['total_volume'] / avg_volume
        
        # 14. OI Change (open interest momentum)
        df['oi_change'] = df['total_oi'].pct_change(5) * 100
        
        # 15. Straddle Cost Percentile (is it cheap?)
        df['straddle_pct'] = (df['straddle_cost'] / df['spot']) * 100
        
        return df
    
    def create_target_variable(self, df, forward_days=3):
        """
        Target: Will a 3-day hold be profitable?
        
        More realistic than scalping:
        - Look forward 3 trading days
        - Check if max move exceeds breakeven
        - Binary: 1 = profitable, 0 = not
        """
        
        df = df.copy()
        
        # Calculate breakeven
        df['breakeven_pct'] = (df['straddle_cost'] / df['spot']) * 100
        
        # Look forward N days (in 5-min intervals)
        # 1 day ≈ 75 periods (9:15-3:30 = 6h15m = 75 × 5min)
        forward_periods = forward_days * 75
        
        # Calculate maximum absolute move over next N days
        future_high = df['spot'].shift(-1).rolling(forward_periods).max().shift(-forward_periods + 1)
        future_low = df['spot'].shift(-1).rolling(forward_periods).min().shift(-forward_periods + 1)
        current_spot = df['spot']
        
        move_up = ((future_high - current_spot) / current_spot * 100).fillna(0)
        move_down = ((current_spot - future_low) / current_spot * 100).fillna(0)
        max_move = pd.concat([move_up, move_down], axis=1).max(axis=1)
        
        # Target: 1 if max move > breakeven
        df['target'] = (max_move > df['breakeven_pct'] * 1.2).astype(int)  # Need 20% cushion
        
        # Also store for analysis
        df['future_max_move'] = max_move
        
        return df
    
    def prepare_ml_dataset(self, df):
        """Prepare clean dataset for ML"""
        
        # Calculate features
        df_features = self.calculate_features(df)
        
        # Create target
        df_labeled = self.create_target_variable(df_features, forward_days=3)
        
        # Feature columns
        self.feature_cols = [
            'iv_percentile', 'iv_rank', 'iv_momentum', 'iv_acceleration',
            'hv_20', 'hv_60', 'iv_hv_spread', 'hv_ratio',
            'price_range', 'bb_width', 'price_momentum_10', 'price_momentum_20',
            'volume_ratio', 'oi_change', 'straddle_pct'
        ]
        
        # Remove NaN
        df_clean = df_labeled.dropna(subset=self.feature_cols + ['target'])
        
        # Only use data where we have future visibility
        # (i.e., not last 3 days where we can't look forward)
        df_clean = df_clean[:-225]  # Remove last 3 days (225 periods)
        
        return df_clean
    
    def train_models(self, df):
        """Train multiple models and compare"""
        
        print("="*70)
        print("ML TRAINING - SWING TRADING STRATEGY")
        print("="*70)
        
        # Prepare data
        print("\nPreparing dataset...")
        df_clean = self.prepare_ml_dataset(df)
        
        print(f"Total samples: {len(df_clean)}")
        print(f"Profitable setups: {df_clean['target'].sum()} ({df_clean['target'].mean()*100:.1f}%)")
        
        # Train-test split (time-based)
        split_idx = int(len(df_clean) * 0.7)
        train = df_clean.iloc[:split_idx]
        test = df_clean.iloc[split_idx:]
        
        X_train = train[self.feature_cols]
        y_train = train['target']
        X_test = test[self.feature_cols]
        y_test = test['target']
        
        print(f"\nTrain: {len(X_train)} samples")
        print(f"Test:  {len(X_test)} samples")
        
        # ===== MODEL 1: LOGISTIC REGRESSION =====
        print("\n" + "="*70)
        print("MODEL 1: LOGISTIC REGRESSION")
        print("="*70)
        
        lr = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
        lr.fit(X_train, y_train)
        
        lr_pred = lr.predict(X_test)
        lr_prob = lr.predict_proba(X_test)[:, 1]
        
        print(f"\nAccuracy:  {accuracy_score(y_test, lr_pred):.3f}")
        print(f"Precision: {precision_score(y_test, lr_pred):.3f}")
        print(f"Recall:    {recall_score(y_test, lr_pred):.3f}")
        
        # ===== MODEL 2: RANDOM FOREST =====
        print("\n" + "="*70)
        print("MODEL 2: RANDOM FOREST")
        print("="*70)
        
        rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_split=100,
            random_state=42,
            class_weight='balanced',
            n_jobs=-1
        )
        rf.fit(X_train, y_train)
        
        rf_pred = rf.predict(X_test)
        rf_prob = rf.predict_proba(X_test)[:, 1]
        
        print(f"\nAccuracy:  {accuracy_score(y_test, rf_pred):.3f}")
        print(f"Precision: {precision_score(y_test, rf_pred):.3f}")
        print(f"Recall:    {recall_score(y_test, rf_pred):.3f}")
        
        # Feature importance
        importances = pd.DataFrame({
            'feature': self.feature_cols,
            'importance': rf.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print("\nTop 10 Features:")
        print(importances.head(10).to_string(index=False))
        
        # ===== MODEL 3: GRADIENT BOOSTING =====
        print("\n" + "="*70)
        print("MODEL 3: GRADIENT BOOSTING")
        print("="*70)
        
        gb = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        gb.fit(X_train, y_train)
        
        gb_pred = gb.predict(X_test)
        gb_prob = gb.predict_proba(X_test)[:, 1]
        
        print(f"\nAccuracy:  {accuracy_score(y_test, gb_pred):.3f}")
        print(f"Precision: {precision_score(y_test, gb_pred):.3f}")
        print(f"Recall:    {recall_score(y_test, gb_pred):.3f}")
        
        # Choose best model (highest precision)
        models = {
            'logistic_regression': (lr, precision_score(y_test, lr_pred)),
            'random_forest': (rf, precision_score(y_test, rf_pred)),
            'gradient_boosting': (gb, precision_score(y_test, gb_pred))
        }
        
        best_name = max(models.items(), key=lambda x: x[1][1])[0]
        self.model = models[best_name][0]
        
        print(f"\n✅ Best model: {best_name.upper()}")
        
        # Save model
        joblib.dump(self.model, f'{best_name}_model.pkl')
        joblib.dump(self.feature_cols, 'feature_columns.pkl')
        
        return {
            'train_data': train,
            'test_data': test,
            'X_test': X_test,
            'y_test': y_test,
            'best_model': best_name
        }
    
    def backtest_ml_strategy(self, df):
        """
        Backtest ML strategy with REALISTIC parameters:
        - 3-day holds (not intraday)
        - ₹50 costs per trade (manageable with 3-day holds)
        - 50% profit target, 35% stop loss
        """
        
        print("\n" + "="*70)
        print("BACKTESTING ML STRATEGY (SWING TRADING)")
        print("="*70)
        
        # Prepare data
        df_clean = self.prepare_ml_dataset(df)
        
        # Get ML predictions
        X = df_clean[self.feature_cols]
        probabilities = self.model.predict_proba(X)[:, 1]
        
        df_clean['ml_probability'] = probabilities
        
        # Simulate trading
        trades = []
        i = 0
        
        while i < len(df_clean) - 225:  # Stop 3 days before end
            row = df_clean.iloc[i]
            
            # Entry condition: ML probability > threshold
            if row['ml_probability'] >= self.ml_probability_threshold:
                
                entry_cost = row['straddle_cost']
                entry_time = row['datetime']
                entry_idx = i
                
                # Hold for 3 days (225 periods)
                hold_periods = 225
                
                # Track max profit and loss during hold
                max_profit_pct = 0
                hit_stop = False
                hit_target = False
                exit_idx = min(i + hold_periods, len(df_clean) - 1)
                exit_reason = "TIME_LIMIT"
                
                for j in range(i+1, min(i + hold_periods + 1, len(df_clean))):
                    current_cost = df_clean.iloc[j]['straddle_cost']
                    pnl_pct = ((current_cost - entry_cost) / entry_cost) * 100
                    
                    # Check exit conditions
                    if pnl_pct >= (self.profit_target * 100):
                        exit_idx = j
                        exit_reason = "PROFIT_TARGET"
                        hit_target = True
                        break
                    elif pnl_pct <= -(self.stop_loss * 100):
                        exit_idx = j
                        exit_reason = "STOP_LOSS"
                        hit_stop = True
                        break
                
                # Calculate final P&L
                exit_cost = df_clean.iloc[exit_idx]['straddle_cost']
                exit_time = df_clean.iloc[exit_idx]['datetime']
                
                raw_pnl = exit_cost - entry_cost
                raw_pnl_pct = (raw_pnl / entry_cost) * 100
                
                # Transaction costs (₹50 total)
                transaction_costs = 50
                
                net_pnl = raw_pnl - transaction_costs
                net_pnl_pct = (net_pnl / entry_cost) * 100
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': exit_time,
                    'ml_probability': row['ml_probability'],
                    'entry_cost': entry_cost,
                    'exit_cost': exit_cost,
                    'raw_pnl': raw_pnl,
                    'costs': transaction_costs,
                    'net_pnl': net_pnl,
                    'net_pnl_pct': net_pnl_pct,
                    'result': 'WIN' if net_pnl > 0 else 'LOSS',
                    'exit_reason': exit_reason,
                    'hold_days': (exit_idx - entry_idx) / 75  # Convert periods to days
                })
                
                # Jump to after this trade (no overlapping positions)
                i = exit_idx + 12  # Wait 1 hour after exit
            else:
                i += 1
        
        trades_df = pd.DataFrame(trades)
        
        if len(trades_df) == 0:
            print("No trades generated!")
            return None, None
        
        # Calculate performance
        total_trades = len(trades_df)
        wins = len(trades_df[trades_df['result'] == 'WIN'])
        losses = total_trades - wins
        win_rate = (wins / total_trades) * 100
        
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
        
        # Results
        results = {
            'total_trades': total_trades,
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
            'avg_hold_days': round(trades_df['hold_days'].mean(), 1),
            'avg_ml_prob': round(trades_df['ml_probability'].mean(), 3)
        }
        
        # Print results
        print(f"\nTotal Trades:        {results['total_trades']}")
        print(f"Win Rate:            {results['win_rate']}%")
        print(f"Avg Hold:            {results['avg_hold_days']} days")
        print(f"Avg ML Confidence:   {results['avg_ml_prob']}")
        
        print(f"\nBEFORE COSTS:")
        print(f"  Raw P&L:           ₹{results['total_raw_pnl']:,.2f}")
        
        print(f"\nCOSTS:")
        print(f"  Total:             ₹{results['total_costs']:,.2f}")
        print(f"  Per Trade:         ₹{results['total_costs']/results['total_trades']:.2f}")
        
        print(f"\nAFTER COSTS:")
        print(f"  Net P&L:           ₹{results['total_net_pnl']:,.2f}")
        print(f"  Avg P&L/Trade:     ₹{results['avg_net_pnl']:.2f}")
        print(f"  Avg Win:           ₹{results['avg_win']:.2f}")
        print(f"  Avg Loss:          ₹{results['avg_loss']:.2f}")
        
        print(f"\nRISK METRICS:")
        print(f"  Profit Factor:     {results['profit_factor']}")
        print(f"  Sharpe Ratio:      {results['sharpe_ratio']}")
        
        return results, trades_df


# ===== MAIN EXECUTION =====
if __name__ == "__main__":
    
    print("="*70)
    print("ML-BASED SWING TRADING FOR OPTIONS")
    print("Realistic Strategy: 2-5 Day Holds, Not Scalping")
    print("="*70)
    
    # Load data
    df = pd.read_csv('straddle_data_prepared.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # Add total volume and OI (combine call + put)
    df['total_volume'] = df.get('volume_call', 0) + df.get('volume_put', 0)
    df['total_oi'] = df.get('oi_call', 0) + df.get('oi_put', 0)
    
    # If columns don't exist, create dummy ones
    if 'total_volume' not in df.columns or df['total_volume'].sum() == 0:
        df['total_volume'] = 1000000  # Dummy
    if 'total_oi' not in df.columns or df['total_oi'].sum() == 0:
        df['total_oi'] = 500000  # Dummy
    
    print(f"\nData loaded: {len(df)} rows")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    
    # Initialize trader
    trader = MLVolatilitySwingTrader()
    
    # Train models
    train_results = trader.train_models(df)
    
    # Backtest
    results, trades_df = trader.backtest_ml_strategy(df)
    
    if results:
        # Save results
        results_df = pd.DataFrame([results])
        results_df.to_csv('ml_swing_performance.csv', index=False)
        
        trades_df.to_csv('ml_swing_trades.csv', index=False)
        
        print("\n" + "="*70)
        print("✅ Results saved!")
        print("="*70)
        
        # Show sample trades
        print("\nSample Trades:")
        for idx in range(min(5, len(trades_df))):
            t = trades_df.iloc[idx]
            print(f"\nTrade #{idx+1}:")
            print(f"  ML Prob:   {t['ml_probability']:.1%}")
            print(f"  Entry:     {t['entry_time']}")
            print(f"  Exit:      {t['exit_time']} ({t['exit_reason']})")
            print(f"  Hold:      {t['hold_days']:.1f} days")
            print(f"  Net P&L:   ₹{t['net_pnl']:.2f} ({t['net_pnl_pct']:.1f}%)")
            print(f"  Result:    {t['result']}")
        
        # Final verdict
        print("\n" + "="*70)
        if results['total_net_pnl'] > 0:
            print(f"✅ PROFITABLE: ₹{results['total_net_pnl']:,.2f}")
            print(f"   {results['total_trades']} trades, {results['win_rate']}% win rate")
            print(f"   Avg hold: {results['avg_hold_days']} days")
        else:
            print(f"⚠️ LOSS: ₹{results['total_net_pnl']:,.2f}")
            print("   Try adjusting probability threshold or hold period")
        print("="*70)
