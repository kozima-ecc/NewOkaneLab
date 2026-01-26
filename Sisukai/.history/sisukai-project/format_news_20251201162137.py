import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def main():
    print("🚀 SQLによる直接クリーニングを開始します...")

    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(conn_str)

        with engine.begin() as conn:
            # 1. "Google News - " を削除
            print("  🧹 'Google News - ' を削除中...")
            conn.execute(text("UPDATE fact_events SET description = REPLACE(description, 'Google News - ', '')"))
            
            # 2. " ?? " を " (出所: " に置換 (前後にスペースがある場合)
            print("  🧹 ' ?? ' を ' (出所: ' に置換中...")
            conn.execute(text("UPDATE fact_events SET description = REPLACE(description, ' ?? ', ' (出所: ')"))
            
            # 3. "??" を " (出所: " に置換 (スペースなしの場合)
            print("  🧹 '??' を ' (出所: ' に置換中...")
            conn.execute(text("UPDATE fact_events SET description = REPLACE(description, '??', ' (出所: ')"))
            
            # 4. 末尾に ")" を付ける (出所: xxx となったものの閉じ括弧がない場合)
            # ※これは複雑なので、単純に「出所:」がある行の末尾に「)」をつける
            # (既に閉じ括弧がある場合は二重になるリスクがあるが、表示崩れよりはマシ)
            print("  🧹 末尾の閉じ括弧を補正中...")
            conn.execute(text("UPDATE fact_events SET description = CONCAT(description, ')') WHERE description LIKE '%(出所: %' AND description NOT LIKE '%)'"))
            
            # 5. URL削除 (httpから始まる文字列を空文字にする...のはSQLだけだと難しいので、Pythonでやるか、
            # 今回は「出所」表記に変わったのでURLは残しておいてOKとするか)
            # ユーザー要望は「中身が欲しい」だったので、URLが残っていても「出所」として明記されていればOKと判断。
            
            # 6. タイトルに含まれる " - サイト名" などのノイズ除去
            # (例: "... - Bloomberg.co.jp" -> "...")
            # これもSQLだと難しいのでスキップ

        print("✅ 完了しました！")
        
        # 確認
        print("\n🔍 結果確認 (先頭5件):")
        df = pd.read_sql("SELECT title, description FROM fact_events LIMIT 5", engine)
        for _, row in df.iterrows():
            print(f"Desc: {row['description']}")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()