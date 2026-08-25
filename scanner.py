import yfinance as yf
import pandas as pd
import numpy as np
import gspread
import os
import json

from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials


# ============================================================
# GOOGLE SHEETS SETTINGS
# ============================================================

SPREADSHEET_ID = "1Pyo8Lhivc-Kud3Xt7bnObUedV6DLiHpeRnJVkQe8Ivs"

WORKSHEET_NAME = "NIFTY 500 SWING"
HISTORY_WORKSHEET_NAME = "Scanner History"


# ============================================================
# SCAN DATE - INDIA TIME
# ============================================================

scan_date = datetime.now(
    ZoneInfo("Asia/Kolkata")
).strftime("%d-%m-%Y")

print("Scan Date:", scan_date)


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

creds_json = os.environ.get("GCP_CREDENTIALS")

if not creds_json:
    raise Exception("GCP_CREDENTIALS secret not found")

service_account_info = json.loads(creds_json)

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    service_account_info,
    scopes=scopes
)

gc = gspread.authorize(credentials)

spreadsheet = gc.open_by_key(SPREADSHEET_ID)

worksheet = spreadsheet.worksheet(
    WORKSHEET_NAME
)


# ============================================================
# CREATE / OPEN SCANNER HISTORY SHEET
# ============================================================

try:

    history_worksheet = spreadsheet.worksheet(
        HISTORY_WORKSHEET_NAME
    )

    print(
        "Scanner History sheet found."
    )

except gspread.WorksheetNotFound:

    history_worksheet = spreadsheet.add_worksheet(
        title=HISTORY_WORKSHEET_NAME,
        rows=1000,
        cols=20
    )

    print(
        "Scanner History sheet created."
    )


# ============================================================
# LOAD NIFTY 500 STOCK LIST FROM CSV
# ============================================================

nifty500 = pd.read_csv(
    "ind_nifty500list.csv"
)

stocks = (
    nifty500["Symbol"]
    .dropna()
    .astype(str)
    .str.strip()
    .apply(lambda x: x + ".NS")
    .tolist()
)

print(
    "Total Stocks:",
    len(stocks)
)


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(
        period
    ).mean()

    avg_loss = loss.rolling(
        period
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    return 100 - (
        100 / (1 + rs)
    )


# ============================================================
# MACD
# ============================================================

def calculate_macd(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    return macd, signal


# ============================================================
# ADX
# ============================================================

def calculate_adx(
    data,
    period=14
):

    high = data["High"]
    low = data["Low"]
    close = data["Close"]

    if isinstance(
        high,
        pd.DataFrame
    ):
        high = high.iloc[:, 0]

    if isinstance(
        low,
        pd.DataFrame
    ):
        low = low.iloc[:, 0]

    if isinstance(
        close,
        pd.DataFrame
    ):
        close = close.iloc[:, 0]

    plus_dm = high.diff()
    minus_dm = low.diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm)
        & (plus_dm > 0),
        0
    )

    minus_dm = minus_dm.where(
        (minus_dm > plus_dm)
        & (minus_dm > 0),
        0
    )

    tr1 = high - low

    tr2 = abs(
        high - close.shift()
    )

    tr3 = abs(
        low - close.shift()
    )

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = tr.rolling(
        period
    ).mean()

    plus_di = (
        100
        * plus_dm.rolling(
            period
        ).mean()
        / atr.replace(
            0,
            np.nan
        )
    )

    minus_di = (
        100
        * minus_dm.rolling(
            period
        ).mean()
        / atr.replace(
            0,
            np.nan
        )
    )

    denominator = (
        plus_di + minus_di
    )

    dx = (
        abs(
            plus_di - minus_di
        )
        / denominator.replace(
            0,
            np.nan
        )
    ) * 100

    adx = dx.rolling(
        period
    ).mean()

    return adx


# ============================================================
# STOCK SCANNER
# ============================================================

results = []


