import os
from datetime import datetime
from typing import List

import pandas as pd
import yfinance as yf
from sqlalchemy import (
    Column,
    Date,
    Float,
    Integer,
    String,
    ForeignKey,
    create_engine,
    text,
)
import time
import json
import requests
import zipfile
import io
import tempfile
from datetime import datetime, timedelta
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import inspect
from sqlalchemy.types import Numeric, BigInteger
import argparse


Base = declarative_base()


class Company(Base):
    __tablename__ = "companies"

    ticker = Column(String(32), primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    country = Column(String(64), nullable=True)
    currency = Column(String(16), nullable=True)

    prices = relationship("PriceDaily", back_populates="company")


class PriceDaily(Base):
    __tablename__ = "prices_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(32), ForeignKey("companies.ticker"), index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    open = Column(Numeric(20, 6), nullable=True)
    high = Column(Numeric(20, 6), nullable=True)
    low = Column(Numeric(20, 6), nullable=True)
    close = Column(Numeric(20, 6), nullable=True)
    adj_close = Column(Numeric(20, 6), nullable=True)
    volume = Column(BigInteger, nullable=True)

    company = relationship("Company", back_populates="prices")


def get_db_path() -> str:
    # Place DB at project root: .../Sisukai/sisukai.db
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    return os.path.join(project_root, "sisukai.db")


def get_engine(db_url: str | None = None):
    if db_url:
        return create_engine(db_url, pool_pre_ping=True)
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # Add timeout to reduce 'database is locked' issues and allow cross-thread
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"timeout": 30, "check_same_thread": False},
        pool_pre_ping=True,
    )


def init_db(db_url: str | None = None):
    engine = get_engine(db_url)
    # Do NOT auto-create ORM tables; schema is managed by ensure_schema_per_mysql_spec/Excel
    return engine


def _map_type(t: str, dialect: str) -> str:
    s = (t or "").strip().lower()
    if dialect == "mysql":
        if s in ("string", "str", "text", "varchar", "char"):
            return "VARCHAR(255)"
        if s in ("int", "integer", "smallint"):
            return "INT"
        if s in ("bigint",):
            return "BIGINT"
        if s in ("float", "real", "double"):
            return "DOUBLE"
        if s.startswith("decimal") or s.startswith("numeric"):
            return s.upper() if "(" in s else "DECIMAL(20,6)"
        if s in ("decimal", "numeric"):
            return "DECIMAL(20,6)"
        if s in ("date", "datetime", "timestamp"):
            return "DATETIME" if s != "date" else "DATE"
        return "VARCHAR(255)"
    else:  # sqlite default
        if s in ("string", "str", "text", "varchar", "char"):
            return "TEXT"
        if s in ("int", "integer", "bigint", "smallint"):
            return "INTEGER"
        if s in ("float", "double", "real", "decimal", "numeric"):
            return "REAL"
        if s in ("date", "datetime", "timestamp"):
            return "DATE"
        return "TEXT"


def apply_excel_schema_if_present(excel_path: str, engine):
    if not os.path.exists(excel_path):
        return
    try:
        xls = pd.ExcelFile(excel_path)
    except Exception:
        return
    sheet_names = [s.lower() for s in xls.sheet_names]
    try:
        dialect = engine.url.get_dialect().name
    except Exception:
        dialect = "sqlite"
    if "schema" in sheet_names:
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[sheet_names.index("schema")])
        cols = {c.strip().lower(): c for c in df.columns if isinstance(c, str)}
        required = ["table", "column", "type"]
        if all(k in cols for k in required):
            tbl_col = cols["table"]
            col_col = cols["column"]
            type_col = cols["type"]
            nullable_col = cols.get("nullable")
            pk_col = cols.get("pk") or cols.get("primary") or cols.get("primary_key")
            unique_col = cols.get("unique")

            spec = {}
            for _, row in df.iterrows():
                tname = str(row[tbl_col]).strip()
                cname = str(row[col_col]).strip()
                if not tname or not cname:
                    continue
                ctype = _map_type(str(row[type_col]) if not pd.isna(row[type_col]) else "", dialect)
                nullable = True
                if nullable_col is not None and not pd.isna(row[nullable_col]):
                    v = str(row[nullable_col]).strip().lower()
                    nullable = not (v in ("false", "0", "no", "n"))
                pk = False
                if pk_col is not None and not pd.isna(row[pk_col]):
                    v = str(row[pk_col]).strip().lower()
                    pk = v in ("true", "1", "yes", "y")
                unique = False
                if unique_col is not None and not pd.isna(row[unique_col]):
                    v = str(row[unique_col]).strip().lower()
                    unique = v in ("true", "1", "yes", "y")
                spec.setdefault(tname, []).append({"name": cname, "type": ctype, "nullable": nullable, "pk": pk, "unique": unique})

            inspector = inspect(engine)
            with engine.begin() as conn:
                for table, cols_spec in spec.items():
                    existing_tables = inspector.get_table_names()
                    if table not in existing_tables:
                        pk_cols = [c["name"] for c in cols_spec if c["pk"]]
                        defs = []
                        for c in cols_spec:
                            d = f"{c['name']} {c['type']}"
                            if not c["nullable"]:
                                d += " NOT NULL"
                            if c["unique"] and c["name"] not in pk_cols:
                                d += " UNIQUE"
                            defs.append(d)
                        pk_clause = f", PRIMARY KEY ({', '.join(pk_cols)})" if pk_cols else ""
                        sql = f"CREATE TABLE IF NOT EXISTS {table} (" + ", ".join(defs) + pk_clause + ")"
                        conn.execute(text(sql))
                    else:
                        existing_cols = {c['name'] for c in inspector.get_columns(table)}
                        for c in cols_spec:
                            if c["name"] in existing_cols:
                                continue
                            add_sql = f"ALTER TABLE {table} ADD COLUMN {c['name']} {c['type']}"
                            if not c["nullable"]:
                                add_sql += " NOT NULL"
                            conn.execute(text(add_sql))
            return

    # Fallback: table-per-sheet with types in header (e.g., "col:type") or second row
    for sheet_name in xls.sheet_names:
        if sheet_name.lower() == "schema":
            continue
        try:
            df_head = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=2)
        except Exception:
            continue
        if df_head.empty:
            continue
        headers = list(df_head.iloc[0].fillna("").map(lambda v: str(v).strip()))
        types_row = list(df_head.iloc[1].fillna("").map(lambda v: str(v).strip())) if len(df_head) > 1 else [""] * len(headers)

        cols_spec = []
        for i, h in enumerate(headers):
            if not h:
                continue
            name = h
            typ_hint = ""
            if ":" in h:
                parts = h.split(":", 1)
                name = parts[0].strip()
                typ_hint = parts[1].strip()
            elif "(" in h and ")" in h and h.index("(") < h.rindex(")"):
                pre, post = h.split("(", 1)
                name = pre.strip()
                typ_hint = post.rsplit(")", 1)[0].strip()
            else:
                # try split by whitespace into name and type e.g. "close float"
                parts_ws = h.split()
                if len(parts_ws) == 2:
                    name = parts_ws[0].strip()
                    typ_hint = parts_ws[1].strip()
            if not typ_hint and i < len(types_row) and types_row[i]:
                typ_hint = types_row[i]
            cols_spec.append({"name": name, "type": _map_type(typ_hint, dialect), "nullable": True, "pk": False, "unique": False})

        if not cols_spec:
            continue

        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        with engine.begin() as conn:
            if sheet_name not in existing_tables:
                defs = [f"{c['name']} {c['type']}" for c in cols_spec]
                sql = f"CREATE TABLE IF NOT EXISTS {sheet_name} (" + ", ".join(defs) + ")"
                conn.execute(text(sql))
            else:
                existing_cols = {c['name'] for c in inspector.get_columns(sheet_name)}
                for c in cols_spec:
                    if c["name"] in existing_cols:
                        continue
                    conn.execute(text(f"ALTER TABLE {sheet_name} ADD COLUMN {c['name']} {c['type']}"))


