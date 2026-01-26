import pandas as pd
from sqlalchemy import create_engine
import urllib.parse

# =========================================================
# 🔑 設定 (パスワードを入力)
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root'
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def main():
    print("🔍 株価テーブル(factstock_daily)の中身を調査します...")

    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(connection_string)
        
        # 1. 保存されている銘柄コードの種類を取得
        print("\n📋 登録されている銘柄コード一覧 (先頭20件):")
        query_list = "SELECT DISTINCT ticker_code FROM factstock_daily LIMIT 20"
        df_tickers = pd.read_sql(query_list, engine)
        
        if df_tickers.empty:
            print("❌ データが1件もありません！移行に失敗している可能性があります。")
        else:
            print(df_tickers['ticker_code'].tolist())
            
        # 2. 件数内訳
        print("\n📊 データ件数ランキング (上位10社):")
        query_count = """
            SELECT ticker_code, COUNT(*) as count 
            FROM factstock_daily 
            GROUP BY ticker_code 
            ORDER BY count DESC 
            LIMIT 10
        """
        df_count = pd.read_sql(query_count, engine)
        print(df_count)

        # 3. トヨタっぽいデータがあるかあいまい検索
        print("\n🕵️‍♂️ '7203' を含むコードを探しています...")
        query_search = "SELECT DISTINCT ticker_code FROM factstock_daily WHERE ticker_code LIKE '%7203%'"
        df_search = pd.read_sql(query_search, engine)
        
        if not df_search.empty:
            print(f"発見しました: {df_search['ticker_code'].tolist()}")
        else:
            print("見つかりませんでした。")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()