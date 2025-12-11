import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import requests
from bs4 import BeautifulSoup
import re
import time
import datetime

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

# 取得対象の期間
START_YEAR = 2015
END_YEAR = 2025
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def get_sentiment_score(text):
    """ 簡易センチメント分析 """
    score = 0.0
    pos_words = ['上場', '買収', '提携', '設立', '開発', '発売', '最高', '黒字', '受賞', '採用', '開始']
    neg_words = ['赤字', '撤退', '中止', '延期', '不祥事', '不正', '処分', '辞任', '解散', '課徴金']
    for w in pos_words:
        if w in text: score += 0.4
    for w in neg_words:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def fetch_wiki_history(ticker, company_name):
    """ Wikipediaから沿革を取得 """
    
    # 検索クエリの作成 (Inc.などはノイズになるので削除)
    clean_name = company_name.replace("株式会社", "").replace("Inc.", "").replace("Corp.", "").strip()
    
    # Wikipedia URL (日本語)
    url = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(clean_name)}"
    
    print(f"  📖 {clean_name} ({ticker}) のWikiを解析中...")
    
    events = []
    try:
        res = requests.get(url)
        if res.status_code != 200:
            print("    -> ページが見つかりませんでした。")
            return []

        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 年号の正規表現 (2015年 ... 2025年)
        year_pattern = re.compile(r'(' + '|'.join([str(y) for y in range(START_YEAR, END_YEAR+1)]) + r')年')
        
        # リストアイテム(li)や段落(p)から年号を含む行を探す
        # 特に「沿革」「歴史」セクションにある li タグが狙い目
        content_text = []
        for li in soup.find_all('li'):
            content_text.append(li.get_text())
        for dd in soup.find_all('dd'): # 定義リストの場合もある
            content_text.append(dd.get_text())

        for text in content_text:
            # "20xx年 - 〇〇" のような形式を探す
            match = year_pattern.search(text)
            if match:
                year_str = match.group(1)
                year_int = int(year_str)
                
                # 年号より後ろの部分をイベント内容とする
                # "2018年10月 - 〇〇を買収" -> "10月 - 〇〇を買収"
                event_text = text.split(year_str + '年', 1)[1].strip()
                
                # 月を解析 (なければその年の適当な日)
                month_match = re.search(r'(\d{1,2})月', event_text)
                if month_match:
                    month = int(month_match.group(1))
                    # 日付まではWikiにないことが多いので「1日」か「15日」にする
                    day = 1
                else:
                    month = 6 # 不明なら中間
                    day = 15

                # 不要なゴミ削除 (" - " が先頭にある場合など)
                clean_desc = re.sub(r'^[-–:：\s]+', '', event_text)
                # 脚注番号 [1] などを削除
                clean_desc = re.sub(r'\[\d+\]', '', clean_desc).strip()
                
                if len(clean_desc) < 5: continue # 短すぎるゴミは無視

                # タイトル生成 (長い場合は短縮)
                title = clean_desc[:30] + "..." if len(clean_desc) > 30 else clean_desc
                
                # センチメント
                score = get_sentiment_score(clean_desc)
                
                # 日付オブジェクト
                try:
                    event_date = datetime.date(year_int, month, day)
                except:
                    continue

                events.append({
                    "event_date": event_date,
                    "ticker_code": ticker,
                    "category": "History", # 沿革
                    "title": title,
                    "description": f"{clean_desc} (出所: Wikipedia)",
                    "sentiment_score": score,
                    "importance": 4
                })

    except Exception as e:
        print(f"    Error: {e}")
        
    print(f"    -> {len(events)} 件のイベントを抽出")
    return events

def main():
    print("🚀 Wikipediaからの歴史イベント収集を開始します...")
    engine = get_db_engine()

    # 1. 既存のゴミニュースを削除
    print("🧹 過去の失敗ニュースデータを削除中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News'"))

    # 2. 企業リスト
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    all_events = []

    # 3. ループ処理
    for _, row in df_comp.iterrows():
        events = fetch_wiki_history(row['ticker_code'], row['company_name'])
        all_events.extend(events)
        time.sleep(1) # サーバー負荷軽減

    # 4. 保存
    if all_events:
        print(f"\n📦 {len(all_events)} 件の歴史データを保存中...")
        df_events = pd.DataFrame(all_events)
        # 重複排除
        df_events.drop_duplicates(subset=['ticker_code', 'title'], inplace=True)
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print("✅ 完了しました！")
        
        # 確認
        print("\n🔍 データサンプル:")
        print(df_events[['event_date', 'ticker_code', 'description']].head(10))

    else:
        print("⚠️ データが取得できませんでした。")

if __name__ == "__main__":
    main()