def _ensure_financials_table(engine, table_name: str = "financials"):
    try:
        dialect = engine.url.get_dialect().name
    except Exception:
        dialect = "sqlite"
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    if table_name in existing_tables:
        return
    if dialect == "mysql":
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          ticker VARCHAR(32) NOT NULL,
          period_end DATE NOT NULL,
          period_type VARCHAR(16) NOT NULL,
          statement VARCHAR(16) NOT NULL,
          item VARCHAR(255) NOT NULL,
          value DECIMAL(20,6) NULL,
          currency VARCHAR(16) NULL,
          INDEX idx_{table_name}_tk_pd (ticker, period_end),
          INDEX idx_{table_name}_tk (ticker)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    else:
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ticker TEXT NOT NULL,
          period_end DATE NOT NULL,
          period_type TEXT NOT NULL,
          statement TEXT NOT NULL,
          item TEXT NOT NULL,
          value REAL NULL,
          currency TEXT NULL
        );
        """
    with engine.begin() as conn:
        conn.execute(text(create_sql))


def fetch_and_load_financials(engine, tickers: List[str], table_name: str = "financials"):
    _ensure_financials_table(engine, table_name)
    rows = []
    for t in tickers:
        tk = yf.Ticker(t)
        try:
            info = tk.info or {}
        except Exception:
            info = {}
        fcur = info.get("financialCurrency") or info.get("currency")
        datasets = []
        try:
            df = tk.financials
            if df is not None and not df.empty:
                datasets.append(("income", df, "annual"))
        except Exception:
            pass

    # Ensure manual mappings for common tickers if still missing
    defaults = {"7203.T": "E02144", "6758.T": "E01777", "9984.T": "E02778"}
    for k, v in defaults.items():
        ticker_to_edinet_map.setdefault(k, v)
        try:
            df = tk.quarterly_financials
            if df is not None and not df.empty:
                datasets.append(("income", df, "quarterly"))
        except Exception:
            pass
        try:
            df = tk.balance_sheet
            if df is not None and not df.empty:
                datasets.append(("balance", df, "annual"))
        except Exception:
            pass
        try:
            df = tk.quarterly_balance_sheet
            if df is not None and not df.empty:
                datasets.append(("balance", df, "quarterly"))
        except Exception:
            pass
        try:
            df = tk.cashflow
            if df is not None and not df.empty:
                datasets.append(("cashflow", df, "annual"))
        except Exception:
            pass
        try:
            df = tk.quarterly_cashflow
            if df is not None and not df.empty:
                datasets.append(("cashflow", df, "quarterly"))
        except Exception:
            pass

        for stmt, df, ptype in datasets:
            # df: index=item, columns=dates
            for col in df.columns:
                try:
                    pdate = pd.to_datetime(col).date()
                except Exception:
                    # yfinance sometimes has period columns as Period-like or strings
                    try:
                        pdate = pd.to_datetime(str(col)).date()
                    except Exception:
                        continue
                for item in df.index:
                    try:
                        val = df.at[item, col]
                    except Exception:
                        continue
                    if pd.isna(val):
                        continue
                    rows.append({
                        "ticker": t,
                        "period_end": pdate,
                        "period_type": ptype,
                        "statement": stmt,
                        "item": str(item),
                        "value": float(val),
                        "currency": fcur,
                    })

    if not rows:
        print("No financials fetched.")
        return

    df_all = pd.DataFrame(rows)
    # Remove existing rows for these tickers to avoid duplicates
    uniq_tickers = sorted(df_all["ticker"].unique().tolist())
    placeholders = ",".join([":t"+str(i) for i in range(len(uniq_tickers))])
    params = {"t"+str(i): v for i, v in enumerate(uniq_tickers)}
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table_name} WHERE ticker IN ({placeholders})"), params)
        df_all.to_sql(table_name, conn, if_exists="append", index=False)


def ensure_schema_per_mysql_spec(engine):
    try:
        dialect = engine.url.get_dialect().name
    except Exception:
        dialect = "sqlite"
    if dialect == "mysql":
        ddl_companies = """
        CREATE TABLE IF NOT EXISTS companies (
            ticker_code VARCHAR(10) NOT NULL COMMENT '銘柄コード',
            company_name VARCHAR(256) NOT NULL COMMENT '企業名',
            industry_name VARCHAR(100) COMMENT '業種名',
            market VARCHAR(50) COMMENT '市場区分',
            listing_date DATE COMMENT '上場日',
            fiscal_month INT COMMENT '決算月',
            PRIMARY KEY (ticker_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        ddl_prices = """
        CREATE TABLE IF NOT EXISTS fact_stock_daily (
            date DATE NOT NULL COMMENT '日付',
            ticker_code VARCHAR(10) NOT NULL COMMENT '銘柄コード',
            open DECIMAL(10, 2),
            high DECIMAL(10, 2),
            low DECIMAL(10, 2),
            close DECIMAL(10, 2),
            adj_close DECIMAL(10, 2),
            volume BIGINT,
            PRIMARY KEY (date, ticker_code),
            FOREIGN KEY (ticker_code) REFERENCES companies(ticker_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        ddl_fin = """
        CREATE TABLE IF NOT EXISTS fact_financials (
            ticker_code VARCHAR(10) NOT NULL COMMENT '銘柄コード',
            fiscal_year INT NOT NULL COMMENT '会計年度',
            quarter TINYINT NOT NULL COMMENT '四半期',
            net_sales BIGINT,
            operating_income BIGINT,
            net_income BIGINT,
            eps DECIMAL(10, 2),
            roe FLOAT,
            PRIMARY KEY (ticker_code, fiscal_year, quarter),
            FOREIGN KEY (ticker_code) REFERENCES companies(ticker_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        ddl_events = """
        CREATE TABLE IF NOT EXISTS fact_events (
            event_id INT AUTO_INCREMENT NOT NULL,
            event_date DATE NOT NULL,
            ticker_code VARCHAR(10) COMMENT '市場全体ならNULL',
            category VARCHAR(50) NOT NULL,
            title VARCHAR(256) NOT NULL,
            description TEXT,
            sentiment_score FLOAT,
            importance TINYINT,
            PRIMARY KEY (event_id),
            FOREIGN KEY (ticker_code) REFERENCES companies(ticker_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        ddl_glossary = """
        CREATE TABLE IF NOT EXISTS Glossary (
            TermID INT AUTO_INCREMENT NOT NULL,
            TermName VARCHAR(256) NOT NULL,
            Category VARCHAR(256) NOT NULL,
            Definition VARCHAR(1000) NOT NULL,
            Reading VARCHAR(100) NOT NULL,
            example TEXT NOT NULL,
            Details TEXT NOT NULL,
            PRIMARY KEY (TermID)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    else:
        ddl_companies = """
        CREATE TABLE IF NOT EXISTS companies (
            ticker_code TEXT NOT NULL,
            company_name TEXT NOT NULL,
            industry_name TEXT,
            market TEXT,
            listing_date DATE,
            fiscal_month INTEGER,
            PRIMARY KEY (ticker_code)
        );
        """
        ddl_prices = """
        CREATE TABLE IF NOT EXISTS fact_stock_daily (
            date DATE NOT NULL,
            ticker_code TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            adj_close REAL,
            volume INTEGER,
            PRIMARY KEY (date, ticker_code)
        );
        """
        ddl_fin = """
        CREATE TABLE IF NOT EXISTS fact_financials (
            ticker_code TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            net_sales INTEGER,
            operating_income INTEGER,
            net_income INTEGER,
            eps REAL,
            roe REAL,
            PRIMARY KEY (ticker_code, fiscal_year, quarter)
        );
        """
        ddl_events = """
        CREATE TABLE IF NOT EXISTS fact_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            event_date DATE NOT NULL,
            ticker_code TEXT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            sentiment_score REAL,
            importance INTEGER
        );
        """
        ddl_glossary = """
        CREATE TABLE IF NOT EXISTS Glossary (
            TermID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            TermName TEXT NOT NULL,
            Category TEXT NOT NULL,
            Definition TEXT NOT NULL,
            Reading TEXT NOT NULL,
            example TEXT NOT NULL,
            Details TEXT NOT NULL
        );
        """
    with engine.begin() as conn:
        for ddl in (ddl_companies, ddl_prices, ddl_fin, ddl_events, ddl_glossary):
            conn.execute(text(ddl))


def upsert_companies_from_yf(engine, tickers: List[str]):
    try:
        dialect = engine.url.get_dialect().name
    except Exception:
        dialect = "sqlite"
    rows = []
    for t in tickers:
        tk = yf.Ticker(t)
        try:
            info = tk.info or {}
        except Exception:
            info = {}
        ticker_code = t
        company_name = info.get("longName") or info.get("shortName") or t
        industry_name = info.get("industry") or info.get("sector")
        market = info.get("exchange") or info.get("market")
        listing_date = None
        if info.get("firstTradeDateEpochUtc"):
            try:
                listing_date = datetime.utcfromtimestamp(int(info.get("firstTradeDateEpochUtc"))).date()
            except Exception:
                listing_date = None
        fiscal_month = None
        # yfinance 'fiscalYearEnd' is like 1231 → month=12
        fy_end = info.get("fiscalYearEnd")
        if fy_end:
            try:
                fiscal_month = int(str(fy_end)) // 100
            except Exception:
                fiscal_month = None
        rows.append({
            "ticker_code": ticker_code,
            "company_name": company_name,
            "industry_name": industry_name,
            "market": market,
            "listing_date": listing_date,
            "fiscal_month": fiscal_month,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return
    with engine.begin() as conn:
        if dialect == "mysql":
            for _, r in df.iterrows():
                conn.execute(
                    text(
                        """
                        INSERT INTO companies (ticker_code, company_name, industry_name, market, listing_date, fiscal_month)
                        VALUES (:ticker_code, :company_name, :industry_name, :market, :listing_date, :fiscal_month)
                        ON DUPLICATE KEY UPDATE company_name=VALUES(company_name), industry_name=VALUES(industry_name), market=VALUES(market), listing_date=VALUES(listing_date), fiscal_month=VALUES(fiscal_month)
                        """
                    ),
                    r.to_dict(),
                )
        else:
            # SQLite: upsert via INSERT OR REPLACE
            for _, r in df.iterrows():
                conn.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO companies (ticker_code, company_name, industry_name, market, listing_date, fiscal_month)
                        VALUES (:ticker_code, :company_name, :industry_name, :market, :listing_date, :fiscal_month)
                        """
                    ),
                    r.to_dict(),
                )


def fetch_and_load_prices_to_fact(engine, tickers: List[str]):
    data = yf.download(
        tickers=tickers,
        period="10y",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=True,
    )
    frames = []
    if isinstance(data.columns, pd.MultiIndex):
        for t in tickers:
            if t not in data.columns.levels[0]:
                continue
            df_t = data[t].copy()
            if df_t.empty:
                continue
            df_t = df_t.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Adj Close":"adj_close","Volume":"volume"})
            df_t["ticker_code"] = t
            df_t["date"] = df_t.index.date
            frames.append(df_t[["date","ticker_code","open","high","low","close","adj_close","volume"]])
    else:
        t = tickers[0] if tickers else None
        df_t = data.copy()
        if not df_t.empty and t:
            df_t = df_t.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Adj Close":"adj_close","Volume":"volume"})
            df_t["ticker_code"] = t
            df_t["date"] = df_t.index.date
            frames.append(df_t[["date","ticker_code","open","high","low","close","adj_close","volume"]])
    if not frames:
        print("No price data downloaded.")
        return
    all_df = pd.concat(frames, ignore_index=True)
    # round to 2 decimals for DECIMAL(10,2)
    for c in ["open","high","low","close","adj_close"]:
        all_df[c] = pd.to_numeric(all_df[c], errors="coerce").round(2)
    all_df["volume"] = pd.to_numeric(all_df["volume"], errors="coerce")
    # drop rows where all OHLCV are NaN (yfinance sometimes returns a trailing empty row for today)
    all_df = all_df.dropna(subset=["open","high","low","close","adj_close","volume"], how="all")
    # ensure volume integer-like after filtering
    all_df["volume"] = all_df["volume"].astype("Int64")
    # Normalize date to ISO string to avoid subtle dtype differences
    all_df["date"] = pd.to_datetime(all_df["date"]).dt.strftime("%Y-%m-%d")
    # deduplicate by (ticker_code, date) preferring rows with more non-null fields
    value_cols = ["open","high","low","close","adj_close","volume"]
    all_df["_nonnull"] = all_df[value_cols].notna().sum(axis=1)
    all_df = (
        all_df.sort_values(["ticker_code","date","_nonnull"], ascending=[True, True, False])
              .drop_duplicates(subset=["ticker_code","date"], keep="first")
              .drop(columns=["_nonnull"])
    )
    # Upsert by dialect
    dialect = engine.dialect.name
    if dialect == "sqlite":
        # Use SQLite upsert to avoid UNIQUE constraint errors, and pre-delete per ticker for safety
        records = all_df[["date","ticker_code","open","high","low","close","adj_close","volume"]].to_dict(orient="records")
        with engine.begin() as conn:
            # pre-delete keeps table tidy if schema changed or duplicates existed
            for t in sorted({r["ticker_code"] for r in records}):
                conn.execute(text("DELETE FROM fact_stock_daily WHERE ticker_code = :t"), {"t": t})
            sql = text(
                """
                INSERT INTO fact_stock_daily
                    (date, ticker_code, open, high, low, close, adj_close, volume)
                VALUES (:date, :ticker_code, :open, :high, :low, :close, :adj_close, :volume)
                ON CONFLICT(date, ticker_code) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    adj_close=excluded.adj_close,
                    volume=excluded.volume
                """
            )
            # chunked executemany
            chunk = 2000
            for i in range(0, len(records), chunk):
                conn.execute(sql, records[i:i+chunk])
    else:
        # Fallback: delete-then-insert per ticker to avoid duplicates
        with engine.begin() as conn:
            uniq_pairs = all_df[["ticker_code","date"]].drop_duplicates()
            for t in uniq_pairs["ticker_code"].unique():
                conn.execute(text("DELETE FROM fact_stock_daily WHERE ticker_code = :t"), {"t": t})
            # Insert in chunks
            chunk = 100000
            for i in range(0, len(all_df), chunk):
                all_df.iloc[i:i+chunk].to_sql("fact_stock_daily", conn, if_exists="append", index=False)


def _lookup_any(df: pd.DataFrame, names: List[str]):
    for n in names:
        if n in df.index:
            return n
    return None


def fiscal_year_quarter(ts: pd.Timestamp, start_month: int = 1) -> tuple[int, int]:
    # Compute fiscal year and quarter with configurable fiscal year start (1-12)
    m = int(ts.month)
    y = int(ts.year)
    sm = max(1, min(12, int(start_month)))
    # Offset month into fiscal year
    offset = (m - sm) % 12
    q = (offset // 3) + 1
    # If month is before fiscal start, fiscal year is previous calendar year
    fy = y if m >= sm else y - 1
    return int(fy), int(q)


def fetch_and_load_financials_fact(engine, tickers: List[str], quarterly_only: bool = False, backfill_10y: bool = False, fiscal_start_month: int = 1):
    rows = []
    for t in tickers:
        tk = yf.Ticker(t)
        # quarterly and annual
        datasets = []
        try:
            fin_a = tk.financials
            if fin_a is not None and not fin_a.empty:
                datasets.append((fin_a, "annual"))
        except Exception:
            pass
        try:
            fin_q = tk.quarterly_financials
            if fin_q is not None and not fin_q.empty:
                datasets.append((fin_q, "quarterly"))
        except Exception:
            pass
        # balance for equity
        bs_a = None
        bs_q = None
        try:
            bs_a = tk.balance_sheet
        except Exception:
            pass
        try:
            bs_q = tk.quarterly_balance_sheet
        except Exception:
            pass
        # shares for EPS calc if needed
        shares = None
        try:
            info = tk.info or {}
            shares = info.get("sharesOutstanding")
        except Exception:
            shares = None

        for df, ptype in datasets:
            if quarterly_only and ptype != "quarterly":
                continue
            rev_key = _lookup_any(df, ["Total Revenue","TotalRevenue","Revenue"]) or ""
            op_key = _lookup_any(df, ["Operating Income","OperatingIncome"]) or ""
            ni_key = _lookup_any(df, ["Net Income","NetIncome"]) or ""
            eps_key = _lookup_any(df, ["Basic EPS","BasicEPS","Diluted EPS","DilutedEPS"]) or ""
            # equity for ROE
            if ptype == "annual" and isinstance(bs_a, pd.DataFrame):
                eq_df = bs_a
            else:
                eq_df = bs_q if isinstance(bs_q, pd.DataFrame) else None
            eq_key = _lookup_any(eq_df, ["Total Stockholder Equity","TotalStockholderEquity"]) if isinstance(eq_df, pd.DataFrame) else None

            for col in df.columns:
                try:
                    pdate = pd.to_datetime(col)
                except Exception:
                    continue
                if ptype == "quarterly":
                    year, qtr = fiscal_year_quarter(pdate, start_month=fiscal_start_month)
                else:
                    year, qtr = int(pdate.year), 0
                def safe_get(key):
                    try:
                        return None if not key else df.at[key, col]
                    except Exception:
                        return None
                net_sales = safe_get(rev_key)
                operating_income = safe_get(op_key)
                net_income = safe_get(ni_key)
                eps = safe_get(eps_key)
                if pd.isna(eps) or eps is None:
                    if shares and net_income and not pd.isna(net_income) and shares:
                        try:
                            eps = float(net_income)/float(shares)
                        except Exception:
                            eps = None
                roe = None
                if eq_key:
                    try:
                        equity = eq_df.at[eq_key, col]
                        if equity and not pd.isna(equity) and net_income and not pd.isna(net_income) and float(equity)!=0:
                            roe = float(net_income)/float(equity)
                    except Exception:
                        roe = None
                def to_int(v):
                    try:
                        return int(v) if v is not None and not pd.isna(v) else None
                    except Exception:
                        try:
                            return int(float(v))
                        except Exception:
                            return None
                def to_dec2(v):
                    try:
                        return round(float(v),2) if v is not None and not pd.isna(v) else None
                    except Exception:
                        return None
                rows.append({
                    "ticker_code": t,
                    "fiscal_year": year,
                    "quarter": qtr,
                    "net_sales": to_int(net_sales),
                    "operating_income": to_int(operating_income),
                    "net_income": to_int(net_income),
                    "eps": to_dec2(eps),
                    "roe": None if roe is None else float(roe),
                })
        # Additional source: merge quarterly income stmt and balance sheet
        try:
            inc_q = tk.quarterly_income_stmt
        except Exception:
            inc_q = None
        try:
            bs_q2 = tk.quarterly_balance_sheet
        except Exception:
            bs_q2 = None
        if isinstance(inc_q, pd.DataFrame) and not inc_q.empty and isinstance(bs_q2, pd.DataFrame) and not bs_q2.empty:
            try:
                merged = inc_q.T.merge(bs_q2.T, left_index=True, right_index=True, how="inner")
                for date_idx, row in merged.iterrows():
                    try:
                        ts = pd.to_datetime(date_idx)
                    except Exception:
                        continue
                    fy, fq = fiscal_year_quarter(ts, start_month=fiscal_start_month)
                    # Map fields with fallbacks
                    net_sales = row.get('Total Revenue')
                    if pd.isna(net_sales):
                        net_sales = row.get('Operating Revenue')
                    operating_income = row.get('Operating Income')
                    net_income = row.get('Net Income')
                    eps = row.get('Basic EPS')
                    if pd.isna(eps):
                        eps = row.get('Diluted EPS')
                    equity = row.get('Stockholders Equity')
                    if pd.isna(equity):
                        equity = row.get('Total Stockholder Equity')
                    roe = None
                    try:
                        if equity is not None and not pd.isna(equity) and equity != 0 and net_income is not None and not pd.isna(net_income):
                            roe = float(net_income) / float(equity) * 100.0
                    except Exception:
                        roe = None
                    rows.append({
                        "ticker_code": t,
                        "fiscal_year": int(fy),
                        "quarter": int(fq),
                        "net_sales": None if pd.isna(net_sales) else int(float(net_sales)),
                        "operating_income": None if pd.isna(operating_income) else int(float(operating_income)),
                        "net_income": None if pd.isna(net_income) else int(float(net_income)),
                        "eps": None if pd.isna(eps) else round(float(eps), 2),
                        "roe": None if roe is None or pd.isna(roe) else float(roe),
                    })
            except Exception:
                pass

        # Enrich with yfinance quarterly_earnings (Revenue/Earnings) and earnings dates (EPS)
        try:
            qe = tk.quarterly_earnings
        except Exception:
            qe = None
        try:
            ed = tk.get_earnings_dates(limit=40)
        except Exception:
            ed = None

        # normalize helper: compute FY and Q from a timestamp
        def _year_q_from_ts(ts: pd.Timestamp):
            return fiscal_year_quarter(ts, start_month=fiscal_start_month)

        # Build an index for quick overwrite of missing values
        existing = {}
        for r in rows:
            if r["ticker_code"] != t:
                continue
            existing[(r["fiscal_year"], r["quarter"])] = r

        # Fill from quarterly_earnings (columns: Revenue, Earnings)
        if isinstance(qe, pd.DataFrame) and not qe.empty:
            for idx, rec in qe.reset_index().iterrows():
                try:
                    ts = pd.to_datetime(rec[qe.index.name or 'Date'])
                except Exception:
                    continue
                fy, fq = _year_q_from_ts(ts)
                target = existing.get((fy, fq))
                if not target:
                    target = {"ticker_code": t, "fiscal_year": fy, "quarter": fq,
                              "net_sales": None, "operating_income": None, "net_income": None, "eps": None, "roe": None}
                    rows.append(target)
                    existing[(fy, fq)] = target
                # Revenue
                try:
                    rev = rec.get("Revenue")
                    if target.get("net_sales") in (None, float('nan')) and rev is not None and not pd.isna(rev):
                        target["net_sales"] = int(float(rev))
                except Exception:
                    pass
                # Earnings (approximate net income)
                try:
                    earn = rec.get("Earnings")
                    if target.get("net_income") in (None, float('nan')) and earn is not None and not pd.isna(earn):
                        target["net_income"] = int(float(earn))
                except Exception:
                    pass

        # Fill EPS from earnings dates
        if isinstance(ed, pd.DataFrame) and not ed.empty:
            # Expect columns like 'EPS Actual' or 'EPS Actual', 'Earnings Date'
            dt_col = None
            for c in ed.columns:
                if 'Earnings Date' in c or 'EarningsDate' in c or c.lower().startswith('earnings'):
                    dt_col = c
                    break
            if dt_col is None and not ed.index.empty:
                ed = ed.reset_index().rename(columns={ed.index.name or 'Date': 'Date'})
                dt_col = 'Date'
            if dt_col is not None:
                for _, rec in ed.iterrows():
                    try:
                        ts = pd.to_datetime(rec.get(dt_col))
                    except Exception:
                        continue
                    fy, fq = _year_q_from_ts(ts)
                    target = existing.get((fy, fq))
                    if not target:
                        target = {"ticker_code": t, "fiscal_year": fy, "quarter": fq,
                                  "net_sales": None, "operating_income": None, "net_income": None, "eps": None, "roe": None}
                        rows.append(target)
                        existing[(fy, fq)] = target
                    # EPS Actual / EPS Estimate columns
                    eps_val = None
                    for c in ["EPS Actual", "EPSActual", "ActualEPS", "EPS"]:
                        if c in ed.columns:
                            eps_val = rec.get(c)
                            break
                    if eps_val is not None and not pd.isna(eps_val):
                        target["eps"] = round(float(eps_val), 2)

        # Optionally create 10-year quarterly skeleton with NULL metrics
        if backfill_10y:
            try:
                # Build fiscal-quarter periods by sliding months
                end = pd.Timestamp.today().to_period('M')
                months = []
                for i in range(0, 120):  # 10 years * 12 months
                    mper = end - i
                    months.append(mper.to_timestamp('M'))
                # Take unique fiscal (year, quarter)
                seen = set()
                for ts in months:
                    fy, fq = fiscal_year_quarter(pd.Timestamp(ts), start_month=fiscal_start_month)
                    key = (fy, fq)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "ticker_code": t,
                        "fiscal_year": int(fy),
                        "quarter": int(fq),
                        "net_sales": None,
                        "operating_income": None,
                        "net_income": None,
                        "eps": None,
                        "roe": None,
                    })
            except Exception:
                pass
    if not rows:
        print("No financials for fact_financials.")
        return
    df_all = pd.DataFrame(rows)
    if not df_all.empty:
        # If skeleton + actuals exist, keep actuals (non-NULL) by dropping duplicates keeping last
        df_all = df_all.sort_values(by=["ticker_code","fiscal_year","quarter"]).drop_duplicates(subset=["ticker_code","fiscal_year","quarter"], keep="last")
    with engine.begin() as conn:
        # delete per ticker to avoid PK conflict
        for t in df_all["ticker_code"].unique():
            conn.execute(text("DELETE FROM fact_financials WHERE ticker_code=:t"), {"t": t})
        df_all.to_sql("fact_financials", conn, if_exists="append", index=False)


# ------------------------ EDGAR (SEC) enrichment for US tickers ------------------------
def _sec_headers(user_agent: str | None) -> dict:
    ua = user_agent or "sisukai-etl/0.1 (contact: unknown@example.com)"
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate", "Host": "data.sec.gov"}


def _load_ticker_cik_map(user_agent: str | None) -> dict:
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_sec_headers(user_agent), timeout=20)
        r.raise_for_status()
        data = r.json()  # {"0": {"cik_str":...,"ticker":"AAPL","title":"Apple Inc."}, ...}
        out = {}
        for _, v in data.items():
            out[str(v.get("ticker", "")).upper()] = f"{int(v.get('cik_str', 0)):010d}"
        return out
    except Exception:
        return {}


def _get_companyfacts(cik: str, user_agent: str | None) -> dict | None:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        r = requests.get(url, headers=_sec_headers(user_agent), timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _pick_units(fact: dict, unit_key: str) -> list:
    if not fact:
        return []
    units = fact.get("units", {})
    for key in (unit_key, "USD"):
        vals = units.get(key)
        if vals:
            return vals
    # EPS often in USD/share
    for k, vals in units.items():
        if "/" in k:
            return vals
    return []


def _frame_to_fyq(item: dict, fiscal_start_month: int) -> tuple[int | None, int | None]:
    # Prefer fp/fy if present; else derive from end date
    fy = item.get("fy")
    fp = item.get("fp")  # e.g., Q1/Q2/Q3/Q4/FY
    if fy and fp and isinstance(fy, int) and isinstance(fp, str) and fp.upper().startswith("Q"):
        try:
            q = int(fp[1])
            return int(fy), int(q)
        except Exception:
            pass
    # Fallback: end date
    try:
        end = pd.to_datetime(item.get("end"))
        fy, fq = fiscal_year_quarter(end, start_month=fiscal_start_month)
        return int(fy), int(fq)
    except Exception:
        return None, None


def fetch_and_upsert_financials_from_edgar(engine, tickers: List[str], fiscal_start_month: int, user_agent: str | None, delay_sec: float = 0.7):
    cik_map = _load_ticker_cik_map(user_agent)
    if not cik_map:
        print("EDGAR ticker->CIK map unavailable; skipping EDGAR enrichment.")
        return
    target_facts = {
        "net_sales": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "operating_income": ["OperatingIncomeLoss"],
        "net_income": ["NetIncomeLoss"],
        "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
        "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    }
    all_rows = []
    for t in tickers:
        cik = cik_map.get(t.upper())
        if not cik:
            continue
        facts = _get_companyfacts(cik, user_agent)
        time.sleep(delay_sec)
        if not facts:
            continue
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        # Collect by (fy, fq)
        by_period: dict[tuple[int, int], dict] = {}
        for key, gaap_fact in us_gaap.items():
            # Map into our target keys if relevant
            mapped_key = None
            for our, cand in target_facts.items():
                if key in cand:
                    mapped_key = our
                    break
            if not mapped_key:
                continue
            # Pick USD units
            vals = _pick_units(gaap_fact, "USD")
            for item in vals:
                fy, fq = _frame_to_fyq(item, fiscal_start_month)
                if not fy or not fq or fq not in (1, 2, 3, 4):
                    continue
                slot = by_period.setdefault((fy, fq), {"ticker_code": t, "fiscal_year": fy, "quarter": fq,
                                                      "net_sales": None, "operating_income": None, "net_income": None, "eps": None, "roe": None, "equity": None})
                try:
                    v = item.get("val")
                    if v is None or pd.isna(v):
                        continue
                    if mapped_key == "eps":
                        slot["eps"] = round(float(v), 2)
                    elif mapped_key == "equity":
                        slot["equity"] = float(v)
                    else:
                        slot[mapped_key] = int(float(v))
                except Exception:
                    pass
        # Compute ROE if possible
        for (fy, fq), slot in by_period.items():
            try:
                ni = slot.get("net_income")
                eq = slot.get("equity")
                if ni is not None and eq not in (None, 0):
                    slot["roe"] = float(ni) / float(eq) * 100.0
            except Exception:
                pass
            slot.pop("equity", None)
            all_rows.append(slot)

    if not all_rows:
        print("No EDGAR rows to upsert.")
        return
    df = pd.DataFrame(all_rows)
    # Upsert per (ticker, fy, q): delete matching keys then insert
    with engine.begin() as conn:
        for (t, fy, q) in df[["ticker_code","fiscal_year","quarter"]].drop_duplicates().itertuples(index=False, name=None):
            conn.execute(text("DELETE FROM fact_financials WHERE ticker_code=:t AND fiscal_year=:fy AND quarter=:q"), {"t": t, "fy": int(fy), "q": int(q)})
        df[["ticker_code","fiscal_year","quarter","net_sales","operating_income","net_income","eps","roe"]].to_sql("fact_financials", conn, if_exists="append", index=False)


def fetch_and_upsert_financials_from_edinet(engine, tickers: List[str], fiscal_start_month: int, focus_dates: bool = False):
    print("EDINET enrichment started (JP filings, ~10y). This may take a while...")
    # Map JP tickers to possible filer names via yfinance
    name_map = {}
    # Map JP tickers to TSE 4-digit code (e.g., 7203 from 7203.T)
    jp_code_map = {}
    # Map JP tickers to EDINET code via external CSV (fallback if unavailable)
    ticker_to_edinet_map: dict[str, str] = {}
    # Optional JP submitter name map (Japanese)
    jp_submitter_name_map: dict[str, str] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info or {}
        except Exception:
            info = {}
        nm = info.get("longName") or info.get("shortName") or t
        name_map[t] = str(nm)
        if ".T" in t.upper():
            try:
                jp_code_map[t] = str(int(t.split(".")[0]))  # strip leading zeros if any
            except Exception:
                jp_code_map[t] = t.split(".")[0]
        time.sleep(0.1)

    # Prefer local EDINET code list if present
    local_csv = os.path.join(os.getcwd(), "EdinetcodeDlInfo.csv")
    loaded_local = False
    if os.path.isfile(local_csv):
        try:
            try:
                df_list = pd.read_csv(local_csv, encoding="utf-8", skiprows=1)
            except UnicodeDecodeError:
                df_list = pd.read_csv(local_csv, encoding="cp932", skiprows=1)
            for _, row in df_list.iterrows():
                sec_code = str(row.get("証券コード", ""))
                edinet_code = str(row.get("ＥＤＩＮＥＴコード", ""))
                jp_name = str(row.get("提出者名", ""))
                if not (sec_code and edinet_code.startswith("E")):
                    continue
                # 例: 72030 -> 7203.T
                if len(sec_code) >= 4:
                    clean_ticker = sec_code[:4] + ".T"
                    ticker_to_edinet_map[clean_ticker] = edinet_code
                    if jp_name:
                        jp_submitter_name_map[clean_ticker] = jp_name
            if ticker_to_edinet_map:
                print(f"EDINET: loaded local code list, mapped tickers: {len(ticker_to_edinet_map)}")
                loaded_local = True
        except Exception:
            pass
    if not loaded_local:
        # Fallback: external EDINET mapping list (community-maintained)
        url_csv = "https://raw.githubusercontent.com/prokuma/disclosure-edinet-list/master/list.csv"
        try:
            df_list = pd.read_csv(url_csv)
            for _, row in df_list.iterrows():
                sec_code_raw = str(row.get("sec_code", row.get("Code", "")))
                edinet_code = str(row.get("edinet_code", row.get("EdinetCode", "")))
                jp_name = str(row.get("name_jp", row.get("SubmitterName", "")))
                if not edinet_code:
                    continue
                if sec_code_raw:
                    if len(sec_code_raw) == 5 and sec_code_raw.endswith("0"):
                        clean_ticker = sec_code_raw[:-1] + ".T"
                    elif len(sec_code_raw) == 4:
                        clean_ticker = sec_code_raw + ".T"
                    else:
                        continue
                    ticker_to_edinet_map[clean_ticker] = edinet_code
                    if jp_name:
                        jp_submitter_name_map.setdefault(clean_ticker, jp_name)
            if ticker_to_edinet_map:
                print(f"EDINET: loaded external code list, mapped tickers: {len(ticker_to_edinet_map)}")
        except Exception:
            pass

    base = "https://api.edinet-fsa.go.jp/api/v2"
    edinet_api_key = os.getenv("EDINET_API_KEY") or os.getenv("SISUKAI_EDINET_API_KEY")
    headers = {"User-Agent": "sisukai-edinet/0.1"}
    if edinet_api_key:
        headers["Ocp-Apim-Subscription-Key"] = edinet_api_key

    def list_docs(date_str: str) -> list:
        url = f"{base}/documents.json"
        params = {"date": date_str, "type": 2}
        if edinet_api_key:
            params["Subscription-Key"] = edinet_api_key
        for _ in range(2):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=30)
                r.raise_for_status()
                data = r.json()
                return data.get("results", []) or []
            except Exception:
                time.sleep(0.5)
        return []

    def list_docs_by_edi(date_str: str, edicode: str) -> list:
        # Filtered listing by EDINET code (if API supports it)
        url = f"{base}/documents.json"
        params = {"date": date_str, "type": 2, "edinetCode": edicode}
        if edinet_api_key:
            params["Subscription-Key"] = edinet_api_key
        for _ in range(2):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=30)
                if r.status_code == 400:
                    # parameter may not be supported, break fast
                    break
                r.raise_for_status()
                data = r.json()
                return data.get("results", []) or []
            except Exception:
                time.sleep(0.3)
        return []

    def dl_zip(doc_id: str) -> bytes | None:
        url = f"{base}/documents/{doc_id}"
        params = {"type": 1}
        if edinet_api_key:
            params["Subscription-Key"] = edinet_api_key
        for _ in range(2):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=60)
                r.raise_for_status()
                return r.content
            except Exception:
                time.sleep(0.5)
        return None

    def get_doc_meta(doc_id: str) -> dict:
        # EDINET v2: metadata JSON
        url = f"{base}/documents/{doc_id}"
        params = {"type": 2}
        if edinet_api_key:
            params["Subscription-Key"] = edinet_api_key
        for _ in range(2):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=30)
                r.raise_for_status()
                # Some deployments return JSON, others return bytes JSON
                try:
                    return r.json()
                except Exception:
                    import json as _json
                    return _json.loads(r.content.decode("utf-8", errors="ignore"))
            except Exception:
                time.sleep(0.5)
        return {}

    # EDINET v2 document type codes (quarterly/annual)
    target_doc_types = set([
        "120",  # 有価証券報告書
        "130",  # 訂正有価証券報告書
        "140",  # 四半期報告書
        # "150",  # 訂正四半期報告書（必要なら追加）
    ])

    # Collect rows here
    all_rows = []

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=365*10 + 30)
    checked_days = 0
    # Build date list when focus_dates is enabled (months 2,5,8,11; days 1-15; weekdays only)
    focus_list = []
    if focus_dates:
        for y in range(today.year, today.year - 10, -1):
            for m in (2, 5, 8, 11):
                for d in range(1, 16):
                    try:
                        dt = datetime(y, m, d).date()
                    except Exception:
                        continue
                    if dt > today or dt < start_date:
                        continue
                    if dt.weekday() >= 5:
                        continue
                    focus_list.append(dt)
        focus_list.sort(reverse=True)

    # Workaround for arelle on Python 3.11+: collections.* moved to collections.abc
    try:
        import collections
        import collections.abc as _abc
        if not hasattr(collections, "MutableSet"):
            collections.MutableSet = _abc.MutableSet  # type: ignore[attr-defined]
        if not hasattr(collections, "MutableMapping"):
            collections.MutableMapping = _abc.MutableMapping  # type: ignore[attr-defined]
        if not hasattr(collections, "MutableSequence"):
            collections.MutableSequence = _abc.MutableSequence  # type: ignore[attr-defined]
    except Exception:
        pass
    from arelle import Cntlr

    def parse_xbrl_and_extract(xbrl_path: str, ticker: str):
        ctrl = Cntlr.Cntlr(logFileName=None)
        model = None
        try:
            model = ctrl.modelManager.load(xbrl_path)
        except Exception:
            return []
        if model is None:
            return []
        # Candidate localNames (without namespace) for concepts
        cand = {
            "net_sales": {"NetSales", "Revenue", "OperatingRevenue", "SalesRevenueNet"},
            "operating_income": {"OperatingIncome", "OperatingIncomeLoss"},
            "net_income": {"ProfitLoss", "ProfitLossAttributableToOwnersOfParent", "NetIncomeLoss"},
            "eps": {"EarningsPerShareDiluted", "EarningsPerShareBasic"},
            "equity": {"Equity", "EquityAttributableToOwnersOfParent", "StockholdersEquity"},
        }
        # Aggregate facts by (fy, fq)
        out = {}
        for f in getattr(model, "facts", []) or []:
            try:
                ln = f.qname.localName if hasattr(f, "qname") else None
                if not ln:
                    continue
                key = None
                for k, names in cand.items():
                    if ln in names:
                        key = k
                        break
                if not key:
                    continue
                ctx = f.context
                if not ctx:
                    continue
                # Prefer endDatetime, else instantDatetime
                dt = getattr(ctx, "endDatetime", None) or getattr(ctx, "instantDatetime", None)
                if not dt:
                    continue
                fy, fq = fiscal_year_quarter(pd.Timestamp(dt), start_month=fiscal_start_month)
                if fq not in (1,2,3,4):
                    continue
                slot = out.setdefault((fy, fq), {"ticker_code": ticker, "fiscal_year": int(fy), "quarter": int(fq),
                                                  "net_sales": None, "operating_income": None, "net_income": None, "eps": None, "roe": None, "equity": None})
                val = None
                try:
                    val = float(f.value)
                except Exception:
                    try:
                        val = float(str(f.value).replace(",", ""))
                    except Exception:
                        val = None
                if val is None:
                    continue
                if key == "eps":
                    slot["eps"] = round(val, 2)
                elif key == "equity":
                    slot["equity"] = val
                else:
                    slot[key] = int(val)
            except Exception:
                continue
        # Compute ROE
        rows = []
        for (fy, fq), slot in out.items():
            try:
                ni = slot.get("net_income")
                eq = slot.get("equity")
                if ni is not None and eq not in (None, 0):
                    slot["roe"] = float(ni) / float(eq) * 100.0
            except Exception:
                pass
            slot.pop("equity", None)
            rows.append(slot)
        return rows

    # Iterate dates: focus list when enabled; otherwise daily backward from today
    def _iter_dates():
        if focus_dates:
            for dt in focus_list:
                yield dt.strftime("%Y-%m-%d")
        else:
            cur = today
            step = timedelta(days=1)
            while cur >= start_date:
                yield cur.strftime("%Y-%m-%d")
                cur -= step

    for date_str in _iter_dates():
        # Try filtered per ticker when we have EDINET code; this reduces matching ambiguity
        docs = []
        edis = [ticker_to_edinet_map.get(t) for t in tickers if ticker_to_edinet_map.get(t)]
        if edis:
            for edi in set(edis):
                d_sub = list_docs_by_edi(date_str, edi)
                if d_sub:
                    docs.extend(d_sub)
                    time.sleep(0.05)
        # Fallback to full list if nothing found for any ticker
        if not docs:
            docs = list_docs(date_str)
        checked_days += 1
        if docs:
            matched_today = 0
            # For each JP ticker, find matching documents of target doc types
            for d in docs:
                try:
                    # List payload may be sparse; fetch metadata per doc to get reliable identifiers
                    doc_id = d.get("docID")
                    if not doc_id:
                        continue
                    meta = get_doc_meta(doc_id)
                    doc_type = str(meta.get("docTypeCode") or d.get("docTypeCode") or "").strip()
                    # possible name fields
                    filer = (
                        meta.get("filerName")
                        or meta.get("submitterName")
                        or meta.get("issuerName")
                        or d.get("filerName")
                        or d.get("submitterName")
                        or d.get("issuerName")
                        or ""
                    )
                    # edinet code in the document (key may vary by API version)
                    doc_edi = (
                        meta.get("edinetCode")
                        or meta.get("edinet_code")
                        or meta.get("filerEdinetCode")
                        or meta.get("submitterEdinetCode")
                        or meta.get("issuerEdinetCode")
                        or d.get("edinetCode")
                        or d.get("edinet_code")
                        or d.get("filerEdinetCode")
                        or d.get("submitterEdinetCode")
                        or d.get("issuerEdinetCode")
                        or ""
                    )
                    doc_edi = str(doc_edi).strip()
                    # Prefer matching by security code when available (possible key variants)
                    doc_sec = (
                        meta.get("secCode")
                        or meta.get("securityCode")
                        or meta.get("jpcoCode")
                        or d.get("secCode")
                        or d.get("securityCode")
                        or d.get("jpcoCode")
                        or ""
                    )
                    doc_sec = str(doc_sec).strip()
                    if not (doc_edi or doc_sec or filer):
                        print(f"EDINET: meta empty for {doc_id}")
                    # Diagnostics: if edinetCode matches our targets but type not targeted, log it once
                    if doc_edi:
                        target_tickers = [t for t, e in ticker_to_edinet_map.items() if e == doc_edi and t in tickers]
                        if target_tickers and doc_type and doc_type not in target_doc_types:
                            print(f"EDINET: {date_str} doc for {','.join(target_tickers)} has non-target type {doc_type} (docID={doc_id})")
                    if doc_type and doc_type not in target_doc_types:
                        continue
                    for t, nm in name_map.items():
                        if ".T" not in t.upper():
                            # JP対象のみ
                            continue
                        code_ok = False
                        edi_ok = False
                        # EDINET code match
                        if doc_edi:
                            mapped = ticker_to_edinet_map.get(t)
                            if mapped and mapped == doc_edi:
                                edi_ok = True
                        if doc_sec:
                            target_code = jp_code_map.get(t)
                            if target_code and (doc_sec == target_code or doc_sec.zfill(4) == target_code.zfill(4)):
                                code_ok = True
                        name_ok_en = nm and (str(nm) in str(filer))
                        jp_nm = jp_submitter_name_map.get(t)
                        name_ok_jp = jp_nm and (str(jp_nm) in str(filer))
                        if edi_ok or code_ok or name_ok_en or name_ok_jp:
                            # Download zip
                            content = dl_zip(doc_id)
                            time.sleep(0.8)
                            if not content:
                                continue
                            # Extract XBRL files to temp and parse
                            try:
                                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                                    with tempfile.TemporaryDirectory() as td:
                                        xbrls = []
                                        for n in zf.namelist():
                                            if n.lower().endswith(".xbrl") and "/PublicDoc/" in n:
                                                xbrls.append(n)
                                        if not xbrls:
                                            # fallback to any .xbrl
                                            xbrls = [n for n in zf.namelist() if n.lower().endswith(".xbrl")]
                                        if not xbrls:
                                            continue
                                        # pick the first
                                        target_name = xbrls[0]
                                        zf.extract(target_name, td)
                                        xbrl_path = os.path.join(td, target_name)
                                        rows = parse_xbrl_and_extract(xbrl_path, t)
                                        if rows:
                                            all_rows.extend(rows)
                                            matched_today += 1
                            except Exception:
                                continue
                except Exception:
                    continue
            if matched_today == 0:
                print(f"EDINET: {date_str} no matched docs (checked {len(docs)})")
        # progress throttle
        time.sleep(0.2)

    if not all_rows:
        print("EDINET: no rows parsed. Skipping upsert.")
        return
    df = pd.DataFrame(all_rows)
    # Dedup keep last
    df = df.sort_values(["ticker_code","fiscal_year","quarter"]).drop_duplicates(["ticker_code","fiscal_year","quarter"], keep="last")
    with engine.begin() as conn:
        for (t, fy, q) in df[["ticker_code","fiscal_year","quarter"]].drop_duplicates().itertuples(index=False, name=None):
            conn.execute(text("DELETE FROM fact_financials WHERE ticker_code=:t AND fiscal_year=:fy AND quarter=:q"), {"t": t, "fy": int(fy), "q": int(q)})
        df[["ticker_code","fiscal_year","quarter","net_sales","operating_income","net_income","eps","roe"]].to_sql("fact_financials", conn, if_exists="append", index=False)
    print(f"EDINET enrichment done. Upserted rows: {len(df)}")

def upsert_companies(session, tickers: List[str]):
    # Fetch basic info from yfinance for currency and name where possible
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            currency = getattr(info, "currency", None) if hasattr(info, "currency") else info.get("currency") if isinstance(info, dict) else None
        except Exception:
            currency = None
        try:
            info_d = yf.Ticker(t).info or {}
        except Exception:
            info_d = {}
        name = info_d.get("longName") or info_d.get("shortName")
        country = info_d.get("country")

        existing = session.get(Company, t)
        if existing:
            # update minimal fields if newly available
            if name and not existing.name:
                existing.name = name
            if country and not existing.country:
                existing.country = country
            if currency and not existing.currency:
                existing.currency = currency
        else:
            session.add(Company(ticker=t, name=name, country=country, currency=currency))
    session.commit()


def fetch_and_load_prices(engine, tickers: List[str]):
    # Use yf.download for efficiency
    print(f"Downloading 10 years daily OHLCV for {len(tickers)} tickers...")
    data = yf.download(
        tickers=tickers,
        period="10y",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=True,
    )

    # Normalize to a flat DataFrame with columns: ticker, date, open, high, low, close, adj_close, volume
    frames = []
    # If only one ticker, yfinance returns single-index columns
    if isinstance(data.columns, pd.MultiIndex):
        for t in tickers:
            if t not in data.columns.levels[0]:
                continue
            df_t = data[t].copy()
            if df_t.empty:
                continue
            df_t = df_t.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adj_close",
                    "Volume": "volume",
                }
            )
            df_t["ticker"] = t
            df_t["date"] = df_t.index.date
            frames.append(df_t[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]])
    else:
        # Single ticker case
        t = tickers[0] if tickers else None
        df_t = data.copy()
        if not df_t.empty and t:
            df_t = df_t.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adj_close",
                    "Volume": "volume",
                }
            )
            df_t["ticker"] = t
            df_t["date"] = df_t.index.date
            frames.append(df_t[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]])

    if not frames:
        print("No data downloaded.")
        return

    all_df = pd.concat(frames, ignore_index=True)
    # Drop rows without close to avoid invalid inserts
    all_df = all_df.dropna(subset=["close"]) 

    # Write to DB using pandas to_sql for speed
    with engine.begin() as conn:
        all_df.to_sql("prices_daily", conn, if_exists="append", index=False)

    # Optional: de-duplicate in case of reruns
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM prices_daily
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM prices_daily
                    GROUP BY ticker, date
                )
                """
            )
        )


def main():
    parser = argparse.ArgumentParser(description="Create DB and fetch 10y OHLCV")
    parser.add_argument("--only", nargs="*", help="Optional list of tickers to fetch only these")
    parser.add_argument("--schema-only", action="store_true", help="Apply Excel schema only and exit")
    parser.add_argument("--db-url", help="SQLAlchemy DB URL (e.g. mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4)")
    parser.add_argument("--financials", action="store_true", help="Also fetch and load financial statements")
    parser.add_argument("--financials-quarterly-only", action="store_true", help="Load only quarterly financials (exclude annual)")
    parser.add_argument("--financials-backfill-10y", action="store_true", help="Backfill 10 years of quarterly skeleton rows with NULLs where data is missing")
    parser.add_argument("--fiscal-start-month", type=int, default=1, help="Fiscal year start month (1-12). Use 4 for Japan FY.")
    parser.add_argument("--fin-table", default="financials", help="Financials table name (default: financials)")
    parser.add_argument("--skip-excel-schema", action="store_true", help="Skip applying Excel-based schema adjustments")
    parser.add_argument("--use-edgar", action="store_true", help="For US tickers, enrich fundamentals from SEC EDGAR (10-Q/10-K companyfacts API)")
    parser.add_argument("--use-edinet", action="store_true", help="For JP tickers, enrich fundamentals from EDINET (XBRL). Experimental: slow, partial coverage.")
    parser.add_argument("--edinet-focus-dates", action="store_true", help="Scan only concentrated dates (2/5/8/11 months, days 1-15, weekdays) for EDINET v2")
    parser.add_argument("--sec-user-agent", default=None, help="Custom User-Agent for SEC API, e.g. 'Your Name your@email.com'")
    args = parser.parse_args()

    # Full default list
    tickers = [
        "9984.T","7203.T","8306.T","6758.T","7751.T","9983.T","7974.T","9432.T","8035.T","6861.T",
        "4502.T","7201.T","7267.T","4901.T","9434.T","8267.T","8031.T","8411.T","8591.T","7205.T",
        "8604.T","6869.T","4503.T","8058.T","9987.T","6981.T","7979.T","4063.T","5947.T","6902.T",
        "7012.T","7011.T","9101.T","9020.T","9021.T","9434.T",
        "NVDA","INTC","AAPL","MSFT","AMZN","TSLA","GOOGL","META","NFLX","CRM","V","MA","JPM","BAC","DIS","CSCO","ADBE","PYPL","TXN"
    ]

    db_url = args.db_url or os.getenv("SISUKAI_DB_URL")
    engine = init_db(db_url)
    # Apply Excel-defined schema if available (optional)
    if not args.skip_excel_schema:
        excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "sisukai.xlsx"))
        apply_excel_schema_if_present(excel_path, engine)
    # Ensure schema per provided MySQL spec (takes precedence)
    ensure_schema_per_mysql_spec(engine)
    # If only applying schema, exit BEFORE any data writes
    if args.schema_only:
        print("Schema applied from DDL (and Excel if enabled). Exit due to --schema-only.")
        return
    # Proceed with data upsert/load
    target = args.only if args.only else tickers
    upsert_companies_from_yf(engine, target)
    fetch_and_load_prices_to_fact(engine, target)
    if args.financials:
        fetch_and_load_financials_fact(
            engine,
            target,
            quarterly_only=args.financials_quarterly_only,
            backfill_10y=args.financials_backfill_10y,
            fiscal_start_month=args.fiscal_start_month,
        )
        if args.use_edgar:
            fetch_and_upsert_financials_from_edgar(
                engine,
                target,
                fiscal_start_month=args.fiscal_start_month,
                user_agent=args.sec_user_agent,
            )
        if args.use_edinet:
            fetch_and_upsert_financials_from_edinet(
                engine,
                target,
                fiscal_start_month=args.fiscal_start_month,
                focus_dates=args.edinet_focus_dates,
            )
    print(f"Done. Database created at: {get_db_path()}")


if __name__ == "__main__":
    main()
