import pandas as pd
from sqlalchemy import create_engine
import urllib.parse

# =========================================================
# 🔑 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root'  # ★パスワードを入力★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def main():
    print("🔍 データ診断を開始します...")

    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(connection_string)
        
        # 1. データ件数チェック
        count_df = pd.read_sql("SELECT COUNT(*) as cnt FROM factstock_daily", engine)
        print(f"\n📊 株価データの総行数: {count_df.iloc[0]['cnt']} 行")

        # 2. どんな銘柄コードが入っているか確認 (先頭20件)
        print("\n📋 登録されている銘柄コード (factstock_daily の中身):")
        tickers_df = pd.read_sql("SELECT DISTINCT ticker_code FROM factstock_daily LIMIT 20", engine)
        print(tickers_df['ticker_code'].tolist())

        # 3. トヨタを探してみる
        print("\n🕵️‍♂️ トヨタ (7203) の検索テスト:")
        
        # パターンA: .T あり
        check_a = pd.read_sql("SELECT COUNT(*) as cnt FROM factstock_daily WHERE ticker_code = '7203.T'", engine)
        print(f"  - '7203.T' で検索: {check_a.iloc[0]['cnt']} 件")
        
        # パターンB: .T なし
        check_b = pd.read_sql("SELECT COUNT(*) as cnt FROM factstock_daily WHERE ticker_code = '7203'", engine)
        print(f"  - '7203'   で検索: {check_b.iloc[0]['cnt']} 件")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()