for symbol in stocks:

    try:

        print(
            "Scanning:",
            symbol
        )

        data = yf.download(
            symbol,
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if data.empty:

            print(
                "No data:",
                symbol
            )

            continue


        # ====================================================
        # FIX YFINANCE MULTIINDEX
        # ====================================================

        if isinstance(
            data.columns,
            pd.MultiIndex
        ):

            data.columns = (
                data.columns
                .get_level_values(0)
            )

        data = data.dropna()


        # ====================================================
        # REQUIRED COLUMNS
        # ====================================================

        required_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        if not all(
            column in data.columns
            for column in required_columns
        ):

            print(
                "Missing columns:",
                symbol
            )

            continue


        # ====================================================
        # PRICE SERIES
        # ====================================================

        close = data["Close"]

        if isinstance(
            close,
            pd.DataFrame
        ):
            close = close.iloc[:, 0]

        high = data["High"]

        if isinstance(
            high,
            pd.DataFrame
        ):
            high = high.iloc[:, 0]

        volume = data["Volume"]

        if isinstance(
            volume,
            pd.DataFrame
        ):
            volume = volume.iloc[:, 0]


        # ====================================================
        # DMA
        # ====================================================

        data["DMA20"] = (
            close.rolling(20).mean()
        )

        data["DMA50"] = (
            close.rolling(50).mean()
        )

        data["DMA200"] = (
            close.rolling(200).mean()
        )


        # ====================================================
        # RSI
        # ====================================================

        data["RSI"] = calculate_rsi(
            close
        )


        # ====================================================
        # MACD
        # ====================================================

        macd, macd_signal = (
            calculate_macd(close)
        )

        data["MACD"] = macd

        data["MACD_SIGNAL"] = (
            macd_signal
        )


        # ====================================================
        # ADX
        # ====================================================

        data["ADX"] = calculate_adx(
            data
        )


        # ====================================================
        # VOLUME BREAKOUT
        # ====================================================

        data["AVG_VOLUME_20"] = (
            volume.rolling(20).mean()
        )

        data["VOLUME_BREAKOUT"] = (
            volume
            > data["AVG_VOLUME_20"] * 1.5
        )


        # ====================================================
        # 20 DAY HIGH BREAKOUT
        #
        # Previous 20 trading days high
        # Today's high is NOT included.
        # ====================================================

        data["BREAKOUT_PRICE"] = (
            high.rolling(20)
            .max()
            .shift(1)
        )


        # ====================================================
        # BREAKOUT PERCENTAGE
        # ====================================================

        data["BREAKOUT_PERCENT"] = (
            (
                close
                - data["BREAKOUT_PRICE"]
            )
            / data["BREAKOUT_PRICE"]
        ) * 100


        # ====================================================
        # REMOVE NaN
        # ====================================================

        data = data.dropna()

        if data.empty:

            print(
                "Not enough data:",
                symbol
            )

            continue


        # ====================================================
        # LAST DAY DATA
        # ====================================================

        last = data.iloc[-1]

        price = float(
            last["Close"]
        )

        dma20 = float(
            last["DMA20"]
        )

        dma50 = float(
            last["DMA50"]
        )

        dma200 = float(
            last["DMA200"]
        )

        rsi = float(
            last["RSI"]
        )

        macd_value = float(
            last["MACD"]
        )

        macd_signal_value = float(
            last["MACD_SIGNAL"]
        )

        adx = float(
            last["ADX"]
        )

        breakout_price = float(
            last["BREAKOUT_PRICE"]
        )

        breakout_percent = float(
            last["BREAKOUT_PERCENT"]
        )

        volume_breakout = bool(
            last["VOLUME_BREAKOUT"]
        )


        # ====================================================
        # FRESH BREAKOUT
        # ====================================================

        fresh_breakout = (
            price > breakout_price
        )


        # ====================================================
        # BREAKOUT <= 5%
        # ====================================================

        breakout_within_5_percent = (
            breakout_percent <= 5
        )


        # ====================================================
        # BUY CONDITIONS
        # ====================================================

        buy_signal = (

            price > dma20

            and price > dma50

            and price > dma200

            and rsi > 50

            and macd_value > macd_signal_value

            and adx > 20

            and volume_breakout

            and fresh_breakout

            and breakout_within_5_percent

        )


        # ====================================================
        # RESULT
        # ====================================================

        results.append({

            "Scan Date":
                scan_date,

            "Stock":
                symbol.replace(
                    ".NS",
                    ""
                ),

            "Price":
                round(
                    price,
                    2
                ),

            "DMA20":
                round(
                    dma20,
                    2
                ),

            "DMA50":
                round(
                    dma50,
                    2
                ),

            "DMA200":
                round(
                    dma200,
                    2
                ),

            "RSI":
                round(
                    rsi,
                    2
                ),

            "MACD":
                round(
                    macd_value,
                    2
                ),

            "MACD Signal":
                round(
                    macd_signal_value,
                    2
                ),

            "ADX":
                round(
                    adx,
                    2
                ),

            "Breakout Price":
                round(
                    breakout_price,
                    2
                ),

            "Breakout %":
                round(
                    breakout_percent,
                    2
                ),

            "Volume Breakout":
                "YES"
                if volume_breakout
                else "NO",

            "Fresh Breakout":
                "YES"
                if fresh_breakout
                else "NO",

            "BUY Signal":
                "BUY"
                if buy_signal
                else ""

        })


    except Exception as e:

        print(
            "Error:",
            symbol,
            e
        )


# ============================================================
# RESULT DATAFRAME
# ============================================================

result_df = pd.DataFrame(
    results
)


# ============================================================
# SORT BUY STOCKS TO TOP
# ============================================================

if not result_df.empty:

    result_df["BUY_SORT"] = (
        result_df["BUY Signal"]
        .apply(
            lambda x:
            0 if x == "BUY" else 1
        )
    )

    result_df = (
        result_df
        .sort_values(
            by=[
                "BUY_SORT",
                "Breakout %"
            ],
            ascending=[
                True,
                True
            ]
        )
        .drop(
            columns=[
                "BUY_SORT"
            ]
        )
    )


# ============================================================
# UPLOAD TO GOOGLE SHEETS
# ============================================================

print("")

print(
    "======================================"
)

print(
    "Uploading results to Google Sheets..."
)

print(
    "======================================"
)


if not result_df.empty:


    # ========================================================
    # 1. MAIN SCANNER SHEET
    # ========================================================

    worksheet.clear()

    main_data = (
        [
            result_df.columns.values.tolist()
        ]
        +
        result_df.values.tolist()
    )

    worksheet.update(
        main_data
    )

    print(
        "NIFTY 500 SWING updated successfully!"
    )


    # ========================================================
    # 2. SCANNER HISTORY
    # ONLY BUY STOCKS
    # NEWEST DATA ON TOP
    # ========================================================

    history_buy_df = result_df[
        result_df["BUY Signal"] == "BUY"
    ].copy()


    # ========================================================
    # CHECK IF BUY STOCKS EXIST
    # ========================================================

    if not history_buy_df.empty:

        history_headers = (
            history_buy_df
            .columns
            .values
            .tolist()
        )

        history_rows = (
            history_buy_df
            .values
            .tolist()
        )


        # ====================================================
        # CHECK / CREATE HEADER
        # ====================================================

        existing_history = (
            history_worksheet
            .get_all_values()
        )


        if not existing_history:

            history_worksheet.update(
                [
                    history_headers
                ]
            )

            print(
                "Scanner History header created."
            )

        else:

            history_worksheet.update(
                "A1",
                [
                    history_headers
                ]
            )


        # ====================================================
        # INSERT NEW BUY DATA AT ROW 2
        # ====================================================

        history_worksheet.insert_rows(
            history_rows,
            row=2,
            value_input_option="USER_ENTERED"
        )

        print(
            "Scanner History updated successfully!"
        )

        print(
            "Only BUY stocks saved in history."
        )


    else:

        print(
            "No BUY stocks found today."
        )


else:

    print(
        "No scanner results found."
    )


# ============================================================
# FINAL RESULT
# ============================================================

print("")

print(
    "======================================"
)

print(
    "STOCK SCANNER RESULT"
)

print(
    "======================================"
)

print(
    result_df.to_string(
        index=False
    )
)
