@"
# NIFTY Options Trading Strategies

## Overview
Backtesting system testing 3 straddle strategies on 18 months of real NIFTY options data.

## Strategies Tested

### 1. IV Scalping
- **Approach:** Buy straddle when implied volatility is low (≤30th percentile)
- **Exit:** 20% profit, 15% stop loss, or 3 days
- **Results:** 210 trades, 4.8% win rate, -₹15,243 P&L ❌

### 2. Gamma Scalping ⭐ WINNER
- **Approach:** Buy high-gamma straddles and hedge continuously
- **Exit:** 25% profit, 15% stop loss, or 3 days
- **Results:** 8 trades, 25% win rate, +₹750 P&L ✅

### 3. Hybrid
- **Approach:** Combines both (requires low IV AND high gamma)
- **Exit:** 25% profit, 15% stop loss, or 3 days
- **Results:** 0 trades (conditions too strict) ⚠️

## Results Summary

| Strategy | Trades | Win Rate | Net P&L | Status |
|----------|--------|----------|---------|--------|
| IV Scalping | 210 | 4.8% | -₹15,243 | ❌ Failed |
| Gamma Scalping | 8 | 25.0% | +₹750 | ✅ Winner |
| Hybrid | 0 | 0% | ₹0 | ⚠️ Too selective |

## Key Insights

**Why IV Scalping Failed:**
- Low volatility period (Aug 2024 - Feb 2026)
- Overtraded (210 entries)
- Stop loss hit repeatedly
- Theta decay crushed buyers

**Why Gamma Scalping Won:**
- Very selective (only 8 trades)
- Active delta hedging protected capital
- Quality over quantity approach
- Disciplined execution

**Why Hybrid Had Zero Trades:**
- Required BOTH low IV AND high gamma simultaneously
- These conditions rarely align in real markets
- Demonstrates over-optimization risk
- Sometimes simpler is better

## Data

- **Period:** August 26, 2024 - February 16, 2026 (540 days)
- **Data Points:** 31,183 straddle pairs
- **Frequency:** 5-minute intervals
- **Instrument:** NIFTY ATM Call + Put options
- **Costs:** Full transaction costs included (₹50/trade)

## Technical Stack

- **Backend:** FastAPI + Python
- **Data Processing:** Pandas, NumPy
- **Deployment:** Render
- **Frontend:** React (Lovable)

## Installation

\`\`\`bash
# Clone repository
git clone https://github.com/rishitmodh12/nifty-options-strategies.git
cd nifty-options-strategies

# Install dependencies
pip install -r requirements.txt

# Run backend
python api_backend.py
\`\`\`

## API Endpoints

- \`GET /\` - System info
- \`GET /strategy/iv_scalping\` - IV Scalping data
- \`GET /strategy/gamma_scalping\` - Gamma Scalping data
- \`GET /strategy/hybrid\` - Hybrid data
- \`GET /compare\` - Compare all strategies

## Live Demo

- **Backend API:** https://nifty-options-strategies.onrender.com
- **Dashboard:** https://preview--nifty-shraddle-ai.lovable.app

## Project Structure

\`\`\`
nifty-options-strategies/
├── api_backend.py              # FastAPI backend
├── requirements.txt            # Python dependencies
├── NIFTY_part_1.csv           # Raw options data (part 1)
├── NIFTY_part_2.csv           # Raw options data (part 2)
├── straddle_data_prepared.csv # Processed straddle data
├── iv_performance.csv         # IV strategy results
├── iv_trades.csv              # IV strategy trades
├── gamma_performance.csv      # Gamma strategy results
├── gamma_trades.csv           # Gamma strategy trades
├── hybrid_performance.csv     # Hybrid strategy results
├── hybrid_trades.csv          # Hybrid strategy trades
└── README.md                  # This file
\`\`\`

## Key Learnings

1. **Selectivity Matters:** 8 disciplined trades beat 210 random entries
2. **Market Regime:** Low volatility favors sellers over buyers
3. **Simplicity Wins:** Simple gamma approach beat complex hybrid
4. **Over-optimization:** Perfect conditions (hybrid) never occurred
5. **Real Costs:** Transaction costs make high-frequency trading unprofitable

## Future Enhancements

- Add short straddle (seller) strategy
- Implement machine learning for entry timing
- Real-time signal generation
- Risk management dashboard
- Alert system for trade signals

## Author

Rishit Modi
- GitHub: [@rishitmodh12](https://github.com/rishitmodh12)

## License

MIT License - see LICENSE file for details

---

**Note:** This is a research and educational project. Past performance does not guarantee future results. Trading options involves substantial risk of loss.
"@