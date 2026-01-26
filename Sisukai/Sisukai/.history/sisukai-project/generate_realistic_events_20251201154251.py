import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import random

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

# ---------------------------------------------------------
# 1. 実際の歴史的イベント (市場全体: ticker_code=NULL)
# ---------------------------------------------------------
GLOBAL_EVENTS = [
    ("2015-08-24", "Market", "チャイナショック：中国経済減速懸念により世界同時株安", -0.8, 5),
    ("2016-06-24", "Politics", "ブレグジット：英国がEU離脱を選択、市場に激震", -0.7, 5),
    ("2016-11-09", "Politics", "トランプ氏が米大統領選で勝利、トランプラリー開始", 0.6, 5),
    ("2019-10-01", "Economy", "消費税が8%から10%に増税", -0.3, 4),
    ("2020-01-16", "Disaster", "日本国内で新型コロナウイルスの感染初確認", -0.5, 5),
    ("2020-03-11", "Disaster", "WHOが新型コロナ「パンデミック」を表明、世界株価暴落", -1.0, 5),
    ("2020-04-07", "Politics", "日本政府、緊急事態宣言を発令", -0.6, 4),
    ("2020-11-09", "Medical", "ファイザー、コロナワクチンの有効性を発表", 0.9, 5),
    ("2021-01-20", "Politics", "バイデン米大統領就任", 0.3, 3),
    ("2022-02-24", "Geopolitics", "ロシアがウクライナに軍事侵攻を開始", -0.9, 5),
    ("2022-03-16", "Economy", "FRBがゼロ金利解除、利上げサイクル開始", -0.4, 5),
    ("2022-07-08", "Politics", "安倍元首相銃撃事件", -0.5, 5),
    ("2022-10-20", "Economy", "円相場が一時1ドル150円台に下落、32年ぶり円安水準", 0.2, 4), # 輸出企業にはプラス
    ("2023-05-08", "Social", "新型コロナの感染症法上の位置づけが5類に移行", 0.5, 3),
    ("2024-01-01", "Disaster", "能登半島地震発生", -0.4, 4),
    ("2024-03-19", "Economy", "日銀がマイナス金利政策を解除、17年ぶり利上げ", -0.2, 5),
]

# ---------------------------------------------------------
# ランダム生成用のテンプレート
# ---------------------------------------------------------
NEWS_TEMPLATES = [
    # (カテゴリ, タイトル, センチメント基礎値, 重要度)
    ("Product", "新主力製品の発表会を開催、AI機能を搭載", 0.6, 3),
    ("Product", "次世代モデルの発売延期を発表", -0.4, 3),
    ("Alliance", "海外大手との業務提携に向けた協議を開始", 0.5, 4),
    ("Corporate", "自社株買いの実施を発表", 0.7, 4),
    ("Corporate", "中期経営計画を上方修正", 0.6, 4),
    ("Corporate", "構造改革に伴う特別損失を計上", -0.5, 4),
    ("Scandal", "不適切な会計処理の疑いで第三者委員会を設置", -0.9, 5),
    ("Scandal", "品質検査データの一部不備が発覚", -0.7, 5),
    ("M&A", "国内ベンチャー企業の買収を発表", 0.3, 3),
]

