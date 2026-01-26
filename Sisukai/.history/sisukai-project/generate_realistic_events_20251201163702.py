import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

# ---------------------------------------------------------
# 1. 歴史的マクロイベント (日付固定)
# ---------------------------------------------------------
MACRO_EVENTS = [
    ("2015-08-24", "チャイナショック", "中国経済減速懸念により世界同時株安が発生。", -0.8),
    ("2016-01-29", "日銀マイナス金利導入", "日銀が史上初のマイナス金利導入を決定。", 0.4),
    ("2016-06-24", "ブレグジット", "英国国民投票でEU離脱派が勝利。金融市場に激震。", -0.7),
    ("2016-11-09", "トランプ大統領当選", "米大統領選でトランプ氏が勝利。トランプラリーの開始。", 0.6),
    ("2018-02-06", "VIXショック", "米金利上昇懸念からVIX指数が急騰、世界的な株価急落。", -0.6),
    ("2018-10-01", "米中貿易摩擦激化", "米中の関税報復合戦が激化、世界経済への懸念高まる。", -0.5),
    ("2019-10-01", "消費増税", "日本の消費税率が8%から10%に引き上げ。", -0.3),
    ("2020-02-24", "コロナショック(初期)", "新型コロナウイルスの世界的な感染拡大懸念で株価暴落開始。", -0.9),
    ("2020-03-16", "コロナショック(底)", "FRBがゼロ金利政策を復活、市場は乱高下。", -0.8),
    ("2020-11-09", "ワクチン開発発表", "ファイザーがコロナワクチンの高い有効性を発表。経済正常化期待。", 0.9),
    ("2021-01-20", "バイデン大統領就任", "バイデン米政権発足。大規模な財政出動への期待。", 0.5),
    ("2022-02-24", "ウクライナ侵攻", "ロシア軍がウクライナに侵攻を開始。資源価格が高騰。", -0.9),
    ("2022-12-20", "日銀YCC修正", "日銀が長期金利の変動幅を拡大（実質利上げ）。円高株安へ。", -0.4),
    ("2023-05-08", "コロナ5類移行", "新型コロナの感染症法上の位置づけが5類に移行。経済活動完全再開。", 0.4),
    ("2024-01-01", "能登半島地震", "石川県能登地方で最大震度7の地震発生。", -0.3),
    ("2024-03-19", "マイナス金利解除", "日銀がマイナス金利政策を解除、17年ぶりの利上げ。", -0.2),
    ("2024-08-05", "令和のブラックマンデー", "日経平均が史上最大の下落幅を記録。円キャリー取引の巻き戻し。", -1.0),
]

