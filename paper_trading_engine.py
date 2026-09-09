import yfinance as yf
import pandas as pd
import numpy as np
import gspread
import os
import json
import math

from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials


# ============================================================
# STEP 4 ? PAPER TRADING ENGINE
# NIFTY 500 SWING BB
#
# FINAL RULES
# ------------------------------------------------------------
# Starting Capital       = ?3,00,000
# Entry                  = Next Trading Day OPEN
# Target                 = +6.28%
# Stop Loss              = NONE
# Max New Trades / Day   = 1
# Investment Size        = Trading Steps sheet
# Quantity               = ROUND UP
# ============================================================


print("")
print("=" * 75)
print(" STEP 4 ? PAPER TRADING ENGINE")
print("=" * 75)
print("")


# ============================================================
# SETTINGS
# ============================================================

SPREADSHEET_ID = (
    "1s8LybmXezn-xTqDgiKTBWGwkiK62O3qghuviUokeUKs"
)

HISTORY_SHEET = "Scanner History BB"
TRADING_STEPS_SHEET = "Trading Steps"

PAPER_TRADES_SHEET = "PAPER TRADES"
PAPER_PORTFOLIO_SHEET = "PAPER PORTFOLIO"

STARTING_CAPITAL = 300000.00

TARGET_PERCENT = 6.28

TARGET_MULTIPLIER = 1 + (
    TARGET_PERCENT / 100
)


# ============================================================
# INDIA DATE
# ============================================================

today_india = datetime.now(
    ZoneInfo("Asia/Kolkata")
).date()

print("Engine Date:", today_india)
print("Starting Capital:", STARTING_CAPITAL)
print("Target:", f"{TARGET_PERCENT}%")
print("Stop Loss: NONE")
print("")


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

creds_json = os.environ.get(
    "GCP_CREDENTIALS"
)

if not creds_json:
    raise Exception(
        "GCP_CREDENTIALS secret not found"
    )

service_account_info = json.loads(
    creds_json
)

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = (
    Credentials
    .from_service_account_info(
        service_account_info,
        scopes=scopes
    )
)

gc = gspread.authorize(
    credentials
)

spreadsheet = gc.open_by_key(
    SPREADSHEET_ID
)

print("Google Sheet connected.")
print("Spreadsheet Title:", spreadsheet.title)

print(
    "Available Worksheets:",
    [ws.title for ws in spreadsheet.worksheets()]
)

print("")


# ============================================================
# OPEN REQUIRED SHEETS
# ============================================================

history_ws = spreadsheet.worksheet(
    HISTORY_SHEET
)

trading_steps_ws = spreadsheet.worksheet(
    TRADING_STEPS_SHEET
)


# ============================================================
# CREATE PAPER TRADES SHEET
# ============================================================

try:

    paper_trades_ws = spreadsheet.worksheet(
        PAPER_TRADES_SHEET
    )

    print(
        "PAPER TRADES sheet found."
    )

except gspread.WorksheetNotFound:

    paper_trades_ws = spreadsheet.add_worksheet(
        title=PAPER_TRADES_SHEET,
        rows=5000,
        cols=40
    )

    print(
        "PAPER TRADES sheet created."
    )


# ============================================================
# CREATE PAPER PORTFOLIO SHEET
# ============================================================

try:

    paper_portfolio_ws = spreadsheet.worksheet(
        PAPER_PORTFOLIO_SHEET
    )

    print(
        "PAPER PORTFOLIO sheet found."
    )

except gspread.WorksheetNotFound:

    paper_portfolio_ws = spreadsheet.add_worksheet(
        title=PAPER_PORTFOLIO_SHEET,
        rows=5000,
        cols=40
    )

    print(
        "PAPER PORTFOLIO sheet created."
    )


# ============================================================
# LOAD TRADING STEPS
#
# IMPORTANT:
# Do NOT use get_all_records() here.
#
# Trading Steps contains blank cells in its header area.
# gspread therefore reports duplicate blank headers.
#
# We read raw values and manually locate "Investment Size".
# ============================================================

print("")
print(
    "Loading Investment Size from Trading Steps..."
)


trading_steps_values = (
    trading_steps_ws.get_all_values()
)


if not trading_steps_values:

    raise Exception(
        "Trading Steps sheet is empty."
    )


# ============================================================
# FIND INVESTMENT SIZE COLUMN
# ============================================================

investment_column_index = None
investment_header_row_index = None


