import pandas as pd
import sqlite3
from sqlalchemy import create_engine, text, inspect
import urllib.parse

# =========================================================
# ⚙️ 設定エリア
# =========================================================
SQLITE_DB_PATH = 'sisukai.db' # パスを修正 (同じフォルダにある想定)
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root'  # ★パスワード: root★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'   # ★DB名: trade_sim★
# =========================================================

def clean_dataframe(df, table_name, mysql_connection):
    inspector = inspect(mysql_connection)
    
    # MySQL側のテーブル名補正 (SQLiteと名前が違う場合に対応)
    mysql_table_name = table_name
    if table_name == 'fact_stock_daily':
        # MySQL側に factstock_daily があるか確認
        if inspector.has_table('factstock_daily'):
            mysql_table_name = 'factstock_daily'
        elif inspector.has_table('fact_stock_daily'):
            mysql_table_name = 'fact_stock_daily'
            
    # カラムチェック
    mysql_cols = [c['name'] for c in inspector.get_columns(mysql_table_name)]
    valid_cols = [c for c in df.columns if c in mysql_cols]
    df_clean = df[valid_cols].copy()

    pk_constraint = inspector.get_pk_constraint(mysql_table_name)
    pks = pk_constraint.get('constrained_columns', [])
    if pks:
        df_clean.dropna(subset=pks, inplace=True)
        # 重複排除
        df_clean.drop_duplicates(subset=pks, keep='last', inplace=True)

    return df_clean, mysql_table_name

def main():
    print("🚀 データ移行プロセス(v5: 最終調整版)を開始します...")

    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        mysql_engine = create_engine(connection_string)
        print(f"📂 接続確認OK: {MYSQL_DB}")
    except Exception as e:
        print(f"❌ 接続エラー: {e}")
        return

    try:
        with mysql_engine.begin() as mysql_conn:
            print("🔧 トランザクション開始: 制約無効化")
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

            cursor = sqlite_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                print(f"\nProcessing SQLite table: {table} ...")
                
                try:
                    df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
                except:
                    print("  -> 読込失敗(スキップ)")
                    continue
                
                if df.empty:
                    print("  -> データなし")
                    continue
                
                try:
                    # クリーニング & テーブル名マッピング
                    df_clean, target_table = clean_dataframe(df, table, mysql_conn)
                    
                    if df_clean.empty:
                        print("  -> 有効データなし")
                        continue

                    print(f"  🧹 既存データをクリア (TRUNCATE `{target_table}`)")
                    mysql_conn.execute(text(f"TRUNCATE TABLE `{target_table}`"))
                    
                    df_clean.to_sql(target_table, con=mysql_conn, if_exists='append', index=False, chunksize=1000)
                    print(f"  ✅ {len(df_clean)} 件 書き込み完了 -> MySQL table: `{target_table}`")
                    
                except Exception as e:
                    print(f"  ❌ 保存エラー: {e}")
                    # エラーでも続行したい場合は raise e をコメントアウト
                    # raise e 

            print("\n🔧 制約有効化 & コミット")
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        
        print("🎉 データ移行、完了しました！")

    except Exception as e:
        print(f"\n❌ エラー発生: {e}")
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    main()