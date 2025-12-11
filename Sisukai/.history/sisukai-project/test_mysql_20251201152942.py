import pandas as pd
from sqlalchemy import create_engine
import urllib.parse

# =========================================================
# 🔑 設定 (パスワードを書き換えてください)
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' # ★あなたのパスワード★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def main():
    print("🚀 MySQL接続テスト...")
    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(connection_string)
        
        # 1. 企業数チェック
        df_comp = pd.read_sql("SELECT count(*) as count FROM companies", engine)
        print(f"🏢 企業数: {df_comp.iloc[0]['count']} 社")

        # 2. トヨタ(7203.T)のデータチェック
        print("\n📈 トヨタ(7203.T)の最新株価:")
        query = "SELECT date, close, volume FROM factstock_daily WHERE ticker_code = '7203.T' ORDER BY date DESC LIMIT 5"
        df_stock = pd.read_sql(query, engine)
        
        if not df_stock.empty:
            print(df_stock)
        else:
            print("⚠️ データが見つかりません (コードが違う可能性があります)")

        # 3. 財務データチェック
        print("\n💰 トヨタ(7203.T)の最新決算:")
        query_fin = "SELECT fiscal_year, quarter, net_sales FROM fact_financials WHERE ticker_code = '7203.T' ORDER BY fiscal_year DESC, quarter DESC LIMIT 3"
        df_fin = pd.read_sql(query_fin, engine)
        print(df_fin if not df_fin.empty else "⚠️ 財務データなし")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()