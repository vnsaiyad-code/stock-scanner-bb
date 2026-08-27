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

SPREADSHEET_ID = "1s8LybmXezn-xTqDgiKTBWGwkiK62O3qghuviUokeUKs"

WORKSHEET_NAME = "NIFTY 500 SWING BB"
HISTORY_WORKSHEET_NAME = "Scanner History BB"


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
# CREATE / OPEN SCANNER HISTORY BB
# ============================================================

try:

    history_worksheet = spreadsheet.worksheet(
        HISTORY_WORKSHEET_NAME
    )

    print("Scanner History BB sheet found.")

except gspread.WorksheetNotFound:

    history_worksheet = spreadsheet.add_worksheet(
        title=HISTORY_WORKSHEET_NAME,
        rows=2000,
        cols=30
    )

    print("Scanner History BB sheet created.")


# ============================================================
# LOAD NIFTY 500 STOCK LIST
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

print("Total Stocks:", len(stocks))


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

def calculate_adx(data, period=14):

    high = data["High"]
    low = data["Low"]
    close = data["Close"]

    if isinstance(high, pd.DataFrame):
        high = high.iloc[:, 0]

    if isinstance(low, pd.DataFrame):
        low = low.iloc[:, 0]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    high = pd.to_numeric(
        high,
        errors="coerce"
    )

    low = pd.to_numeric(
        low,
        errors="coerce"
    )

    close = pd.to_numeric(
        close,
        errors="coerce"
    )

    up_move = high.diff()

    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move) &
            (up_move > 0),
            up_move,
            0.0
        ),
        index=data.index
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move) &
            (down_move > 0),
            down_move,
            0.0
        ),
        index=data.index
    )

    tr1 = high - low

    tr2 = (
        high - close.shift(1)
    ).abs()

    tr3 = (
        low - close.shift(1)
    ).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = tr.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_dm_smoothed = plus_dm.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    minus_dm_smoothed = minus_dm.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_di = (
        100
        * plus_dm_smoothed
        / atr.replace(0, np.nan)
    )

    minus_di = (
        100
        * minus_dm_smoothed
        / atr.replace(0, np.nan)
    )

    di_sum = plus_di + minus_di

    dx = (
        100
        * (plus_di - minus_di).abs()
        / di_sum.replace(0, np.nan)
    )

    adx = dx.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return adx


# ============================================================
# STOCK SCANNER
# ============================================================

results = []