for row_index, row in enumerate(
    trading_steps_values
):

    for column_index, cell_value in enumerate(
        row
    ):

        clean_value = (
            str(cell_value)
            .strip()
            .lower()
            .replace("_", " ")
        )

        if clean_value == "investment size":

            investment_column_index = column_index

            investment_header_row_index = row_index

            break

    if investment_column_index is not None:

        break


if investment_column_index is None:

    raise Exception(
        "Investment Size column not found "
        "in Trading Steps sheet."
    )


print(
    "Investment Size column found at:",
    f"Column {investment_column_index + 1}"
)

print(
    "Investment Size header row:",
    investment_header_row_index + 1
)


# ============================================================
# EXTRACT INVESTMENT SIZE LADDER
# ============================================================

investment_sizes = []


for row in trading_steps_values[
    investment_header_row_index + 1:
]:

    if (
        investment_column_index
        >= len(row)
    ):

        continue


    value = row[
        investment_column_index
    ]


    try:

        if value is None:
            continue

        text = str(value).strip()

        if text == "":
            continue

        # Remove common currency / comma formatting
        text = (
            text
            .replace("?", "")
            .replace("?", "")
            .replace(",", "")
            .replace("Rs.", "")
            .replace("Rs", "")
            .strip()
        )

        number = float(text)

        if number > 0:

            investment_sizes.append(
                number
            )

    except Exception:

        continue


if not investment_sizes:

    raise Exception(
        "No valid Investment Size values "
        "found in Trading Steps."
    )


print(
    "Investment Size values loaded:",
    len(investment_sizes)
)

print(
    "First Investment Size:",
    investment_sizes[0]
)

print("")


# ============================================================
# LOAD BUY SIGNAL HISTORY
# ============================================================

print(
    "Loading Scanner History BB..."
)

history_data = (
    history_ws.get_all_records()
)

if not history_data:

    raise Exception(
        "Scanner History BB is empty. "
        "No BUY signals available."
    )


history_df = pd.DataFrame(
    history_data
)


# ============================================================
# CHECK REQUIRED COLUMNS
# ============================================================

required_history_columns = [
    "Scan Date",
    "Stock",
    "BUY Signal"
]

for column in required_history_columns:

    if column not in history_df.columns:

        raise Exception(
            f"Required column missing "
            f"from Scanner History BB: {column}"
        )


# ============================================================
# ONLY BUY SIGNALS
# ============================================================

history_df = history_df[
    history_df["BUY Signal"]
    .astype(str)
    .str.upper()
    .str.strip()
    == "BUY"
].copy()


if history_df.empty:

    raise Exception(
        "No BUY signals found in "
        "Scanner History BB."
    )


# ============================================================
# PARSE SIGNAL DATE - SAFE FOR ALL EXPECTED DATE FORMATS
# ============================================================

def parse_scan_date(value):
    if value is None or str(value).strip() == "":
        return None

    text = str(value).strip()

    # ISO: YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
        try:
            return pd.to_datetime(text, format="%Y-%m-%d", errors="coerce").date()
        except Exception:
            return None

    # ISO with slash: YYYY/M/D
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        try:
            return pd.to_datetime(text, format="%Y/%m/%d", errors="coerce").date()
        except Exception:
            return None

    # Indian: DD-MM-YYYY / DD/MM/YYYY
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            parsed = pd.to_datetime(text, format=fmt, errors="coerce")
            if not pd.isna(parsed):
                return parsed.date()
        except Exception:
            pass

    try:
        parsed = pd.to_datetime(text, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None

history_df["Signal Date"] = history_df["Scan Date"].apply(parse_scan_date)


history_df = history_df.dropna(
    subset=["Signal Date"]
)


# ============================================================
# CLEAN STOCK SYMBOL
# ============================================================

history_df["Stock"] = (
    history_df["Stock"]
    .astype(str)
    .str.strip()
    .str.upper()
)


history_df = history_df[
    history_df["Stock"] != ""
].copy()


# ============================================================
# REMOVE EXACT DUPLICATE SIGNALS
# ============================================================

history_df = (
    history_df
    .drop_duplicates(
        subset=[
            "Signal Date",
            "Stock"
        ]
    )
)


# ============================================================
# CHRONOLOGICAL ORDER
# ============================================================

history_df = (
    history_df
    .sort_values(
        by=[
            "Signal Date",
            "Stock"
        ]
    )
    .reset_index(
        drop=True
    )
)


print(
    "Historical BUY signals:",
    len(history_df)
)

print("")


# ============================================================
# DOWNLOAD PRICE DATA
# ============================================================

symbols = (
    history_df["Stock"]
    .drop_duplicates()
    .tolist()
)

print(
    "Unique stocks:",
    len(symbols)
)

print("")
print(
    "Downloading historical OHLC data..."
)
print("")


price_data = {}


for i, stock in enumerate(
    symbols,
    start=1
):

    ticker = stock

    if not ticker.endswith(
        ".NS"
    ):

        ticker = ticker + ".NS"


    try:

        print(
            f"[{i}/{len(symbols)}] Downloading {ticker}"
        )


        data = yf.download(
            ticker,
            period="max",
            interval="1d",
            auto_adjust=False,
            progress=False
        )


        if data.empty:

            print(
                "  No data:",
                ticker
            )

            continue


        # ====================================================
        # FIX MULTIINDEX
        # ====================================================

        if isinstance(
            data.columns,
            pd.MultiIndex
        ):

            data.columns = (
                data.columns
                .get_level_values(0)
            )


        required_price_columns = [
            "Open",
            "High",
            "Low",
            "Close"
        ]


        if not all(
            column in data.columns
            for column
            in required_price_columns
        ):

            print(
                "  Required OHLC missing:",
                ticker
            )

            continue


        data = data[
            required_price_columns
        ].copy()


        for column in required_price_columns:

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce"
            )


        data = data.dropna()


        # ====================================================
        # NORMALIZE DATE
        # ====================================================

        if isinstance(
            data.index,
            pd.DatetimeIndex
        ):

            data.index = (
                data.index
                .tz_localize(None)
                .normalize()
            )


        price_data[stock] = data


    except Exception as e:

        print(
            "  Download error:",
            ticker,
            e
        )