def main():
    print("🚀 過去データに基づくイベント生成を開始します...")
    engine = get_db_engine()

    # 既存データのクリア
    print("🧹 イベントテーブルを初期化します...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE fact_events"))

    all_events = []

    # ---------------------------------------------------------
    # 2. マクロイベントの登録
    # ---------------------------------------------------------
    print("🌍 マクロイベントを生成中...")
    for date_str, title, desc, score in MACRO_EVENTS:
        all_events.append({
            "event_date": datetime.datetime.strptime(date_str, "%Y-%m-%d").date(),
            "ticker_code": None,
            "category": "Market",
            "title": title,
            "description": f"{title} - {desc}",
            "sentiment_score": score,
            "importance": 5
        })

    # ---------------------------------------------------------
    # 3. 株価急変動イベント (Stock Price Action)
    # ---------------------------------------------------------
    print("📈 株価データから「急騰・急落イベント」を生成中...")
    
    # 全株価データを取得して変動率を計算
    query = """
        SELECT date, ticker_code, close 
        FROM factstock_daily 
        ORDER BY ticker_code, date
    """
    df_stock = pd.read_sql(query, engine)
    
    # 前日比計算
    df_stock['prev_close'] = df_stock.groupby('ticker_code')['close'].shift(1)
    df_stock['pct_change'] = (df_stock['close'] - df_stock['prev_close']) / df_stock['prev_close']
    
    # ±5%以上動いた日を抽出
    df_moves = df_stock[abs(df_stock['pct_change']) >= 0.05].copy()
    
    print(f"  -> {len(df_moves)} 件の急変動を検出しました")

    for _, row in df_moves.iterrows():
        change_pct = row['pct_change'] * 100
        direction = "急騰" if change_pct > 0 else "急落"
        sentiment = 0.8 if change_pct > 0 else -0.8
        
        title = f"株価{direction}: 前日比 {change_pct:+.1f}%"
        desc = f"終値 {row['close']:,.0f}円。前日比 {change_pct:+.1f}% の{direction}を記録。市場の注目を集めた。"
        
        all_events.append({
            "event_date": row['date'],
            "ticker_code": row['ticker_code'],
            "category": "PriceAction",
            "title": title,
            "description": desc,
            "sentiment_score": sentiment,
            "importance": 4
        })

    # ---------------------------------------------------------
    # 4. 決算発表イベント (Earnings)
    # ---------------------------------------------------------
    print("💰 財務データから「決算発表イベント」を生成中...")

    query_fin = """
        SELECT f.ticker_code, f.fiscal_year, f.quarter, f.net_sales, f.net_income, c.company_name 
        FROM fact_financials f
        JOIN companies c ON f.ticker_code = c.ticker_code
    """
    df_fin = pd.read_sql(query_fin, engine)

    for _, row in df_fin.iterrows():
        # 発表日の推定 (四半期末の45日後)
        # 3月決算企業を基準に簡易計算 (多少ズレるがシミュレーションには十分)
        try:
            year = row['fiscal_year']
            q = row['quarter']
            
            # 決算期末月 (日本企業の場合)
            # Q1=6月, Q2=9月, Q3=12月, Q4=3月
            if q == 1:   mo = 8;  da = 10 # 8/10頃発表
            elif q == 2: mo = 11; da = 10 # 11/10頃発表
            elif q == 3: mo = 2;  da = 10 # 翌年2/10頃発表
            else:        mo = 5;  da = 10 # 翌年5/10頃発表
            
            if q >= 3: year += 1
            
            # 日付オブジェクト作成
            ann_date = datetime.date(year, mo, da)
            
            # 土日なら翌月曜に
            if ann_date.weekday() == 5: ann_date += datetime.timedelta(days=2)
            if ann_date.weekday() == 6: ann_date += datetime.timedelta(days=1)
            
            # 数値フォーマット
            sales = f"{row['net_sales']:,.0f}" if row['net_sales'] else "-"
            income = f"{row['net_income']:,.0f}" if row['net_income'] else "-"
            
            title = f"決算発表: 第{q}四半期"
            desc = f"{row['company_name']}が第{q}四半期決算を発表。売上高: {sales}円, 純利益: {income}円。"
            
            # センチメントは不明(0)とするか、黒字ならプラスにするなど
            # ここでは簡易的に「黒字なら+0.3, 赤字なら-0.3」
            score = 0.3 if (row['net_income'] and row['net_income'] > 0) else -0.3

            all_events.append({
                "event_date": ann_date,
                "ticker_code": row['ticker_code'],
                "category": "Earnings",
                "title": title,
                "description": desc,
                "sentiment_score": score,
                "importance": 5
            })

        except:
            continue

    # ---------------------------------------------------------
    # 保存処理
    # ---------------------------------------------------------
    if all_events:
        print(f"\n📦 合計 {len(all_events)} 件のイベントデータを保存中...")
        df_events = pd.DataFrame(all_events)
        
        # 重複排除
        df_events.drop_duplicates(subset=['event_date', 'ticker_code', 'category'], inplace=True)
        
        df_events.to_sql('fact_events', engine, if_exists='append', index=False, chunksize=2000)
        print("✅ 完了しました！")
        
        # 確認
        print("\n🔍 データサンプル:")
        print(df_events[['event_date', 'ticker_code', 'title']].head(5))
    else:
        print("⚠️ データが生成されませんでした。")

if __name__ == "__main__":
    main()