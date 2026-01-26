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
    print("🚀 英語ニュースの翻訳を開始します...")

    try:
        # DB接続
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
        conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
        engine = create_engine(conn_str)

        # 1. 翻訳対象データの取得
        # 米国株のティッカー（.Tがつかないもの）のニュースを取得
        query = """
            SELECT event_id, title, description 
            FROM fact_events 
            WHERE ticker_code NOT LIKE '%.T' 
              AND ticker_code IS NOT NULL
        """
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
                # タイトルの翻訳
                # 既に日本語っぽい場合（ASCII文字以外を含む）はスキップする簡易判定
                if not is_english(row['title']):
                    continue

                print(f"  Translating ({i+1}/{len(df_en)}): {row['title'][:30]}...")
                
                ja_title = translator.translate(row['title'])
                
                # 詳細の翻訳 (URL部分は残したいが、単純に全文翻訳してみる)
                # descriptionには "Source: ... - http..." のようにURLが含まれることが多い
                # URLを壊さないように分離する工夫
                desc = row['description']
                url_part = ""
                text_part = desc
                
                if "http" in desc:
                    parts = desc.split("http")
                    text_part = parts[0]
                    url_part = "http" + "".join(parts[1:])
                
                ja_desc_text = translator.translate(text_part)
                ja_desc = f"{ja_desc_text} {url_part}"

                updates.append({
                    "event_id": row['event_id'],
                    "title": ja_title,
                    "description": ja_desc
                })
                
                # Google翻訳への負荷軽減
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
    try:
        text.encode(encoding='utf-8').decode('ascii')
    except UnicodeDecodeError:
        return False
    return True

if __name__ == "__main__":
    main()