print("")
print(
    "Price data loaded for:",
    len(price_data),
    "stocks"
)
print("")


# ============================================================
# HELPER:
# NEXT TRADING DAY
# ============================================================

def get_next_trading_day(
    data,
    signal_date
):

    signal_timestamp = pd.Timestamp(
        signal_date
    )

    future_data = data[
        data.index
        > signal_timestamp
    ]


    if future_data.empty:

        return None


    return future_data.index[0]


# ============================================================
# HELPER:
# GET PRICE ON DATE
# ============================================================

def get_day_row(
    data,
    date_value
):

    try:

        timestamp = pd.Timestamp(
            date_value
        )

        if timestamp in data.index:

            return data.loc[
                timestamp
            ]

    except Exception:

        pass


    return None


# ============================================================
# LOAD EXISTING PAPER TRADES — PERSISTENT STATE
# ============================================================
print("Loading existing PAPER TRADES...")

paper_trade_columns = [
    "Stock", "Signal Date", "Entry Date", "Entry Price", "Target Price",
    "Quantity", "Investment Size", "Actual Investment", "Target %",
    "Target Hit Date", "Exit Date", "Exit Price", "Exit Value",
    "Profit/Loss", "Profit %", "Current Price", "Current Value",
    "Unrealized P/L", "Unrealized %", "Last Price Date", "Status"
]

existing_values = paper_trades_ws.get_all_values()
existing_trades = []

if existing_values and len(existing_values) > 1:
    existing_header = [str(x).strip() for x in existing_values[0]]
    header_map = {name: i for i, name in enumerate(existing_header) if name}

    for raw_row in existing_values[1:]:
        if not any(str(x).strip() for x in raw_row):
            continue
        trade = {}
        for column in paper_trade_columns:
            idx = header_map.get(column)
            trade[column] = raw_row[idx].strip() if idx is not None and idx < len(raw_row) else ""
        if trade.get("Stock"):
            existing_trades.append(trade)

print("Existing PAPER TRADES:", len(existing_trades))


def parse_date_value(value):
    if value is None or str(value).strip() == "":
        return None

    text = str(value).strip()

    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
        try:
            return pd.to_datetime(text, format="%Y-%m-%d", errors="coerce").date()
        except Exception:
            return None

    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        try:
            return pd.to_datetime(text, format="%Y/%m/%d", errors="coerce").date()
        except Exception:
            return None

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            parsed = pd.to_datetime(text, format=fmt, errors="coerce")
            if not pd.isna(parsed):
                return parsed.date()
        except Exception:
            pass

    try:
        parsed = pd.to_datetime(text, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


def to_float(value, default=0.0):
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).replace(",", "").replace("?", "").replace("Rs.", "").replace("Rs", "").strip())
    except Exception:
        return default


