import pandas as pd
import sqlite3
from sqlalchemy import create_engine, text, inspect
import urllib.parse

# =========================================================
# ⚙️ 設定エリア
# =========================================================
SQLITE_DB_PATH = '../sisukai.db'
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root'  # ★ここにパスワードを入力★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def clean_dataframe(df, table_name, mysql_engine):
    """
    データフレームをMySQLの定義に合わせてクリーニングする関数
    """
    inspector = inspect(mysql_engine)
    
    # 1. MySQL側に存在しない列を削除 (listing_dateエラー対策)
    mysql_cols = [c['name'] for c in inspector.get_columns(table_name)]
    valid_cols = [c for c in df.columns if c in mysql_cols]
    
    removed_cols = set(df.columns) - set(valid_cols)
    if removed_cols:
        print(f"    ⚠️ 未定義の列をカットします: {removed_cols}")
    
    df_clean = df[valid_cols].copy()

    # 2. 必須項目(PK)がNULLの行を削除 (fiscal_yearエラー対策)
    # Primary Keyを取得
    pk_constraint = inspector.get_pk_constraint(table_name)
    pks = pk_constraint.get('constrained_columns', [])
    
    if pks:
        original_count = len(df_clean)
        # PKに含まれる列に欠損がある行を削除
        df_clean.dropna(subset=pks, inplace=True)
        dropped_count = original_count - len(df_clean)
        if dropped_count > 0:
            print(f"    🧹 {dropped_count} 件の不備データ(PK欠損)を除外しました")

    return df_clean

def main():
    print("🚀 データ移行プロセス(v2)を開始します...")

    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        mysql_engine = create_engine(connection_string)
        print(f"📂 接続確認OK")
    except Exception as e:
        print(f"❌ 接続エラー: {e}")
        return

    try:
        # 外部キー制約チェックを一時的に無効化
        with mysql_engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            print(f"\nProcessing table: {table} ...")
            
            # SQLiteから読込
            try:
                df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
            except:
                print("  -> 読み込み失敗(スキップ)")
                continue
            
            if df.empty:
                print("  -> データなし")
                continue
            
            # ★ここでデータをクリーニング★
            try:
                df_clean = clean_dataframe(df, table, mysql_engine)
                
                if df_clean.empty:
                    print("  -> 有効なデータが残りませんでした")
                    continue

                # MySQLに保存
                df_clean.to_sql(table, mysql_engine, if_exists='append', index=False, chunksize=1000)
                print(f"  ✅ {len(df_clean)} 件 保存成功")
                
            except Exception as e:
                print(f"  ❌ 保存エラー: {e}")

        # 外部キー制約を戻す
        with mysql_engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

    except Exception as e:
        print(f"\n❌ 全体エラー: {e}")
    
    finally:
        sqlite_conn.close()
        print("\n🏁 処理終了")

if __name__ == "__main__":
    main()