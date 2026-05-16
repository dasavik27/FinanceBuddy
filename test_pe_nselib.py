from nselib import capital_market
df = capital_market.market_watch_all_indices()
pe_val = df.loc[df['index'] == 'NIFTY SMALLCAP 250', 'pe']
print(pe_val)