# Normalize existing rows and build the set of already processed signals.
for trade in existing_trades:
    trade["Stock"] = str(trade.get("Stock", "")).strip().upper()
    trade["Signal Date"] = parse_date_value(trade.get("Signal Date"))
    trade["Entry Date"] = parse_date_value(trade.get("Entry Date"))
    trade["Target Hit Date"] = parse_date_value(trade.get("Target Hit Date"))
    trade["Exit Date"] = parse_date_value(trade.get("Exit Date"))
    trade["Last Price Date"] = parse_date_value(trade.get("Last Price Date"))
    for c in ["Entry Price", "Target Price", "Quantity", "Investment Size", "Actual Investment",
              "Target %", "Exit Price", "Exit Value", "Profit/Loss", "Profit %", "Current Price",
              "Current Value", "Unrealized P/L", "Unrealized %"]:
        if trade.get(c, "") != "":
            trade[c] = to_float(trade[c], 0.0)

existing_signal_keys = set()
for trade in existing_trades:
    if trade.get("Stock") and trade.get("Signal Date"):
        existing_signal_keys.add((trade["Signal Date"], trade["Stock"]))

# ============================================================
# RECONSTRUCT CASH + NEXT LADDER STEP
# ============================================================
# PAPER TRADES is the persistent ledger. Cash is reconstructed from
# actual investments and target-hit exit values so every GitHub run
# starts from the same state instead of replaying old signals.

cash = float(STARTING_CAPITAL)

for trade in existing_trades:
    actual_investment = to_float(trade.get("Actual Investment"), 0.0)
    cash -= actual_investment

    if str(trade.get("Status", "")).strip().upper() == "TARGET HIT":
        cash += to_float(trade.get("Exit Value"), 0.0)

cash = max(cash, 0.0)
investment_index = len(existing_trades)

# ============================================================
# UPDATE EXISTING OPEN TRADES — ONLY UP TO TODAY
# ============================================================
# Never look into future market data. A target can only be registered
# if its High was reached on or before today's Indian date.

open_positions = []
completed_trades = []
active_stock_until = {}

for trade in existing_trades:
    stock = trade["Stock"]
    entry_date = trade.get("Entry Date")
    entry_price = to_float(trade.get("Entry Price"), 0.0)
    target_price = to_float(trade.get("Target Price"), 0.0)
    quantity = int(round(to_float(trade.get("Quantity"), 0.0)))
    actual_investment = to_float(trade.get("Actual Investment"), 0.0)
    status = str(trade.get("Status", "")).strip().upper()

    if status == "TARGET HIT":
        completed_trades.append(trade.copy())
        active_stock_until[stock] = trade.get("Target Hit Date") or trade.get("Exit Date")
        continue

    if stock not in price_data or entry_date is None or entry_price <= 0 or quantity <= 0:
        open_positions.append(trade.copy())
        active_stock_until[stock] = None
        continue

    data = price_data[stock]
    entry_timestamp = pd.Timestamp(entry_date)
    today_timestamp = pd.Timestamp(today_india)

    scan_exit_data = data[(data.index >= entry_timestamp) & (data.index <= today_timestamp)].copy()
    target_hit_timestamp = None

    for check_timestamp, day_row in scan_exit_data.iterrows():
        try:
            day_high = float(day_row["High"])
        except Exception:
            continue
        if np.isfinite(day_high) and day_high >= target_price:
            target_hit_timestamp = check_timestamp
            break

    if target_hit_timestamp is not None:
        exit_date = target_hit_timestamp.date()
        exit_price = target_price
        exit_value = quantity * exit_price
        profit_loss = exit_value - actual_investment
        profit_percent = (profit_loss / actual_investment * 100) if actual_investment else 0.0

        # The original row's investment was already deducted above;
        # now return capital + profit exactly once.
        cash += exit_value

        trade.update({
            "Target Hit Date": exit_date,
            "Exit Date": exit_date,
            "Exit Price": exit_price,
            "Exit Value": exit_value,
            "Profit/Loss": profit_loss,
            "Profit %": profit_percent,
            "Current Price": "",
            "Current Value": "",
            "Unrealized P/L": "",
            "Unrealized %": "",
            "Last Price Date": exit_date,
            "Status": "TARGET HIT",
        })
        completed_trades.append(trade.copy())
        active_stock_until[stock] = exit_date

        print(
            f"TARGET HIT | {stock} | Entry {entry_date} @ {entry_price:.2f} | "
            f"Exit {exit_date} @ {exit_price:.2f} | P/L ?{profit_loss:.2f} | Cash ?{cash:.2f}"
        )
    else:
        # Current mark-to-market must also be limited to today.
        available = data[data.index <= today_timestamp]
        if not available.empty:
            latest_timestamp = available.index[-1]
            latest_close = float(available.iloc[-1]["Close"])
            current_value = quantity * latest_close
            unrealized_pnl = current_value - actual_investment
            unrealized_percent = (unrealized_pnl / actual_investment * 100) if actual_investment else 0.0

            trade.update({
                "Current Price": latest_close,
                "Current Value": current_value,
                "Unrealized P/L": unrealized_pnl,
                "Unrealized %": unrealized_percent,
                "Last Price Date": latest_timestamp.date(),
                "Status": "OPEN",
                "Target %": TARGET_PERCENT,
            })

        open_positions.append(trade.copy())
        active_stock_until[stock] = None

