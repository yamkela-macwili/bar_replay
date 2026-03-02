"""Generate sample EURUSD H1 data for development."""
import pandas as pd
import numpy as np
import os

np.random.seed(42)
n = 500
base_price = 1.08500
dates = pd.date_range("2024-01-02 00:00", periods=n, freq="h")

prices = [base_price]
for i in range(1, n):
    change = np.random.normal(0, 0.0008)
    trend = np.sin(i / 50) * 0.00005
    prices.append(prices[-1] + change + trend)

rows = []
for i, dt in enumerate(dates):
    p = prices[i]
    h = p + abs(np.random.normal(0, 0.0005))
    l = p - abs(np.random.normal(0, 0.0005))
    o = p + np.random.normal(0, 0.0003)
    c = p + np.random.normal(0, 0.0003)
    o = max(min(o, h), l)
    c = max(min(c, h), l)
    v = int(np.random.uniform(100, 5000))
    rows.append({
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "open": round(o, 5),
        "high": round(h, 5),
        "low": round(l, 5),
        "close": round(c, 5),
        "volume": v
    })

os.makedirs("data/sample", exist_ok=True)
df = pd.DataFrame(rows)
df.to_csv("data/sample/EURUSD_H1.csv", index=False)
print(f"Generated {len(df)} rows")
print(df.head())
