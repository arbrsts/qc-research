import alphalens as al
import pandas as pd
from QuantConnect.Data.UniverseSelection import *
import pytz
import numpy as np

class FactorAnalysis:
    def __init__(self, qb, symbols, lookback_period=360, rsi_period=30, asset_class='forex'):
        self.qb = qb
        self.symbols = symbols
        self.lookback_period = lookback_period
        self.rsi_period = rsi_period
        self.asset_class = asset_class
        self.history = self.qb.History([qb.AddForex(symbol).Symbol for symbol in symbols], lookback_period, Resolution.Daily)
        self.factors = self._calculate_rsi_factors()

    def _symbol_to_str(self, symbol):
        return str(symbol).split()[0]

    def _calculate_rsi_factors(self):
        all_rsidf = []
        
        for symbol in self.symbols:
            rsi = RelativeStrengthIndex(self.rsi_period)
            rsidf = self.qb.Indicator(rsi, symbol, self.lookback_period, Resolution.Daily)
            rsidf['date'] = rsidf.index
            rsidf['asset'] = self._symbol_to_str(symbol)
            rsidf.reset_index(drop=True, inplace=True)
            rsidf.set_index(['date', 'asset'], inplace=True)
            all_rsidf.append(rsidf)
        
        combined_rsidf = pd.concat(all_rsidf)
        combined_rsidf.columns = ['averagegain', 'averageloss', 'current']
        combined_rsidf_reset = combined_rsidf.reset_index()
        combined_rsidf_reset['date'] = pd.to_datetime(combined_rsidf_reset['date']).dt.tz_localize('UTC').dt.normalize()  # Convert to date and localize
        
        mean_rsi = combined_rsidf_reset['current'].mean()
        std_rsi = combined_rsidf_reset['current'].std()

        def transform_rsi(value):
            if abs(value - mean_rsi) <= std_rsi:
                return value
            elif value > mean_rsi + std_rsi:
                return 2 * (mean_rsi + std_rsi) - value
            elif value < mean_rsi - std_rsi:
                return 2 * (mean_rsi - std_rsi) - value

        combined_rsidf_reset['current'] = combined_rsidf_reset['current'].apply(transform_rsi)

        melted = pd.melt(combined_rsidf_reset, id_vars=['date', 'asset'], var_name='metric', value_name='value')
        pivot_df = melted.pivot_table(index=['date', 'asset'], columns='metric', values='value')
        pivot_df.columns.name = None
        pivot_df = pivot_df[['current']]
        pivot_df = pivot_df.reset_index().set_index(['date', 'asset'])
        pivot_df.sort_index(inplace=True)
        pivot_df = pivot_df[~pivot_df.index.duplicated(keep='first')]  # Remove duplicates
        return pivot_df

    def get_factors(self):
        return self.factors

    def get_prices(self):
        df = pd.DataFrame(self.history)
        df.reset_index(inplace=True)
        df['time'] = pd.to_datetime(df['time']).dt.tz_localize('UTC').dt.normalize()  # Convert to date and localize
        df['symbol'] = df['symbol'].apply(self._symbol_to_str)
        df_wide = df.pivot(index='time', columns='symbol', values='close')
        df_wide = df_wide[~df_wide.index.duplicated(keep='first')]  # Remove duplicates
        prices = df_wide.loc[self.factors.index.get_level_values('date').unique()]
        return prices

    def get_clean_factor_and_forward_returns(self, max_loss=0.10, quantiles=5):
        prices = self.get_prices()
        factor_data = al.utils.get_clean_factor_and_forward_returns(self.factors, prices, max_loss=max_loss, quantiles=quantiles)
        return factor_data

# Example usage
qb = QuantBook()
symbols = ["EURUSD", "USDJPY", "GBPUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]
fa = FactorAnalysis(qb, symbols, asset_class='forex')

factors = fa.get_factors()
prices = fa.get_prices()
print(factors.head())
print(prices.head())
factor_data = fa.get_clean_factor_and_forward_returns()

print(factor_data.head())

al.tears.create_returns_tear_sheet(factor_data,
                                   long_short=True,
                                   group_neutral=False,
                                   by_group=False)