# ============================================================
# FIND TODAY'S NEW ENTRY — NO HISTORICAL REPLAY
# ============================================================
print("")
print("=" * 75)
print(" CHECKING TODAY'S NEW BUY SIGNALS")
print("=" * 75)
print("")

new_trade = None
new_trade_count = 0
skipped_trades = []

# Only a signal whose NEXT trading day is TODAY can create a new trade.
# This prevents the engine from replaying all old Scanner History rows.
today_candidates = []

for _, signal in history_df.iterrows():
    stock = str(signal["Stock"]).strip().upper()
    signal_date = signal["Signal Date"]
    key = (signal_date, stock)

    if key in existing_signal_keys:
        continue
    if stock not in price_data:
        continue

    data = price_data[stock]
    entry_timestamp = get_next_trading_day(data, signal_date)
    if entry_timestamp is None:
        continue

    entry_date = entry_timestamp.date()
    if entry_date == today_india:
        today_candidates.append((signal_date, stock, entry_timestamp))

today_candidates.sort(key=lambda x: (x[2], x[1]))

print("Today's eligible new signals:", len(today_candidates))

print("Recent BUY signals / next entry dates:")
for _, signal in history_df.tail(15).iterrows():
    debug_stock = str(signal["Stock"]).strip().upper()
    debug_signal_date = signal["Signal Date"]
    if debug_stock in price_data and debug_signal_date is not None:
        debug_next = get_next_trading_day(price_data[debug_stock], debug_signal_date)
        print(
            f"  {debug_stock} | Signal {debug_signal_date} | "
            f"Next Entry {debug_next.date() if debug_next is not None else None}"
        )


