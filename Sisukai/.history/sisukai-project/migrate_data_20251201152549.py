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

def clean_dataframe(df, table_name, mysql_connection):
    """
    データフレームをMySQLの定義に合わせてクリーニングする関数
    """
    # ConnectionからInspectorを作成
    inspector = inspect(mysql_connection)
    
    # 1. MySQL側に存在しない列を削除
    mysql_cols = [c['name'] for c in inspector.get_columns(table_name)]
    valid_cols = [c for c in df.columns if c in mysql_cols]
    
    removed_cols = set(df.columns) - set(valid_cols)
    if removed_cols:
        print(f"    ⚠️ 未定義の列をカット: {removed_cols}")
    
    df_clean = df[valid_cols].copy()

    # 2. 必須項目(PK)がNULLの行を削除
    pk_constraint = inspector.get_pk_constraint(table_name)
    pks = pk_constraint.get('constrained_columns', [])
    
    if pks:
        original_count = len(df_clean)
        df_clean.dropna(subset=pks, inplace=True)
        dropped_count = original_count - len(df_clean)
        if dropped_count > 0:
            print(f"    🧹 {dropped_count} 件の不備データ(PK欠損)を除外")

    return df_clean

def main():
    print("🚀 データ移行プロセス(v3: トランザクション版)を開始します...")

    # 1. SQLite接続
    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    except Exception as e:
        print(f"❌ SQLite接続エラー: {e}")
        return

    # 2. MySQL接続 (Engine作成)
    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        mysql_engine = create_engine(connection_string)
    except Exception as e:
        print(f"❌ MySQL接続エラー: {e}")
        return

    # 3. 移行処理 (1つのトランザクション内で実行)
    try:
        # begin() を使うことで、ブロックを抜けるまでコミットされず、同一コネクションが保証される
        with mysql_engine.begin() as mysql_conn:
            print("🔧 トランザクション開始: 外部キー制約を無効化")
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

            # テーブル一覧取得
            cursor = sqlite_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                print(f"\nProcessing table: {table} ...")
                
                # SQLiteから読込
                try:
                    df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
                except:
                    print("  -> 読込失敗(スキップ)")
                    continue
                
                if df.empty:
                    print("  -> データなし")
                    continue
                
                # クリーニング
                try:
                    df_clean = clean_dataframe(df, table, mysql_conn)
                    
                    if df_clean.empty:
                        print("  -> 有効データなし")
                        continue

                    # MySQLに保存
                    # ★重要: engineではなく、現在の mysql_conn を渡す！
                    df_clean.to_sql(table, con=mysql_conn, if_exists='append', index=False, chunksize=1000)
                    print(f"  ✅ {len(df_clean)} 件 書き込み完了 (未コミット)")
                    
                except Exception as e:
                    print(f"  ❌ 保存エラー: {e}")
                    raise e # エラー時はロールバックさせるために例外を投げる

            print("\n🔧 外部キー制約を有効化")
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            
            print("💾 コミット中... (ここで初めてDBに反映されます)")
        
        # withブロックをエラーなく抜ければ自動コミットされる
        print("🎉 全処理完了: データ移行に成功しました！")

    except Exception as e:
        print(f"\n❌ 重大なエラーによりロールバックしました: {e}")
    
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    main()