# AKShare data source implementation for FinancialDataSource interface
import pandas as pd
import akshare as ak
from typing import List, Optional
import logging
from .data_source_interface import FinancialDataSource, DataSourceError, NoDataFoundError

logger = logging.getLogger(__name__)

# Map baostock-style codes (sh.600000, sz.000001) to akshare formats
def _code_to_akshare(code: str) -> str:
    """Convert 'sh.600000' -> 'sh600000', 'sz.000001' -> 'sz000001'"""
    return code.replace('.', '')

# Map akshare columns to baostock-like names for compatibility
def _map_k_columns(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Map akshare OHLCV columns to baostock-compatible names"""
    col_map = {
        '日期': 'date',
        '股票代码': 'code',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'amount',
        '涨跌幅': 'pctChg',
        '换手率': 'turn',
    }
    df = df.rename(columns=col_map)
    # Add code column from the input code
    df['code'] = code
    # Ensure date is string
    if 'date' in df.columns:
        df['date'] = df['date'].astype(str)
    return df


class AkshareDataSource(FinancialDataSource):
    """AKShare implementation of FinancialDataSource"""

    def get_historical_k_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjust_flag: str = "3",
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        logger.info(f"Fetching K-data for {code} ({start_date} to {end_date})")
        try:
            symbol = _code_to_akshare(code)
            # akshare expects YYYYMMDD format
            start_fmt = start_date.replace('-', '')
            end_fmt = end_date.replace('-', '')

            df = ak.stock_zh_a_daily(symbol=symbol, start_date=start_fmt, end_date=end_fmt)
            df = _map_k_columns(df, code)

            if df.empty:
                raise NoDataFoundError(f"No K-data found for {code}")
            logger.info(f"Retrieved {len(df)} records for {code}")
            return df
        except NoDataFoundError:
            raise
        except Exception as e:
            logger.exception(f"Error fetching K-data for {code}: {e}")
            raise DataSourceError(f"AKShare K-data error: {e}")

    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        logger.info(f"Fetching basic info for {code}")
        try:
            symbol = _code_to_akshare(code)
            # Use financial report sina as a proxy for basic info
            df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")
            # Extract basic info from first row
            if df.empty:
                raise NoDataFoundError(f"No basic info found for {code}")
            # Return a simple info dataframe
            result = pd.DataFrame({
                'code': [code],
                'code_name': [df.columns[0] if not df.empty else code],
            })
            logger.info(f"Retrieved basic info for {code}")
            return result
        except NoDataFoundError:
            raise
        except Exception as e:
            logger.exception(f"Error fetching basic info for {code}: {e}")
            raise DataSourceError(f"AKShare basic info error: {e}")

    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        # Not available via AKShare directly, return placeholder
        raise NoDataFoundError("Trade dates not available via AKShare")

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("All stock list not available via AKShare")

    def get_deposit_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("Deposit rate not available via AKShare")

    def get_loan_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("Loan rate not available via AKShare")

    def get_required_reserve_ratio_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None, year_type: str = '0') -> pd.DataFrame:
        raise NoDataFoundError("Reserve ratio not available via AKShare")

    def get_money_supply_data_month(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        try:
            df = ak.macro_china_money_supply()
            if df.empty:
                raise NoDataFoundError("No money supply data")
            logger.info(f"Retrieved {len(df)} money supply records")
            return df
        except Exception as e:
            logger.exception(f"Error fetching money supply: {e}")
            raise DataSourceError(f"AKShare money supply error: {e}")

    def get_money_supply_data_year(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return self.get_money_supply_data_month(start_date, end_date)

    # ---- Financial data ----
    def _get_financial_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        symbol = _code_to_akshare(code)
        try:
            df = ak.stock_financial_abstract(symbol=symbol)
            if df is None or df.empty:
                raise NoDataFoundError(f"No financial data for {code}")
            return df
        except Exception as e:
            raise DataSourceError(f"AKShare financial data error: {e}")

    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return self._get_financial_data(code, year, quarter)

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return self._get_financial_data(code, year, quarter)

    def get_growth_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return self._get_financial_data(code, year, quarter)

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return self._get_financial_data(code, year, quarter)

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return self._get_financial_data(code, year, quarter)

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return self._get_financial_data(code, year, quarter)

    # ---- Index constituent data ----
    def get_sz50_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("SZ50 constituents not available via AKShare")

    def get_hs300_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("HS300 constituents not available via AKShare")

    def get_zz500_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("ZZ500 constituents not available via AKShare")

    # ---- Generic data ----
    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        raise NoDataFoundError("Dividend data not available via AKShare")

    def get_adjust_factor_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NoDataFoundError("Adjust factor not available via AKShare")

    def get_performance_express_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self._get_financial_data(code, start_date[:4], int(start_date[5:7]) // 3 + 1)

    def get_forecast_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self._get_financial_data(code, start_date[:4], int(start_date[5:7]) // 3 + 1)

    def get_stock_industry(self, code: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        raise NoDataFoundError("Stock industry not available via AKShare")
