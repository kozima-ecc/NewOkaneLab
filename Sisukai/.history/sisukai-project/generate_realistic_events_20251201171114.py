import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import time
import random
import re
import requests
from bs4 import BeautifulSoup
from GoogleNews import GoogleNews

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

START_YEAR = 2015
END_YEAR = 2025

# 1年あたりの保存件数
SAVE_LIMIT_PER_YEAR = 3

# フィルタリング用 (株価実況などは除外)
NG_KEYWORDS = [
    '株価', '予想', '決算', '業績', '増益', '減益', '黒字', '赤字', 
    'アナリスト', 'レーティング', '目標', '配当', '優待', 'チャート', 
    '前場', '後場', '寄り付き', '大引け', '続伸', '反落', '急騰', '急落', 
    'ストップ高', 'ストップ安', '値上がり', '値下がり', 'ランキング', '市況', 
    'テクニカル', '見通し'
]

# 優先キーワード (実体経済ニュース)
GOOD_KEYWORDS = [
    '買収', '提携', '合併', '新製品', '発売', '開始', '設立', '撤退', '中止', 
    '辞任', '就任', '交代', '不正', '問題', '事故', 'リコール', '処分', '違反', 
    '開発', '成功', '承認', '採用', '上場', '公開', '世界初', '最高'
]
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def get_japanese_name(ticker, default_name):
    try:
        url = f"https://finance.yahoo.co.jp/quote/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return default_name

        soup = BeautifulSoup(res.content, "html.parser")
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text()
            name = name.replace('の株価・株式情報', '').replace(' - Yahoo!ファイナンス', '')
            name = re.sub(r'【.*?】', '', name)
            name = name.replace('株式会社', '').replace('(株)', '').replace('株)', '')
            return name.strip()
    except:
        pass
    return default_name

def clean_text(text):
    if not text: return ""
    # HTMLタグ除去
    text = re.sub(r'<[^>]+>', '', str(text))
    # 余計な空白削除
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def format_description(text, source):
    """ 詳細を100文字程度に要約・整形 """
    if not text: return ""
    
    # 1. 邪魔な日付情報の削除 ("14時間前", "2023/01/01" など)
    text = re.sub(r'\d{1,2}時間前', '', text)
    text = re.sub(r'\d{1,2}日前', '', text)
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    
    # 2. 先頭の記号削除
    text = re.sub(r'^[-–:：\s]+', '', text)

    # 3. 文字数制限 (100文字)
    # ソース表記 "(出所: xxx)" の分(約15文字)を考慮して85文字程度で切る
    limit = 90
    if len(text) > limit:
        text = text[:limit] + "..."
        
    # 4. ソース付与
    if source:
        # ドメイン名が長すぎる場合は短縮
        if "http" in source:
            try:
                source = urllib.parse.urlparse(source).netloc.replace('www.', '')
            except:
                pass
        return f"{text} (出所: {source})"
    
    return text

def is_boring(text):
    for ng in NG_KEYWORDS:
        if ng in text: return True
    return False

def calc_priority(text):
    score = 0
    for good in GOOD_KEYWORDS:
        if good in text: score += 1
    return score

def analyze_sentiment(text):
    score = 0.0
    pos = ['増益', '最高', '好調', '上昇', '買収', '提携', '成功', '期待', '新製品', '承認', '開始']
    neg = ['減益', '赤字', '下落', '不振', '中止', '撤退', '懸念', '不祥事', '違反', '辞任', '不正']
    for w in pos:
        if w in text: score += 0.4
    for w in neg:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def fetch_history_google_filtered(ticker, search_name, lang='ja', region='JP'):
    all_results = []
    googlenews = GoogleNews(lang=lang, region=region)
    
    # 検索クエリ (株価ノイズ除去)
    query = f'{search_name} -株価 -予想 -チャート'
    print(f"  🔍 検索: {query}")

    for year in range(START_YEAR, END_YEAR + 1):
        start_date = f"01/01/{year}"
        end_date = f"12/31/{year}"
        
        try:
            googlenews.clear()
            googlenews.set_time_range(start_date, end_date)
            googlenews.search(query)
            results = googlenews.results()
            
            candidates = []
            for res in results:
                title = clean_text(res.get('title', ''))
                desc = clean_text(res.get('desc', ''))
                media = clean_text(res.get('media', ''))
                
                # ゴミ除外
                if len(title) < 5: continue
                if is_boring(title + desc): continue

                # 日付 (仮)
                event_date = datetime.date(year, 6, 15)
                
                # ★整形処理
                formatted_desc = format_description(desc, media)
                
                # 優先度計算
                priority = calc_priority(title + desc)
                
                candidates.append({
                    "data": {
                        "event_date": event_date,
                        "ticker_code": ticker,
                        "category": "News",
                        "title": title[:255], # 256文字制限対応
                        "description": formatted_desc,
                        "sentiment_score": analyze_sentiment(title + desc),
                        "importance": 3 + priority
                    },
                    "priority": priority
                })

            # 優先度順にソートして上位3件
            candidates.sort(key=lambda x: x['priority'], reverse=True)
            
            selected = [c['data'] for c in candidates[:SAVE_LIMIT_PER_YEAR]]
            all_results.extend(selected)
            
            print(f"    - {year}年: {len(results)}件 -> {len(selected)}件 (整形済)")
            time.sleep(random.uniform(3.0, 5.0))
            
        except Exception as e:
            print(f"    ! Error {year}: {e}")
            time.sleep(5)

    return all_results

def main():
    print("🚀 過去10年分の厳選ニュース収集(フォーマット修正版)を開始します...")
    engine = get_db_engine()

    print("🧹 ニュースデータをリセット中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News' OR category = 'History'"))

    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        print(f"\n[{i+1}/{len(df_comp)}] {ticker}")
        
        if ticker.endswith(".T"):
            search_name = get_japanese_name(ticker, db_name)
            lang, region = 'ja', 'JP'
        else:
            jp_name = get_japanese_name(ticker, None)
            if jp_name and jp_name != ticker:
                search_name = jp_name
                lang, region = 'ja', 'JP'
            else:
                search_name = db_name.replace("Inc.", "").replace("Corporation", "").replace("Corp.", "").strip()
                lang, region = 'ja', 'JP'

        events = fetch_history_google_filtered(ticker, search_name, lang, region)
        
        if events:
            df_events = pd.DataFrame(events)
            df_events.drop_duplicates(subset=['title'], inplace=True)
            df_events.to_sql('fact_events', engine, if_exists='append', index=False)
            print("    -> 保存完了")
        else:
            print("    -> 該当なし")
            
        time.sleep(3)

    print("\n🎉 全完了しました！")

if __name__ == "__main__":
    main()