def main():
    print("🚀 イベントデータ生成を開始します...")

    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(conn_str)
        
        all_events = []

        # -------------------------------------------------
        # 1. マクロイベントの追加
        # -------------------------------------------------
        print("  🌍 歴史的マクロイベントを作成中...")
        for date, cat, title, score, imp in GLOBAL_EVENTS:
            all_events.append({
                "event_date": date,
                "ticker_code": None, # 市場全体
                "category": cat,
                "title": title,
                "description": f"{title}。市場全体への影響が懸念される。",
                "sentiment_score": score,
                "importance": imp
            })

        # -------------------------------------------------
        # 2. 決算発表イベント (DBの財務データから生成)
        # -------------------------------------------------
        print("  💰 財務データから決算発表ニュースを作成中...")
        
        # 財務データと企業名を取得
        query = """
            SELECT f.ticker_code, f.fiscal_year, f.quarter, f.net_sales, f.net_income, c.company_name
            FROM fact_financials f
            JOIN companies c ON f.ticker_code = c.ticker_code
            ORDER BY f.ticker_code, f.fiscal_year, f.quarter
        """
        df_fin = pd.read_sql(query, engine)
        
        # 前期比計算のためにグループ化
        df_fin['prev_sales'] = df_fin.groupby('ticker_code')['net_sales'].shift(1)
        df_fin['prev_income'] = df_fin.groupby('ticker_code')['net_income'].shift(1)

        for _, row in df_fin.iterrows():
            # 決算発表日を推定 (四半期末の45日後とする)
            # 日本企業の年度: 4月開始が多い。
            # Q1(4-6) -> 8/14頃, Q2(7-9) -> 11/14頃, Q3(10-12) -> 2/14頃, Q4(1-3) -> 5/14頃
            # ※簡易ロジックです
            
            try:
                if row['quarter'] == 1:
                    base_date = datetime.date(row['fiscal_year'], 8, 14)
                elif row['quarter'] == 2:
                    base_date = datetime.date(row['fiscal_year'], 11, 14)
                elif row['quarter'] == 3:
                    base_date = datetime.date(row['fiscal_year'] + 1, 2, 14)
                else: # Q4
                    base_date = datetime.date(row['fiscal_year'] + 1, 5, 14)
                
                # 土日ならずらす
                if base_date.weekday() >= 5:
                    base_date -= datetime.timedelta(days=2)
                
                # センチメント判定 (増収増益ならポジティブ)
                score = 0.0
                title_parts = []
                
                # 売上判定
                if pd.notna(row['net_sales']) and pd.notna(row['prev_sales']):
                    if row['net_sales'] > row['prev_sales']:
                        score += 0.4
                        title_parts.append("増収")
                    else:
                        score -= 0.3
                        title_parts.append("減収")
                
                # 利益判定
                if pd.notna(row['net_income']) and pd.notna(row['prev_income']):
                    if row['net_income'] > row['prev_income']:
                        score += 0.5
                        title_parts.append("増益")
                    else:
                        score -= 0.4
                        title_parts.append("減益")
                
                # 最終調整
                score = max(-1.0, min(1.0, score)) # クリップ
                title_res = "、".join(title_parts) if title_parts else "決算"
                
                event_title = f"{row['company_name']}、第{row['quarter']}四半期決算発表：{title_res}"
                desc = f"売上高: {row['net_sales']:,.0f}円, 純利益: {row['net_income']:,.0f}円。"
                
                all_events.append({
                    "event_date": base_date,
                    "ticker_code": row['ticker_code'],
                    "category": "Earnings",
                    "title": event_title,
                    "description": desc,
                    "sentiment_score": score,
                    "importance": 5 # 決算は重要
                })

            except:
                continue

        # -------------------------------------------------
        # 3. ランダム企業ニュースの生成
        # -------------------------------------------------
        print("  🎲 ランダムな企業ニュースを散りばめています...")
        
        tickers = df_fin['ticker_code'].unique()
        start_date = datetime.date(2015, 1, 1)
        end_date = datetime.date.today()
        days_range = (end_date - start_date).days
        
        for ticker in tickers:
            # 1社あたり平均5件くらいのランダムニュースを生成
            for _ in range(5):
                rand_days = random.randint(0, days_range)
                event_date = start_date + datetime.timedelta(days=rand_days)
                
                # 土日スキップ
                if event_date.weekday() >= 5: continue
                
                # テンプレート選択
                cat, templ_title, base_score, imp = random.choice(NEWS_TEMPLATES)
                
                # センチメントにゆらぎを与える
                final_score = base_score + random.uniform(-0.1, 0.1)
                final_score = max(-1.0, min(1.0, final_score))
                
                all_events.append({
                    "event_date": event_date,
                    "ticker_code": ticker,
                    "category": cat,
                    "title": templ_title, # 実際は企業名を入れたりするが今回は簡易的
                    "description": f"{ticker}に関する{cat}ニュース。",
                    "sentiment_score": final_score,
                    "importance": imp
                })

        # -------------------------------------------------
        # DBへ保存
        # -------------------------------------------------
        print(f"\n📦 合計 {len(all_events)} 件のイベントを保存します...")
        
        df_events = pd.DataFrame(all_events)
        
        # 一括保存
        df_events.to_sql('fact_events', engine, if_exists='append', index=False, chunksize=1000)
        
        print("✅ 完了しました！")
        print(df_events.head())

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()