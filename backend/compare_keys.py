import csv

with open("data/portfolios.csv", newline="", encoding="utf-8-sig") as f:
    portfolio_keys = {row["portfolio_key"].strip() for row in csv.DictReader(f)}

with open("data/portfolio_returns.csv", newline="", encoding="utf-8-sig") as f:
    returns_keys = {row["portfolio_key"].strip() for row in csv.DictReader(f)}

only_in_returns = returns_keys - portfolio_keys
only_in_portfolios = portfolio_keys - returns_keys
matching = returns_keys & portfolio_keys

print(f"portfolios.csv has {len(portfolio_keys)} unique portfolio_key values")
print(f"portfolio_returns.csv has {len(returns_keys)} unique portfolio_key values")
print(f"{len(matching)} keys match between the two files")
print()
print(f"In portfolio_returns.csv but NOT in portfolios.csv ({len(only_in_returns)}):")
for k in sorted(only_in_returns)[:15]:
    print(" ", repr(k))
print()
print(f"In portfolios.csv but NOT in portfolio_returns.csv ({len(only_in_portfolios)}):")
for k in sorted(only_in_portfolios)[:15]:
    print(" ", repr(k))