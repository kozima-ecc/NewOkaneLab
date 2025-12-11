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

def clean_text(text_content):
    if not text_content:
        return ""
    
    txt = str(text_content)
    
    # 1. 文字化け "?? " を " - " や "(出所: ...)" に置換
    # ニュースの末尾にある "?? SourceName" はソース表記にする
    if "??" in txt:
        # 文末に近い "??" はソース表記に変える
        parts = txt.split("??")
        if len(parts) > 1:
            main_text = parts[0].strip()
            source_text = parts[1].strip()
            
            # ソース部分がURLやドメインっぽい場合
            if "." in source_text or "http" in source_text:
                txt = f"{main_text} (出所: {source_text})"
            else:
                txt = f"{main_text} - {source_text}"
    
    # 2. "Google News -" などのノイズ除去
    txt = txt.replace("Google News - ", "")
    txt = txt.replace("Google News", "")
    
    # 3. 不要な記号の整理
    txt = txt.replace("  ", " ").strip()
    
    # 4. URLが長すぎる場合、末尾にあれば (Link) に短縮する等の処理も可能だが
    # 今回は「ユーザーが見る」ため、URLはそのまま残すか、
    # もし「URLが邪魔」なら削除する以下の行を有効にしてください。
    
    # URL削除パターン (ご希望に合わせてコメントアウトを外してください)
    # txt = re.sub(r'https?://\S+', '', txt).strip() 

    return txt

def main():
    print("ニュースデータの整形(クリーンアップ)を開始します...")
    engine = get_db_engine()

    try:
        # 1. ニュース系データの取得
        query = "SELECT event_id, title, description FROM fact_events WHERE category = 'News'"
        df = pd.read_sql(query, engine)
        
        print(f"処理対象: {len(df)} 件")
        
        updates = []
        
        for _, row in df.iterrows():
            original_desc = row['description']
            original_title = row['title']
            
            # クリーニング実行
            new_desc = clean_text(original_desc)
            new_title = clean_text(original_title)
            
            # 変更がある場合のみ更新リストに追加
            if new_desc != original_desc or new_title != original_title:
                updates.append({
                    "event_id": row['event_id'],
                    "title": new_title,
                    "description": new_desc
                })
        
        # 2. データベース更新
        if updates:
            print(f"{len(updates)} 件のデータを整形して上書き保存中...")
            
            # 一括更新だと重いので、トランザクション内でループ実行
            with engine.begin() as conn:
                for up in updates:
                    sql = text("UPDATE fact_events SET title = :title, description = :description WHERE event_id = :event_id")
                    conn.execute(sql, up)
            
            print("整形完了！")
            
            # 確認用表示
            print("\n【整形後】データサンプル:")
            check_query = "SELECT title, description FROM fact_events WHERE category='News' LIMIT 5"
            check_df = pd.read_sql(check_query, engine)
            for i, r in check_df.iterrows():
                print(f"--- [{i+1}] ---")
                print(f"Title: {r['title']}")
                print(f"Desc : {r['description']}")
        else:
            print("修正が必要なデータはありませんでした。")

    except Exception as e:
        print(f"エラー: {e}")

if __name__ == "__main__":
    main()