for signal_date, stock, entry_timestamp in today_candidates:
    if new_trade_count >= 1:
        skipped_trades.append({
            "Stock": stock,
            "Signal Date": signal_date,
            "Entry Date": today_india,
            "Reason": "Maximum 1 new trade per day"
        })
        continue

    # Do not buy a stock that is already open.
    if stock in active_stock_until and active_stock_until[stock] is None:
        skipped_trades.append({
            "Stock": stock,
            "Signal Date": signal_date,
            "Entry Date": today_india,
            "Reason": "Stock already has an open trade"
        })
        continue

    data = price_data[stock]
    entry_row = get_day_row(data, entry_timestamp)
    if entry_row is None:
        skipped_trades.append({
            "Stock": stock,
            "Signal Date": signal_date,
            "Entry Date": today_india,
            "Reason": "Entry price unavailable"
        })
        continue

    try:
        entry_price = float(entry_row["Open"])
    except Exception:
        entry_price = 0.0

    if not np.isfinite(entry_price) or entry_price <= 0:
        skipped_trades.append({
            "Stock": stock,
            "Signal Date": signal_date,
            "Entry Date": today_india,
            "Reason": "Invalid entry price"
        })
        continue

    if investment_index >= len(investment_sizes):
        skipped_trades.append({
            "Stock": stock,
            "Signal Date": signal_date,
            "Entry Date": today_india,
            "Reason": "Investment Size ladder exhausted"
        })
        continue

    planned_investment = float(investment_sizes[investment_index])
    quantity = math.ceil(planned_investment / entry_price)
    actual_investment = quantity * entry_price

    if actual_investment > cash + 0.000001:
        skipped_trades.append({
            "Stock": stock,
            "Signal Date": signal_date,
            "Entry Date": today_india,
            "Investment Size": planned_investment,
            "Actual Investment": actual_investment,
            "Available Cash": cash,
            "Reason": "Insufficient capital"
        })
        continue

    cash -= actual_investment
    target_price = entry_price * TARGET_MULTIPLIER

    # Check target on entry day and only on dates through TODAY.
    target_hit_timestamp = None
    scan_exit_data = data[(data.index >= entry_timestamp) & (data.index <= pd.Timestamp(today_india))]
    for check_timestamp, day_row in scan_exit_data.iterrows():
        try:
            day_high = float(day_row["High"])
        except Exception:
            continue
        if np.isfinite(day_high) and day_high >= target_price:
            target_hit_timestamp = check_timestamp
            break

    position = {
        "Stock": stock,
        "Signal Date": signal_date,
        "Entry Date": today_india,
        "Entry Price": entry_price,
        "Target Price": target_price,
        "Quantity": quantity,
        "Investment Size": planned_investment,
        "Actual Investment": actual_investment,
        "Target %": TARGET_PERCENT,
        "Target Hit Date": target_hit_timestamp.date() if target_hit_timestamp is not None else None,
        "Exit Date": target_hit_timestamp.date() if target_hit_timestamp is not None else "",
        "Exit Price": target_price if target_hit_timestamp is not None else "",
        "Exit Value": quantity * target_price if target_hit_timestamp is not None else "",
        "Profit/Loss": (quantity * target_price - actual_investment) if target_hit_timestamp is not None else "",
        "Profit %": ((quantity * target_price - actual_investment) / actual_investment * 100) if target_hit_timestamp is not None else "",
        "Current Price": "",
        "Current Value": "",
        "Unrealized P/L": "",
        "Unrealized %": "",
        "Last Price Date": today_india,
        "Status": "TARGET HIT" if target_hit_timestamp is not None else "OPEN",
    }

    if target_hit_timestamp is not None:
        exit_value = quantity * target_price
        cash += exit_value
        completed_trades.append(position.copy())
        active_stock_until[stock] = target_hit_timestamp.date()
        print(f"TARGET HIT TODAY | {stock} | Entry ?{entry_price:.2f} | Exit ?{target_price:.2f}")
    else:
        latest_row = data[data.index <= pd.Timestamp(today_india)].iloc[-1]
        latest_close = float(latest_row["Close"])
        current_value = quantity * latest_close
        unrealized_pnl = current_value - actual_investment
        unrealized_percent = (unrealized_pnl / actual_investment * 100) if actual_investment else 0.0
        position.update({
            "Current Price": latest_close,
            "Current Value": current_value,
            "Unrealized P/L": unrealized_pnl,
            "Unrealized %": unrealized_percent,
            "Last Price Date": today_india,
        })
        open_positions.append(position.copy())
        active_stock_until[stock] = None
        print(
            f"NEW TRADE | {stock} | Signal {signal_date} | Entry {today_india} @ ?{entry_price:.2f} | "
            f"Qty {quantity} | Investment ?{actual_investment:.2f} | Cash ?{cash:.2f}"
        )

    existing_signal_keys.add((signal_date, stock))
    new_trade = position.copy()
    new_trade_count += 1
    investment_index += 1

# ============================================================
# COMBINE PERSISTENT + NEW TRADES
# ============================================================
all_trades = completed_trades + open_positions

# Deduplicate by Signal Date + Stock, keeping the latest state.
trade_map = {}
for trade in all_trades:
    key = (trade.get("Signal Date"), str(trade.get("Stock", "")).upper())
    trade_map[key] = trade
all_trades = list(trade_map.values())

if all_trades:
    trades_df = pd.DataFrame(all_trades)
    trades_df = trades_df.sort_values(by=["Entry Date", "Stock"], na_position="last").reset_index(drop=True)
else:
    trades_df = pd.DataFrame()

# ============================================================
# PORTFOLIO MARKET VALUE
# ============================================================

open_market_value = 0.0

unrealized_pnl_total = 0.0


for position in open_positions:

    try:

        open_market_value += float(
            position[
                "Current Value"
            ]
        )

        unrealized_pnl_total += float(
            position[
                "Unrealized P/L"
            ]
        )

    except Exception:

        pass


# ============================================================
# REALIZED P/L
# ============================================================

realized_pnl = 0.0


for trade in completed_trades:

    try:

        realized_pnl += float(
            trade[
                "Profit/Loss"
            ]
        )

    except Exception:

        pass


# ============================================================
# TOTAL EQUITY
# ============================================================

total_equity = (
    cash
    + open_market_value
)


total_return = (
    total_equity
    - STARTING_CAPITAL
)


total_return_percent = (
    total_return
    / STARTING_CAPITAL
) * 100


