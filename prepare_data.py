import pandas as pd
import numpy as np

print("Loading data...")
df = pd.read_csv('NIFTY_part_1.csv')
print(f"Loaded {len(df)} rows")

# Clean date format (remove Excel formatting)
df['date'] = df['date'].str.replace('=\"', '').str.replace('\"', '')
df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%d-%m-%y %H:%M:%S')

print("Filtering ATM options...")
df_atm = df[df['strike_offset'] == 'ATM'].copy()

# Separate calls and puts
calls = df_atm[df_atm['option_type'] == 'CALL'].copy()
puts = df_atm[df_atm['option_type'] == 'PUT'].copy()

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
straddle['total_volume'] = straddle['volume_call'] + straddle['volume_put']
straddle['total_oi'] = straddle['oi_call'] + straddle['oi_put']

# Clean
straddle = straddle[
    (straddle['straddle_cost'] > 0) &
    (straddle['avg_iv'] > 0) &
    (straddle['avg_iv'] < 100)
]

print(f"Created {len(straddle)} straddle pairs")

# Save
straddle.to_csv('straddle_data_prepared.csv', index=False)
print("✅ Saved to straddle_data_prepared.csv")
