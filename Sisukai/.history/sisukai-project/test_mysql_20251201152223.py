import pandas as pd
from sqlalchemy import create_engine
import urllib.parse

# =========================================================
# 🔑 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'your_password'  # ★ここにMySQLのパスワードを入力★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'sisukai_db'
# =========================================================

def main():
    print("🚀 MySQL接続テストを開始します...")

    try:
        # 接続文字列の作成
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        
        # エンジン作成
        engine = create_engine(connection_string)
        
        # 1. 企業リストの取得
        print("\n📋 登録されている企業リスト (先頭5件):")
        df_companies = pd.read_sql("SELECT * FROM companies LIMIT 5", engine)
        print(df_companies[['ticker_code', 'company_name']])

        # 2. トヨタの株価データを取得して分析
        target_ticker = "7203.T"
        print(f"\n📈 {target_ticker} の最新株価データ (先頭5件):")
        
        query = f"""
            SELECT date, close, volume 
            FROM factstock_daily 
            WHERE ticker_code = '{target_ticker}' 
            ORDER BY date DESC 
            LIMIT 5
        """
        df_stock = pd.read_sql(query, engine)
        
        if not df_stock.empty:
            print(df_stock)
            print("\n✅ データ取得成功！")
            print("   これでAIによるシミュレーションや分析を始める準備が整いました。")
        else:
            print(f"⚠️ {target_ticker} のデータが見つかりませんでした。")

    except Exception as e:
        print(f"❌ 接続エラー: {e}")

if __name__ == "__main__":
    main()