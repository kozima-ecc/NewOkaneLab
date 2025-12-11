import pandas as pd
import math

def get_companies_list(engine):
    """ 企業リストを取得して辞書リストで返す """
    query = "SELECT ticker_code, company_name, industry_name, market FROM companies"
    try:
        df = pd.read_sql(query, engine)
        return df.to_dict(orient='records')
    except Exception as e:
        raise e

def run_simulation_logic(data, engine):
    """
    シミュレーション実行ロジック
    data: フロントからの入力JSON
    engine: SQLAlchemyのDBエンジン
    """
    tickers = data.get('tickers', [])
    start_date = data.get('start_date', '2015-01-01')
    end_date = data.get('end_date', '2024-12-31')
    
    try:
        initial_inv = float(data.get('initial_investment', 0))
        monthly_inv = float(data.get('monthly_investment', 0))
    except ValueError:
        return {"error": "金額は数値で指定してください"}

    if not tickers:
        return {"error": "銘柄が選択されていません"}

    # --- A. 株価データの取得 ---
    tickers_str = "', '".join(tickers)
    query_stock = f"""
        SELECT date, ticker_code, close 
        FROM factstock_daily 
        WHERE ticker_code IN ('{tickers_str}')
          AND date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY date ASC
    """
    
    try:
        df = pd.read_sql(query_stock, engine)
    except Exception as e:
        return {"error": f"株価データ取得エラー: {str(e)}"}

    if df.empty:
        return {"error": "指定期間の株価データがありません"}
    
    # データ整形
    df['date'] = pd.to_datetime(df['date'])
    df_pivot = df.pivot(index='date', columns='ticker_code', values='close')
    # 欠損値補完 (前日の値 -> 翌日の値 -> 0)
    df_pivot = df_pivot.fillna(method='ffill').fillna(method='bfill').fillna(0)

    # --- B. 資産推移の計算 ---
    inv_per_ticker = monthly_inv / len(tickers)
    initial_per_ticker = initial_inv / len(tickers)
    
    holdings = {t: 0.0 for t in tickers} # 保有株数

    # 初回投資
    if not df_pivot.empty:
        first_date = df_pivot.index[0]
        for t in tickers:
            if t in df_pivot.columns:
                price = df_pivot.loc[first_date, t]
                if price > 0:
                    holdings[t] += initial_per_ticker / price

    daily_result = []
    last_month = None
    total_invested = initial_inv

    # 日次ループ
    for date, row in df_pivot.iterrows():
        current_month = date.strftime('%Y-%m')
        
        # 月初の積立
        if last_month and current_month != last_month:
            total_invested += monthly_inv
            for t in tickers:
                if t in row and row[t] > 0:
                    holdings[t] += inv_per_ticker / row[t]
        
        last_month = current_month

        # 評価額計算
        current_total_value = 0
        for t in tickers:
            if t in row:
                current_total_value += holdings[t] * row[t]
        
        daily_result.append({
            "date": date.strftime('%Y-%m-%d'),
            "total_assets": round(current_total_value),
            "invested_amount": round(total_invested)
        })

    # --- C. イベントデータの取得 ---
    query_events = f"""
        SELECT event_date, ticker_code, title, description, sentiment_score 
        FROM fact_events 
        WHERE (ticker_code IN ('{tickers_str}') OR ticker_code IS NULL)
          AND event_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY event_date ASC
    """
    try:
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
    except:
        events_list = []

    # --- D. サマリー作成 ---
    final_assets = daily_result[-1]["total_assets"] if daily_result else 0
    total_invested_final = daily_result[-1]["invested_amount"] if daily_result else 0
    return_rate = 0
    if total_invested_final > 0:
        return_rate = round((final_assets / total_invested_final * 100) - 100, 2)

    return {
        "status": "success",
        "graph_data": daily_result,
        "events": events_list,
        "summary": {
            "final_assets": final_assets,
            "total_invested": total_invested_final,
            "return_rate": return_rate
        }
    }