# ============================================================
# PAPER TRADES OUTPUT
# ============================================================

print("")
print("=" * 75)
print(" UPDATING PAPER TRADES")
print("=" * 75)
print("")


paper_trade_columns = [

    "Stock",
    "Signal Date",
    "Entry Date",
    "Entry Price",
    "Target Price",
    "Quantity",
    "Investment Size",
    "Actual Investment",
    "Target %",
    "Target Hit Date",
    "Exit Date",
    "Exit Price",
    "Exit Value",
    "Profit/Loss",
    "Profit %",
    "Current Price",
    "Current Value",
    "Unrealized P/L",
    "Unrealized %",
    "Last Price Date",
    "Status"
]


# ============================================================
# BUILD PAPER TRADES DIRECTLY FROM ALL TRADES
# ============================================================

print(
    "Total processed trades:",
    len(all_trades)
)


trades_df = pd.DataFrame(
    all_trades
)


if not trades_df.empty:

    # --------------------------------------------------------
    # ADD ANY MISSING COLUMNS
    # --------------------------------------------------------

    for column in paper_trade_columns:

        if column not in trades_df.columns:

            trades_df[column] = ""


    # --------------------------------------------------------
    # KEEP EXACT PAPER TRADES COLUMN ORDER
    # --------------------------------------------------------

    trades_df = trades_df[
        paper_trade_columns
    ].copy()


    # --------------------------------------------------------
    # CONVERT DATE VALUES TO STRING
    # --------------------------------------------------------

    date_columns = [

        "Signal Date",
        "Entry Date",
        "Target Hit Date",
        "Exit Date",
        "Last Price Date"
    ]


    for column in date_columns:

        if column in trades_df.columns:

            trades_df[column] = trades_df[
                column
            ].apply(

                lambda x: (
                    x.isoformat()
                    if hasattr(x, "isoformat")
                    else (
                        str(x)
                        if x not in ["", None]
                        else ""
                    )
                )
            )


    # --------------------------------------------------------
    # ROUND NUMERIC COLUMNS
    # --------------------------------------------------------

    numeric_columns = [

        "Entry Price",
        "Target Price",
        "Investment Size",
        "Actual Investment",
        "Target %",
        "Exit Price",
        "Exit Value",
        "Profit/Loss",
        "Profit %",
        "Current Price",
        "Current Value",
        "Unrealized P/L",
        "Unrealized %"
    ]


    for column in numeric_columns:

        if column in trades_df.columns:

            trades_df[column] = pd.to_numeric(
                trades_df[column],
                errors="coerce"
            ).round(2)


    # --------------------------------------------------------
    # CONVERT ALL VALUES TO GOOGLE-SHEETS / JSON SAFE TYPES
    # --------------------------------------------------------

    paper_trades_values = [
        paper_trade_columns
    ]


    for _, trade in trades_df.iterrows():

        row = []

        for column in paper_trade_columns:

            value = trade[column]


            if pd.isna(value):

                value = ""


            elif isinstance(
                value,
                (np.integer,)
            ):

                value = int(value)


            elif isinstance(
                value,
                (np.floating,)
            ):

                value = float(value)


            elif hasattr(
                value,
                "isoformat"
            ):

                value = value.isoformat()


            else:

                value = str(value)


            row.append(value)


        paper_trades_values.append(
            row
        )


else:

    print(
        "WARNING: No trades found for PAPER TRADES."
    )

    paper_trades_values = [
        paper_trade_columns
    ]


# ============================================================
# UPDATE PAPER TRADES
# ============================================================

paper_trades_ws.clear()


# Make sure the worksheet has enough rows/columns.
required_rows = max(
    len(paper_trades_values),
    100
)

required_columns = len(
    paper_trade_columns
)


paper_trades_ws.resize(
    rows=required_rows,
    cols=required_columns
)


paper_trades_ws.update(
    range_name="A1",
    values=paper_trades_values,
    value_input_option="USER_ENTERED"
)


print(
    "PAPER TRADES updated."
)


print(
    "PAPER TRADES rows written:",
    len(paper_trades_values) - 1
)


# ============================================================
# PAPER PORTFOLIO
# ============================================================

portfolio_rows = []


# ============================================================
# SUMMARY
# ============================================================

portfolio_rows.append([
    "Metric",
    "Value"
])


portfolio_rows.append([
    "As Of Date",
    str(today_india)
])


portfolio_rows.append([
    "Starting Capital",
    round(
        STARTING_CAPITAL,
        2
    )
])