for symbol in stocks:

    try:

        print("Scanning:", symbol)

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

        high = data["High"]

        volume = data["Volume"]

        if isinstance(
            close,
            pd.DataFrame
        ):
            close = close.iloc[:, 0]

        if isinstance(
            high,
            pd.DataFrame
        ):
            high = high.iloc[:, 0]

        if isinstance(
            volume,
            pd.DataFrame
        ):
            volume = volume.iloc[:, 0]


        close = pd.to_numeric(
            close,
            errors="coerce"
        )

        high = pd.to_numeric(
            high,
            errors="coerce"
        )

        volume = pd.to_numeric(
            volume,
            errors="coerce"
        )


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
        # VOLUME
        #
        # Previous 20 completed days
        # Today's volume excluded.
        # ====================================================

        data["AVG_VOLUME_20"] = (
            volume
            .rolling(20)
            .mean()
            .shift(1)
        )

        data["VOLUME_RATIO"] = (
            volume
            / data["AVG_VOLUME_20"]
        )

        data["VOLUME_BREAKOUT"] = (
            data["VOLUME_RATIO"] >= 1.5
        )


        # ====================================================
        # 20 DAY HIGH BREAKOUT
        #
        # Previous 20 completed days only.
        # ====================================================

        data["BREAKOUT_PRICE"] = (
            high
            .rolling(20)
            .max()
            .shift(1)
        )


        # ====================================================
        # BREAKOUT PERCENT
        # ====================================================

        data["BREAKOUT_PERCENT"] = (

            (
                close
                - data["BREAKOUT_PRICE"]
            )

            / data["BREAKOUT_PRICE"]

        ) * 100


        # ====================================================
        # BOLLINGER BANDS
        # ====================================================

        data["BB_MIDDLE"] = (
            close.rolling(20).mean()
        )

        data["BB_STD"] = (
            close.rolling(20).std()
        )

        data["BB_UPPER"] = (
            data["BB_MIDDLE"]
            + (
                data["BB_STD"] * 2
            )
        )

        data["BB_LOWER"] = (
            data["BB_MIDDLE"]
            - (
                data["BB_STD"] * 2
            )
        )


        # ====================================================
        # REMOVE NaN
        # ====================================================

        data = data.dropna()

        if len(data) < 2:

            print(
                "Not enough data:",
                symbol
            )

            continue


        # ====================================================
        # LAST DAY
        # ====================================================

        last = data.iloc[-1]

        previous = data.iloc[-2]


        # ====================================================
        # VALUES
        # ====================================================

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

        volume_ratio = float(
            last["VOLUME_RATIO"]
        )

        bb_middle = float(
            last["BB_MIDDLE"]
        )

        bb_upper = float(
            last["BB_UPPER"]
        )

        bb_lower = float(
            last["BB_LOWER"]
        )


        # ====================================================
        # CORE CONDITIONS
        # ====================================================

        price_above_dma20 = (
            price > dma20
        )

        price_above_dma50 = (
            price > dma50
        )

        price_above_dma200 = (
            price > dma200
        )


        # ====================================================
        # DMA STRUCTURE
        #
        # Strong bullish alignment.
        # ====================================================

        bullish_dma_structure = (
            dma20 > dma50
            and dma50 > dma200
        )


        # ====================================================
        # RSI
        #
        # Healthy bullish momentum.
        # Avoid extremely overbought entries.
        # ====================================================

        rsi_bullish = (
            52 <= rsi <= 70
        )


        # ====================================================
        # MACD
        # ====================================================

        macd_bullish = (
            macd_value
            > macd_signal_value
        )


        # ====================================================
        # ADX
        #
        # 20+ = trend exists
        # 25+ = stronger trend
        # ====================================================

        adx_good = (
            adx >= 20
        )

        adx_strong = (
            adx >= 25
        )


        # ====================================================
        # VOLUME
        # ====================================================

        volume_good = (
            volume_ratio >= 1.5
        )

        volume_strong = (
            volume_ratio >= 2.0
        )


        # ====================================================
        # FRESH 20 DAY BREAKOUT
        # ====================================================

        fresh_breakout = (
            price > breakout_price
        )


        # ====================================================
        # BREAKOUT RANGE
        #
        # Must be between 0% and 5%.
        # ====================================================

        breakout_within_5_percent = (
            0 <= breakout_percent <= 5
        )


        # ====================================================
        # BOLLINGER BAND
        #
        # BB breakout is confirmation,
        # NOT mandatory.
        # ====================================================

        previous_close = float(
            previous["Close"]
        )

        previous_bb_upper = float(
            previous["BB_UPPER"]
        )

        bb_breakout = (
            price > bb_upper
            and previous_close
            <= previous_bb_upper
        )


        # ====================================================
        # BB POSITION
        #
        # Even if fresh BB breakout is absent,
        # price near/above upper band gets credit.
        # ====================================================

        bb_position_good = (
            price >= bb_middle
        )


        # ====================================================
        # QUALITY SCORE
        #
        # Maximum = 12
        # ====================================================

        score = 0


        # Trend - 4 points
        if price_above_dma20:
            score += 1

        if price_above_dma50:
            score += 1

        if price_above_dma200:
            score += 1

        if bullish_dma_structure:
            score += 1


        # Momentum - 2 points
        if rsi_bullish:
            score += 1

        if macd_bullish:
            score += 1


        # Trend strength - 1 point
        if adx_good:
            score += 1


        # Volume - 1 point
        if volume_good:
            score += 1


        # Breakout - 2 points
        if fresh_breakout:
            score += 1

        if breakout_within_5_percent:
            score += 1


        # Bollinger - 1 point
        if bb_breakout:
            score += 1


        # Additional BB position - 1 point
        if bb_position_good:
            score += 1


        # ====================================================
        # STRONG BUY LOGIC
        #
        # Mandatory:
        # 1. Price above DMA20/50/200
        # 2. Bullish DMA structure
        # 3. Fresh 20-day breakout
        # 4. Breakout 0-5%
        #
        # Plus quality score >= 9
        #
        # OR exceptionally strong setup:
        # score >= 10 with all major trend conditions.
        # ====================================================

        mandatory_core = (

            price_above_dma20

            and price_above_dma50

            and price_above_dma200

            and bullish_dma_structure

            and fresh_breakout

            and breakout_within_5_percent

        )


        buy_signal = (

            mandatory_core

            and score >= 9

        )


        # ====================================================
        # SETUP STRENGTH
        # ====================================================

        if score >= 11:

            setup_strength = "VERY STRONG"

        elif score >= 9:

            setup_strength = "STRONG"

        elif score >= 7:

            setup_strength = "GOOD"

        elif score >= 5:

            setup_strength = "WATCH"

        else:

            setup_strength = "WEAK"


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

            "Volume Ratio":
                round(
                    volume_ratio,
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

            "BB Middle":
                round(
                    bb_middle,
                    2
                ),

            "BB Upper":
                round(
                    bb_upper,
                    2
                ),

            "BB Lower":
                round(
                    bb_lower,
                    2
                ),

            "BB Breakout":
                "YES"
                if bb_breakout
                else "NO",

            "Volume Breakout":
                "YES"
                if volume_good
                else "NO",

            "Fresh Breakout":
                "YES"
                if fresh_breakout
                else "NO",

            "Score":
                score,

            "Setup Strength":
                setup_strength,

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
# SORT
#
# BUY first
# Then highest score
# Then lowest breakout %
# ============================================================

if not result_df.empty:

    result_df["BUY_SORT"] = (
        result_df["BUY Signal"]
        .apply(
            lambda x:
            0 if x == "BUY"
            else 1
        )
    )

    result_df = (
        result_df
        .sort_values(
            by=[
                "BUY_SORT",
                "Score",
                "Breakout %"
            ],
            ascending=[
                True,
                False,
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
    "Uploading BB scanner results..."
)

print(
    "======================================"
)


if not result_df.empty:


    # ========================================================
    # MAIN BB SCANNER SHEET
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
        "NIFTY 500 SWING BB updated successfully!"
    )


    # ========================================================
    # SCANNER HISTORY BB
    # ONLY BUY STOCKS
    # ========================================================

    history_buy_df = result_df[
        result_df["BUY Signal"] == "BUY"
    ].copy()


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
        # CHECK HEADER
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
                "Scanner History BB header created."
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
            "Scanner History BB updated successfully!"
        )

        print(
            "Only BUY stocks saved in BB history."
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
    "BOLLINGER BAND QUALITY SCANNER RESULT"
)

print(
    "======================================"
)

print(
    result_df.to_string(
        index=False
    )
)
