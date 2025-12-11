import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse

# DB設定
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def get_companies_list():
    """ フロントのプルダウン用に企業リストを返す """
    engine = get_db_engine()
    query = "SELECT ticker_code, company_name FROM companies"
    df = pd.read_sql(query, engine)
    return df.to_dict(orient='records')

def run_simulation_logic(data):
    """
    シミュレーション実行のコアロジック
    data = {
        "initial_investment": 1000000,
        "monthly_investment": 50000,
        "tickers": ["7203.T", "AAPL"],
        "start_date": "2015-01-01",
        "end_date": "2024-12-31"
    }
    """
    engine = get_db_engine()
    
    tickers = data.get('tickers', [])
    start_date = data.get('start_date', '2015-01-01')
    end_date = data.get('end_date', '2025-12-31')
    initial_inv = float(data.get('initial_investment', 0))
    monthly_inv = float(data.get('monthly_investment', 0))

    if not tickers:
        return {"error": "No tickers selected"}

    # -------------------------------------------------
    # 1. 株価データの取得
    # -------------------------------------------------
    # 選択された銘柄の期間中のデータを取得
    tickers_str = "', '".join(tickers)
    query_stock = f"""
        SELECT date, ticker_code, close 
        FROM factstock_daily 
        WHERE ticker_code IN ('{tickers_str}')
          AND date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY date ASC
    """
    df = pd.read_sql(query_stock, engine)
    
    # 日付をDatetime型に変換
    df['date'] = pd.to_datetime(df['date'])
    
    # ピボットテーブル化（行:日付, 列:銘柄, 値:終値）
    df_pivot = df.pivot(index='date', columns='ticker_code', values='close')
    
    # 欠損値は前日の値で埋める（土日祝対策）
    df_pivot = df_pivot.fillna(method='ffill')
    # それでも無い（上場前など）は0にするか除外するが、今回はそのまま
    
    # -------------------------------------------------
    # 2. シミュレーション計算 (簡易版: 等分投資)
    # -------------------------------------------------
    # 毎月の積立額を銘柄数で割る
    inv_per_ticker = monthly_inv / len(tickers)
    initial_per_ticker = initial_inv / len(tickers)
    
    # 保有株数管理
    holdings = {t: 0.0 for t in tickers}
    
    # 初期投資 (開始日時点の株価で購入)
    if not df_pivot.empty:
        first_date = df_pivot.index[0]
        for t in tickers:
            if t in df_pivot.columns and pd.notna(df_pivot.loc[first_date, t]):
                price = df_pivot.loc[first_date, t]
                if price > 0:
                    holdings[t] += initial_per_ticker / price

    # 日次ループ用の結果リスト
    daily_result = []
    
    # 月次積立の判定用 (YYYY-MMが変わったら投資)
    last_month = None
    
    total_invested = initial_inv

    for date, row in df_pivot.iterrows():
        current_month = date.strftime('%Y-%m')
        
        # 月が変わったら積立投資 (毎月1回)
        if last_month and current_month != last_month:
            total_invested += monthly_inv
            for t in tickers:
                if t in row and pd.notna(row[t]) and row[t] > 0:
                    holdings[t] += inv_per_ticker / row[t]
        
        last_month = current_month
        
        # 現在の資産評価額計算
        current_total_value = 0
        breakdown = {}
        
        for t in tickers:
            if t in row and pd.notna(row[t]):
                val = holdings[t] * row[t]
                current_total_value += val
                breakdown[t] = val
        
        daily_result.append({
            "date": date.strftime('%Y-%m-%d'),
            "total_assets": round(current_total_value),
            "invested_amount": round(total_invested),
            # "breakdown": breakdown # 内訳が必要ならコメントアウト解除
        })

    # -------------------------------------------------
    # 3. 関連イベントの取得
    # -------------------------------------------------
    # チャートに表示するため、その期間の選択銘柄 + 市場全体のイベントを取得
    query_events = f"""
        SELECT event_date, ticker_code, title, description, sentiment_score 
        FROM fact_events 
        WHERE (ticker_code IN ('{tickers_str}') OR ticker_code IS NULL)
          AND event_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY event_date ASC
    """
    df_events = pd.read_sql(query_events, engine)
    events_list = []
    for _, row in df_events.iterrows():
        events_list.append({
            "date": row['event_date'].strftime('%Y-%m-%d'),
            "ticker": row['ticker_code'] if row['ticker_code'] else "Market",
            "title": row['title'],
            "description": row['description'],
            "sentiment": row['sentiment_score']
        })

    return {
        "graph_data": daily_result,
        "events": events_list,
        "summary": {
            "final_assets": daily_result[-1]["total_assets"] if daily_result else 0,
            "total_invested": daily_result[-1]["invested_amount"] if daily_result else 0,
            "return_rate": round((daily_result[-1]["total_assets"] / daily_result[-1]["invested_amount"] * 100) - 100, 2) if daily_result and daily_result[-1]["invested_amount"] > 0 else 0
        }
    }