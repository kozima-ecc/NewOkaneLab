import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
from deep_translator import GoogleTranslator
import time

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'
# =========================================================

def main():
    print("🚀 英語ニュースの翻訳(v2)を開始します...")

    try:
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(conn_str)

        # 1. 翻訳対象データの取得
        # ★修正点: '%.T' を '%%.T' に変更してエスケープ
        query = """
            SELECT event_id, title, description 
            FROM fact_events 
            WHERE ticker_code NOT LIKE '%%.T' 
              AND ticker_code IS NOT NULL
        """
        
        # SQL読み込み
        df_en = pd.read_sql(query, engine)
        
        print(f"  📝 翻訳対象: {len(df_en)} 件")
        
        if df_en.empty:
            print("  翻訳するデータがありませんでした。")
            return

        # 翻訳器の初期化
        translator = GoogleTranslator(source='auto', target='ja')
        
        updates = []
        
        # 2. 翻訳ループ
        for i, row in df_en.iterrows():
            try:
                original_title = row['title']
                # 既に日本語っぽい場合（ASCII文字以外を含む）はスキップ
                if not is_english(original_title):
                    continue

                print(f"  Translating ({i+1}/{len(df_en)}): {original_title[:30]}...")
                
                # タイトル翻訳
                ja_title = translator.translate(original_title)
                
                # 詳細の翻訳 (URLを壊さないように分離)
                desc = row['description']
                url_part = ""
                text_part = desc
                
                # URLが含まれているかチェック
                # "Source: ... - http..." や "Google News - http..." の形式が多い
                if "http" in desc:
                    # 最後のhttp以降をURLとして分離
                    parts = desc.split("http")
                    # 最後の要素がURL本体、それ以前がテキスト
                    # ただしURLが複数ある場合は複雑になるので、簡易的に「最後のhttp」をURLとする
                    # あるいは "Google News -" で分割するなど
                    
                    # 簡易ロジック: 最初のhttp以降は翻訳しない
                    text_part = parts[0]
                    url_part = "http" + "".join(parts[1:])
                
                # テキスト部分を翻訳
                ja_desc_text = translator.translate(text_part)
                
                # 結合
                ja_desc = f"{ja_desc_text} {url_part}".strip()

                updates.append({
                    "event_id": row['event_id'],
                    "title": ja_title,
                    "description": ja_desc
                })
                
                # 負荷軽減
                time.sleep(0.5)

            except Exception as e:
                print(f"    Error translating ID {row['event_id']}: {e}")
                continue

        # 3. DB更新
        if updates:
            print(f"\n💾 {len(updates)} 件の翻訳結果を保存中...")
            with engine.begin() as conn:
                for up in updates:
                    sql = text("UPDATE fact_events SET title = :title, description = :description WHERE event_id = :event_id")
                    conn.execute(sql, up)
            print("✅ 完了しました！")
        else:
            print("  翻訳が必要なデータはありませんでした。")

    except Exception as e:
        print(f"❌ エラー: {e}")

def is_english(text):
    """ 簡易的に英語かどうか判定 (ASCII文字のみなら英語とみなす) """
    if not text: return False
    try:
        text.encode(encoding='utf-8').decode('ascii')
    except UnicodeDecodeError:
        return False
    return True

if __name__ == "__main__":
    main()