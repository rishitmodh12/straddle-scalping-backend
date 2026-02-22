"""
ML-Based Volatility Prediction Strategy
Hackathon Implementation - Predicts if RV > IV for profitable straddles
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
import joblib
from datetime import datetime, timedelta


class VolatilityPredictor:
    """ML-based prediction of volatility expansion for straddle trading"""
    
    def __init__(self, lookback_days=252):
        self.lookback_days = lookback_days
        self.models = {}
        self.feature_cols = []
        
    def calculate_technical_indicators(self, df):
        """Calculate all features for ML model"""
        
        df = df.copy()
        
        # 1. IV Metrics
        df['iv_percentile'] = df['avg_iv'].rolling(window=100).apply(
            lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100
        )
        df['iv_rank'] = df['avg_iv'].rolling(window=252).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100 if x.max() > x.min() else 50
        )
        df['iv_change'] = df['avg_iv'].pct_change(5) * 100  # 5-period % change
        
        # 2. Historical Volatility (Realized Volatility)
        returns = np.log(df['spot'] / df['spot'].shift(1))
        df['hist_vol_20'] = returns.rolling(20).std() * np.sqrt(252) * 100
        df['hist_vol_50'] = returns.rolling(50).std() * np.sqrt(252) * 100
        
        # 3. ATR (Average True Range)
        # Approximate using spot high-low range
        df['true_range'] = abs(df['spot'].diff())
        df['atr_14'] = df['true_range'].rolling(14).mean()
        df['atr_pct'] = (df['atr_14'] / df['spot']) * 100
        
        # 4. ADX (Trend Strength) - Simplified
        price_change = df['spot'].diff()
        df['plus_dm'] = np.where(price_change > 0, price_change, 0)
        df['minus_dm'] = np.where(price_change < 0, abs(price_change), 0)
        df['adx'] = (df['plus_dm'].rolling(14).mean() + df['minus_dm'].rolling(14).mean()) / 2
        df['adx'] = (df['adx'] / df['spot']) * 100
        
        # 5. RSI (Relative Strength Index)
        delta = df['spot'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 6. Bollinger Band Width
        df['bb_middle'] = df['spot'].rolling(20).mean()
        df['bb_std'] = df['spot'].rolling(20).std()
        df['bb_width'] = (df['bb_std'] * 4) / df['bb_middle'] * 100
        
        # 7. Price Momentum
        df['momentum_5'] = df['spot'].pct_change(5) * 100
        df['momentum_10'] = df['spot'].pct_change(10) * 100
        
        # 8. IV vs HV Spread
        df['iv_hv_spread'] = df['avg_iv'] - df['hist_vol_20']
        
        return df
    
    def create_target_variable(self, df, forward_days=2):
        """
        Create binary target: 1 if future move > straddle breakeven, else 0
        
        Straddle breakeven = straddle cost as % of spot
        Future move = absolute return over next 2 days
        """
        
        df = df.copy()
        
        # Calculate breakeven as % of spot
        df['breakeven_pct'] = (df['straddle_cost'] / df['spot']) * 100
        
        # Calculate future absolute return
        df['future_spot'] = df['spot'].shift(-forward_days)
        df['future_abs_return'] = abs((df['future_spot'] - df['spot']) / df['spot']) * 100
        
        # Target: 1 if future move > breakeven
        df['target'] = (df['future_abs_return'] > df['breakeven_pct']).astype(int)
        
        # Also calculate if profitable for validation
        df['would_profit'] = df['target']
        
        return df
    
    def prepare_features(self, df):
        """Prepare feature matrix for ML"""
        
        feature_cols = [
            'iv_percentile', 'iv_rank', 'iv_change',
            'hist_vol_20', 'hist_vol_50',
            'atr_pct', 'adx', 'rsi',
            'bb_width', 'momentum_5', 'momentum_10',
            'iv_hv_spread'
        ]
        
        self.feature_cols = feature_cols
        
        return df[feature_cols], df['target']
    
    def train_models(self, df):
        """Train both Logistic Regression and Random Forest"""
        
        print("Preparing data...")
        df_processed = self.calculate_technical_indicators(df)
        df_processed = self.create_target_variable(df_processed, forward_days=2)
        
        # Remove NaN values
        df_clean = df_processed.dropna()
        
        print(f"Total samples: {len(df_clean)}")
        print(f"Profitable cases: {df_clean['target'].sum()} ({df_clean['target'].mean()*100:.1f}%)")
        
        # Prepare features
        X, y = self.prepare_features(df_clean)
        
        # Train-test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )
        
        print(f"\nTrain size: {len(X_train)}, Test size: {len(X_test)}")
        
        # Model 1: Logistic Regression
        print("\n" + "="*60)
        print("TRAINING LOGISTIC REGRESSION")
        print("="*60)
        
        lr_model = LogisticRegression(max_iter=1000, random_state=42)
        lr_model.fit(X_train, y_train)
        
        lr_pred = lr_model.predict(X_test)
        lr_prob = lr_model.predict_proba(X_test)[:, 1]
        
        print("\nLogistic Regression Results:")
        print(f"Accuracy: {accuracy_score(y_test, lr_pred):.3f}")
        print(f"Precision: {precision_score(y_test, lr_pred):.3f}")
        print(f"Recall: {recall_score(y_test, lr_pred):.3f}")
        
        # Cross-validation
        cv_scores = cross_val_score(lr_model, X_train, y_train, cv=5)
        print(f"Cross-val Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
        
        self.models['logistic_regression'] = lr_model
        
        # Model 2: Random Forest
        print("\n" + "="*60)
        print("TRAINING RANDOM FOREST")
        print("="*60)
        
        rf_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=50,
            random_state=42,
            n_jobs=-1
        )
        rf_model.fit(X_train, y_train)
        
        rf_pred = rf_model.predict(X_test)
        rf_prob = rf_model.predict_proba(X_test)[:, 1]
        
        print("\nRandom Forest Results:")
        print(f"Accuracy: {accuracy_score(y_test, rf_pred):.3f}")
        print(f"Precision: {precision_score(y_test, rf_pred):.3f}")
        print(f"Recall: {recall_score(y_test, rf_pred):.3f}")
        
        cv_scores = cross_val_score(rf_model, X_train, y_train, cv=5)
        print(f"Cross-val Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
        
        # Feature importance
        print("\nTop 5 Features:")
        importances = pd.DataFrame({
            'feature': self.feature_cols,
            'importance': rf_model.feature_importances_
        }).sort_values('importance', ascending=False)
        print(importances.head())
        
        self.models['random_forest'] = rf_model
        
        # Save test results
        return {
            'X_test': X_test,
            'y_test': y_test,
            'lr_pred': lr_pred,
            'lr_prob': lr_prob,
            'rf_pred': rf_pred,
            'rf_prob': rf_prob,
            'feature_importance': importances
        }
    
    def backtest_ml_strategy(self, df, model_name='random_forest', prob_threshold=0.6):
        """Backtest ML-based strategy"""
        
        print(f"\n{'='*60}")
        print(f"BACKTESTING ML STRATEGY: {model_name.upper()}")
        print(f"Probability Threshold: {prob_threshold}")
        print(f"{'='*60}")
        
        # Prepare data
        df_processed = self.calculate_technical_indicators(df)
        df_processed = self.create_target_variable(df_processed, forward_days=2)
        df_clean = df_processed.dropna().copy()
        
        # Get features
        X = df_clean[self.feature_cols]
        
        # Get model predictions
        model = self.models[model_name]
        predictions = model.predict_proba(X)[:, 1]
        
        df_clean['ml_prob'] = predictions
        df_clean['ml_signal'] = (predictions >= prob_threshold).astype(int)
        
        # Simulate trades
        trades = []
        
        for i in range(len(df_clean)):
            if df_clean.iloc[i]['ml_signal'] == 1:
                entry_cost = df_clean.iloc[i]['straddle_cost']
                future_spot = df_clean.iloc[i]['future_spot']
                current_spot = df_clean.iloc[i]['spot']
                
                # Calculate P&L
                abs_move = abs(future_spot - current_spot)
                pnl = abs_move - entry_cost
                
                trades.append({
                    'entry_time': df_clean.iloc[i]['datetime'],
                    'ml_prob': df_clean.iloc[i]['ml_prob'],
                    'entry_cost': entry_cost,
                    'spot_move': abs_move,
                    'pnl': pnl,
                    'result': 'WIN' if pnl > 0 else 'LOSS'
                })
        
        if len(trades) == 0:
            print("No trades generated!")
            return None
        
        trades_df = pd.DataFrame(trades)
        
        # Calculate metrics
        total_trades = len(trades_df)
        wins = len(trades_df[trades_df['result'] == 'WIN'])
        win_rate = (wins / total_trades) * 100
        total_pnl = trades_df['pnl'].sum()
        avg_pnl = trades_df['pnl'].mean()
        
        total_profit = trades_df[trades_df['result'] == 'WIN']['pnl'].sum()
        total_loss = abs(trades_df[trades_df['result'] == 'LOSS']['pnl'].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else 0
        
        sharpe = (avg_pnl / trades_df['pnl'].std()) if trades_df['pnl'].std() > 0 else 0
        
        # Results
        results = {
            'total_trades': total_trades,
            'winning_trades': wins,
            'losing_trades': total_trades - wins,
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(avg_pnl, 2),
            'profit_factor': round(profit_factor, 2),
            'sharpe_ratio': round(sharpe, 2),
            'avg_ml_prob': round(trades_df['ml_prob'].mean(), 3)
        }
        
        print(f"\nML Strategy Results:")
        print(f"Total Trades: {results['total_trades']}")
        print(f"Win Rate: {results['win_rate']}%")
        print(f"Total P&L: ₹{results['total_pnl']}")
        print(f"Profit Factor: {results['profit_factor']}")
        print(f"Sharpe Ratio: {results['sharpe_ratio']}")
        print(f"Avg ML Probability: {results['avg_ml_prob']}")
        
        return results, trades_df
    
    def save_models(self):
        """Save trained models"""
        for name, model in self.models.items():
            joblib.dump(model, f'{name}_model.pkl')
            print(f"✅ Saved {name}")
        
        # Save feature columns
        joblib.dump(self.feature_cols, 'feature_columns.pkl')
    
    def load_models(self):
        """Load trained models"""
        try:
            self.models['logistic_regression'] = joblib.load('logistic_regression_model.pkl')
            self.models['random_forest'] = joblib.load('random_forest_model.pkl')
            self.feature_cols = joblib.load('feature_columns.pkl')
            print("✅ Models loaded successfully")
        except:
            print("⚠️ Models not found. Train first!")


# Main execution
if __name__ == "__main__":
    
    print("="*60)
    print("ML-BASED VOLATILITY PREDICTION SYSTEM")
    print("Hackathon Project - NIFTY Straddle AI")
    print("="*60)
    
    # Load data
    print("\nLoading data...")
    straddle_df = pd.read_csv('straddle_data_prepared.csv')
    straddle_df['datetime'] = pd.to_datetime(straddle_df['datetime'])
    
    print(f"Data loaded: {len(straddle_df)} rows")
    print(f"Date range: {straddle_df['datetime'].min()} to {straddle_df['datetime'].max()}")
    
    # Initialize predictor
    predictor = VolatilityPredictor()
    
    # Train models
    test_results = predictor.train_models(straddle_df)
    
    # Backtest with Logistic Regression
    lr_results, lr_trades = predictor.backtest_ml_strategy(
        straddle_df, 
        model_name='logistic_regression',
        prob_threshold=0.6
    )
    
    # Backtest with Random Forest
    rf_results, rf_trades = predictor.backtest_ml_strategy(
        straddle_df,
        model_name='random_forest', 
        prob_threshold=0.6
    )
    
    # Save models
    predictor.save_models()
    
    # Save results for dashboard
    if lr_results:
        lr_results_df = pd.DataFrame([lr_results])
        lr_results_df.to_csv('ml_lr_performance_metrics.csv', index=False)
        lr_trades.to_csv('ml_lr_backtest_results.csv', index=False)
    
    if rf_results:
        rf_results_df = pd.DataFrame([rf_results])
        rf_results_df.to_csv('ml_rf_performance_metrics.csv', index=False)
        rf_trades.to_csv('ml_rf_backtest_results.csv', index=False)
    
    print("\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)
    
    print(f"\n{'Strategy':<25} {'Trades':<10} {'Win Rate':<12} {'P&L':<15}")
    print("-"*65)
    
    if lr_results:
        print(f"{'ML - Logistic Reg':<25} {lr_results['total_trades']:<10} "
              f"{lr_results['win_rate']}%{'':<7} ₹{lr_results['total_pnl']}")
    
    if rf_results:
        print(f"{'ML - Random Forest':<25} {rf_results['total_trades']:<10} "
              f"{rf_results['win_rate']}%{'':<7} ₹{rf_results['total_pnl']}")
    
    print("\n✅ ML models trained and saved!")
    print("✅ Results saved to CSV files")
