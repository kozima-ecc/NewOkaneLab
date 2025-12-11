import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import re

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def clean_text_aggressive(text_content):
    if not text_content:
        return ""
    
    txt = str(text_content)

    # 1. URLと "Google News" の削除 (正規表現で強力に)
    # "Google News" 以降、または "http" 以降をすべて削除する
    txt = re.sub(r'Google News.*', '', txt, flags=re.IGNORECASE)
    txt = re.sub(r'https?://[\w/:%#\$&\?\(\)~\.=\+\-]+', '', txt)
    
    # 2. 謎の区切り文字 "??" の処理
    # ?が2つ以上連続していたら、" -" に変える
    txt = re.sub(r'\?{2,}', ' - ', txt)
    
    # 3. 末尾のソース表記を綺麗にする
    # " - サイト名" のようになっている場合、 "(出所: サイト名)" に整形
    # 末尾の " - " 以降をキャプチャ
    match = re.search(r' - ([^-]+)$', txt)
    if match:
        source = match.group(1).strip()
        # ソースが短すぎず長すぎない場合のみ整形
        if 1 < len(source) < 30:
            txt = txt[:match.start()] + f" (出所: {source})"

    # 4. 余計な空白・改行の削除
    txt = txt.strip()
    
    return txt

def main():
    print("🚀 強力クリーニングを開始します...")
    engine = get_db_engine()

    try:
        # 1. データ取得
        query = "SELECT event_id, description FROM fact_events WHERE category = 'News'"
        df = pd.read_sql(query, engine)
        
        print(f"  📝 処理対象: {len(df)} 件")
        
        if df.empty:
            print("  対象データがありません。")
            return

        # --- デバッグ: 最初の1件の「生データ」を表示 ---
        raw_sample = df.iloc[0]['description']
        print("\n🔍 [DEBUG] Pythonから見た最初のデータの生身:")
        print(f"  '{raw_sample}'")
        print("  (このデータに対して置換処理を行います)\n")
        # -------------------------------------------

        updates = []
        
        for _, row in df.iterrows():
            original_desc = row['description']
            
            # 強力クリーニング実行
            new_desc = clean_text_aggressive(original_desc)
            
            # 変更があればリストに追加
            # (strip()して差があれば更新)
            if new_desc.strip() != original_desc.strip():
                updates.append({
                    "event_id": row['event_id'],
                    "description": new_desc
                })
        
        # 2. データベース更新
        if updates:
            print(f"  💾 {len(updates)} 件のデータを更新中...")
            
            with engine.begin() as conn:
                for up in updates:
                    sql = text("UPDATE fact_events SET description = :description WHERE event_id = :event_id")
                    conn.execute(sql, up)
            
            print("✅ 更新完了！")
            
            # 確認用表示
            print("\n🔍 【整形後】データサンプル (Top 3):")
            check_query = "SELECT title, description FROM fact_events WHERE category='News' LIMIT 3"
            check_df = pd.read_sql(check_query, engine)
            for i, r in check_df.iterrows():
                print(f"--- [{i+1}] ---")
                print(f"Desc : {r['description']}")
        else:
            print("  ⚠️ 変更が必要なデータが見つかりませんでした。")
            print("  (正規表現のパターンにマッチしていない可能性があります)")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()