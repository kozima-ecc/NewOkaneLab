import pandas as pd
import sqlite3
from sqlalchemy import create_engine, text
import urllib.parse

# =========================================================
# ⚙️ 設定エリア
# =========================================================
# SQLiteのパス (1つ上の階層にある場合)
SQLITE_DB_PATH = '../sisukai.db'

# MySQLの設定 (環境に合わせて書き換えてください)
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'your_password'  # ★ここにパスワードを入力★
MYSQL_HOST = 'localhost'
MYSQL_DB = 'sisukai_db'
# =========================================================

def main():
    print("🚀 データ移行プロセスを開始します...")

    # 1. SQLiteに接続
    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        print(f"📂 SQLiteに接続完了: {SQLITE_DB_PATH}")
    except Exception as e:
        print(f"❌ SQLite接続エラー: {e}")
        return

    # 2. MySQLに接続 (SQLAlchemy)
    try:
        # パスワードに含まれる記号をURLエンコード
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        
        mysql_engine = create_engine(connection_string)
        print(f"📂 MySQLに接続完了: {MYSQL_DB}")
    except Exception as e:
        print(f"❌ MySQL接続エラー: {e}")
        print("※パスワードが間違っているか、pymysqlが入っていない可能性があります。")
        return

    # 3. データ移行実行
    try:
        # 外部キー制約チェックを一時的に無効化 (これがないと順番次第でエラーになる)
        with mysql_engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            print("🔧 外部キー制約を一時的に無効化しました")

        # SQLiteからテーブル一覧を取得
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            print(f"\nProcessing table: {table} ...")
            
            # SQLiteからデータを読み込む
            df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
            
            if df.empty:
                print("  -> データなし (スキップ)")
                continue
            
            print(f"  -> {len(df)} 件のデータを読み込みました")

            # MySQLに書き込む
            # if_exists='append': 既存のテーブルに追加
            # index=False: DataFrameのインデックス番号は入れない
            try:
                df.to_sql(table, mysql_engine, if_exists='append', index=False, chunksize=1000)
                print("  ✅ MySQLへの保存成功")
            except Exception as e:
                print(f"  ❌ 保存エラー: {e}")

        # 外部キー制約チェックを戻す
        with mysql_engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            print("\n🔧 外部キー制約を有効化しました")

    except Exception as e:
        print(f"\n❌ 全体エラー: {e}")
    
    finally:
        sqlite_conn.close()
        print("\n🏁 処理終了")

if __name__ == "__main__":
    main()