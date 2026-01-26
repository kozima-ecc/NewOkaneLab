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
    all_df["volume"] = pd.to_numeric(all_df["volume"], errors="coerce").astype("Int64")
    with engine.begin() as conn:
        # delete overlapping rows to avoid PK conflicts
        uniq_pairs = all_df[["ticker_code","date"]].drop_duplicates()
        # For performance, delete per ticker range
        for t in uniq_pairs["ticker_code"].unique():
            conn.execute(text("DELETE FROM fact_stock_daily WHERE ticker_code = :t"), {"t": t})
        all_df.to_sql("fact_stock_daily", conn, if_exists="append", index=False)


def _lookup_any(df: pd.DataFrame, names: List[str]):
    for n in names:
        if n in df.index:
            return n
    return None


def fetch_and_load_financials_fact(engine, tickers: List[str], quarterly_only: bool = False):
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
                year = int(pdate.year)
                qtr = int(((pdate.month-1)//3)+1) if ptype=="quarterly" else 0
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
    if not rows:
        print("No financials for fact_financials.")
        return
    df_all = pd.DataFrame(rows)
    with engine.begin() as conn:
        # delete per ticker to avoid PK conflict
        for t in df_all["ticker_code"].unique():
            conn.execute(text("DELETE FROM fact_financials WHERE ticker_code=:t"), {"t": t})
        df_all.to_sql("fact_financials", conn, if_exists="append", index=False)


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
    parser.add_argument("--fin-table", default="financials", help="Financials table name (default: financials)")
    parser.add_argument("--skip-excel-schema", action="store_true", help="Skip applying Excel-based schema adjustments")
    args = parser.parse_args()

    # Full default list
    tickers = [
        "9984.T","7203.T","8306.T","6758.T","7751.T","9983.T","7974.T","9432.T","8035.T","6861.T",
        "4502.T","7201.T","7267.T","4901.T","9434.T","8267.T","8031.T","8411.T","8591.T","7205.T",
        "8604.T","6869.T","4503.T","8058.T","9987.T","6981.T","7979.T","4063.T","5947.T","6902.T",
        "7012.T","7011.T","9101.T","9020.T","9021.T",
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
        fetch_and_load_financials_fact(engine, target, quarterly_only=args.financials_quarterly_only)
    print(f"Done. Database created at: {get_db_path()}")


if __name__ == "__main__":
    main()
