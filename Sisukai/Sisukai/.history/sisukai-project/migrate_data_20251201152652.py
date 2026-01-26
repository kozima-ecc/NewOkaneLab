import pandas as pd
import sqlite3
from sqlalchemy import create_engine, text, inspect
import urllib.parse

# =========================================================
# ⚙️ 設定エリア
# =========================================================
SQLITE_DB_PATH = '../sisukai.db'
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'your_password'  # ★パスワードを入力★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'sisukai_db'
# =========================================================

def clean_dataframe(df, table_name, mysql_connection):
    inspector = inspect(mysql_connection)
    mysql_cols = [c['name'] for c in inspector.get_columns(table_name)]
    valid_cols = [c for c in df.columns if c in mysql_cols]
    df_clean = df[valid_cols].copy()

    pk_constraint = inspector.get_pk_constraint(table_name)
    pks = pk_constraint.get('constrained_columns', [])
    if pks:
        df_clean.dropna(subset=pks, inplace=True)
    
    # 重複削除 (SQLite側で既に重複している場合への対策)
    if pks:
        df_clean.drop_duplicates(subset=pks, keep='last', inplace=True)

    return df_clean

def insert_on_duplicate_update(table, conn, keys, data_iter):
    # MySQL特有の ON DUPLICATE KEY UPDATE 構文を使うためのメソッド
    from sqlalchemy.dialects.mysql import insert
    
    data = [dict(zip(keys, row)) for row in data_iter]
    
    if not data:
        return

    stmt = insert(table.table).values(data)
    
    # アップデートするカラム（PK以外）
    update_dict = {c.name: c for c in stmt.excluded if not c.primary_key}
    
    if update_dict:
        update_stmt = stmt.on_duplicate_key_update(update_dict)
        conn.execute(update_stmt)
    else:
        # PKしかないテーブル等の場合、IGNORE
        conn.execute(stmt.prefix_with('IGNORE'))

def main():
    print("🚀 データ移行プロセス(v4: 重複回避版)を開始します...")

    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        mysql_engine = create_engine(connection_string)
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
                print(f"\nProcessing table: {table} ...")
                
                try:
                    df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
                except:
                    continue
                
                if df.empty:
                    print("  -> データなし")
                    continue
                
                try:
                    df_clean = clean_dataframe(df, table, mysql_conn)
                    if df_clean.empty: continue

                    # ★ここが変更点: chunksizeを小さくし、エラー時は無視する簡易的な方法に変更
                    # 本当は ON DUPLICATE KEY UPDATE がベストだが、pandasのto_sql標準では対応していない。
                    # そのため、一番簡単な「一度テーブルの中身を空にしてから入れる」方式を採用します。
                    # ※もし既存データを消したくない場合は、上記の insert_on_duplicate_update を使う必要がありますが、
                    # 今回は「移行」なので、全入れ替えで問題ないはずです。
                    
                    print(f"  🧹 既存データをクリアして挿入します (TRUNCATE)")
                    mysql_conn.execute(text(f"TRUNCATE TABLE `{table}`"))
                    
                    df_clean.to_sql(table, con=mysql_conn, if_exists='append', index=False, chunksize=1000)
                    print(f"  ✅ {len(df_clean)} 件 書き込み完了")
                    
                except Exception as e:
                    print(f"  ❌ 保存エラー: {e}")
                    raise e 

            print("\n🔧 制約有効化 & コミット")
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        
        print("🎉 データ移行、完了しました！")

    except Exception as e:
        print(f"\n❌ エラー発生: {e}")
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    main()