portfolio_rows.append([
    "Available Cash",
    round(
        cash,
        2
    )
])


portfolio_rows.append([
    "Open Market Value",
    round(
        open_market_value,
        2
    )
])


portfolio_rows.append([
    "Total Equity",
    round(
        total_equity,
        2
    )
])


portfolio_rows.append([
    "Realized P/L",
    round(
        realized_pnl,
        2
    )
])


portfolio_rows.append([
    "Unrealized P/L",
    round(
        unrealized_pnl_total,
        2
    )
])


portfolio_rows.append([
    "Total Return",
    round(
        total_return,
        2
    )
])


portfolio_rows.append([
    "Total Return %",
    round(
        total_return_percent,
        2
    )
])


portfolio_rows.append([
    "Completed Trades",
    len(completed_trades)
])


portfolio_rows.append([
    "Open Positions",
    len(open_positions)
])


portfolio_rows.append([
    "Total Processed Entries",
    len(all_trades)
])


portfolio_rows.append([
    "Skipped Signals",
    len(skipped_trades)
])


portfolio_rows.append([
    "Next Investment Size Index",
    investment_index + 1
])


if investment_index < len(
    investment_sizes
):

    next_investment_size = (
        investment_sizes[
            investment_index
        ]
    )

else:

    next_investment_size = "LADDER EXHAUSTED"


portfolio_rows.append([
    "Next Investment Size",
    next_investment_size
])


portfolio_rows.append([
    "Target %",
    TARGET_PERCENT
])


portfolio_rows.append([
    "Stop Loss",
    "NONE"
])


portfolio_rows.append([
    "",
    ""
])


# ============================================================
# OPEN POSITION DETAILS
# ============================================================

portfolio_rows.append([
    "OPEN POSITIONS",
    ""
])


portfolio_rows.append([
    "Stock",
    "Entry Date"
])


for position in open_positions:

    portfolio_rows.append([
        position["Stock"],
        str(position["Entry Date"])
    ])


# ============================================================
# UPDATE PAPER PORTFOLIO
# ============================================================

paper_portfolio_ws.clear()

paper_portfolio_ws.update(
    range_name="A1",
    values=portfolio_rows,
    value_input_option="USER_ENTERED"
)


print(
    "PAPER PORTFOLIO updated."
)


# ============================================================
# ENGINE SUMMARY
# ============================================================

print("")
print("=" * 75)
print(" ENGINE SUMMARY")
print("=" * 75)


print(
    "Starting Capital      : ?",
    round(
        STARTING_CAPITAL,
        2
    )
)


print(
    "Available Cash        : ?",
    round(
        cash,
        2
    )
)


print(
    "Open Market Value     : ?",
    round(
        open_market_value,
        2
    )
)


print(
    "Total Equity          : ?",
    round(
        total_equity,
        2
    )
)


print(
    "Realized P/L          : ?",
    round(
        realized_pnl,
        2
    )
)


print(
    "Unrealized P/L        : ?",
    round(
        unrealized_pnl_total,
        2
    )
)


print(
    "Total Return          : ?",
    round(
        total_return,
        2
    )
)


print(
    "Total Return %        :",
    round(
        total_return_percent,
        2
    ),
    "%"
)


print(
    "Completed Trades      :",
    len(completed_trades)
)


print(
    "Open Positions        :",
    len(open_positions)
)


print(
    "Skipped Signals       :",
    len(skipped_trades)
)


print(
    "Investment Sizes Used :",
    investment_index
)


print(
    "Target                :",
    f"{TARGET_PERCENT}%"
)


print(
    "Stop Loss             : NONE"
)


print("")
print("=" * 75)
print(" PAPER TRADING ENGINE COMPLETED")
print("=" * 75)
print("")


# ============================================================
# OPEN POSITIONS DISPLAY
# ============================================================

if open_positions:

    print(
        "CURRENT OPEN POSITIONS:"
    )

    print("")

    for position in open_positions:

        print(
            position["Stock"],
            "| Entry:",
            position["Entry Date"],
            "| Entry Price:",
            round(
                position["Entry Price"],
                2
            ),
            "| Target:",
            round(
                position["Target Price"],
                2
            ),
            "| Qty:",
            position["Quantity"],
            "| Current:",
            round(
                position["Current Price"],
                2
            ),
            "| Unrealized P/L:",
            round(
                position["Unrealized P/L"],
                2
            )
        )

else:

    print(
        "No open positions."
    )


print("")
print(
    "Google Sheets updated successfully."
)
