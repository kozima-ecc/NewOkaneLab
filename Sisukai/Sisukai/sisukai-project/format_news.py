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

def aggressive_fix(text_content):
    if not text_content:
        return ""
    
    txt = str(text_content).strip()
    
    # ロジック:
    # 文末にある「URL」や「ドメイン名(xxx.comなど)」を探し、
    # その直前にある「スペースや?などの記号の塊」を「 (出所: 」に置換する。
    
    # 正規表現の解説:
    # [\s\?]+      : スペース(\s)かハテナ(\?)が1回以上続く場所 (ここがゴミ)
    # (            : グループ開始 (サイト名部分)
    #  https?://\S+  : httpまたはhttpsで始まるURL
    #  |             : または
    #  [\w\.-]+\.[a-z]{2,} : "sdki.jp" や "Bloomberg.co.jp" のようなドメイン名
    # )            : グループ終了
    # $            : 文末
    
    pattern = r'[\s\?]+(https?://\S+|[\w\.-]+\.[a-z]{2,})$'
    
    # 置換実行 ( \1 はキャプチャしたサイト名 )
    new_txt = re.sub(pattern, r' (出所: \1)', txt, flags=re.IGNORECASE)
    
    # 念のため、閉じ括弧がない場合は補完（二重にならないようにチェック）
    if " (出所:" in new_txt and not new_txt.endswith(")"):
        new_txt += ")"

    return new_txt

def main():
    print("🚀 最終強力クリーニングを開始します...")
    engine = get_db_engine()

    try:
        # 1. ニュースデータの取得
        query = "SELECT event_id, description FROM fact_events WHERE category = 'News'"
        df = pd.read_sql(query, engine)
        
        print(f"  📝 処理対象: {len(df)} 件")
        
        updates = []
        
        # 2. 修正ループ
        for _, row in df.iterrows():
            original = row['description']
            fixed = aggressive_fix(original)
            
            # 変化があったものだけ更新リスト入り
            if original != fixed:
                updates.append({
                    "event_id": row['event_id'],
                    "description": fixed
                })

        # 3. データベース更新
        if updates:
            print(f"  💾 {len(updates)} 件のデータを修正・保存中...")
            
            with engine.begin() as conn:
                for up in updates:
                    sql = text("UPDATE fact_events SET description = :description WHERE event_id = :event_id")
                    conn.execute(sql, up)
            
            print("✅ 完了しました！")
            
            # 確認表示 (Before -> Afterのサンプル)
            print("\n🔍 修正結果サンプル:")
            check_query = "SELECT description FROM fact_events WHERE category='News' LIMIT 5"
            check_df = pd.read_sql(check_query, engine)
            for r in check_df.itertuples():
                print(f" - {r.description}")

        else:
            print("  ✨ 修正が必要なデータは見つかりませんでした（既に綺麗な可能性があります）。")
            # デバッグ用: どんなデータが残っているか1つ表示
            if not df.empty:
                print(f"  (参考: 現在のデータ例 -> {df.iloc[0]['description']})")

    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    main()