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

# フィルタリング用
NG_KEYWORDS = [
    '株価', '予想', '決算', '業績', '増益', '減益', '黒字', '赤字', 
    'アナリスト', 'レーティング', '目標', '配当', '優待', 'チャート', 
    '前場', '後場', '寄り付き', '大引け', '続伸', '反落', '急騰', '急落', 
    'ストップ高', 'ストップ安', '値上がり', '値下がり', 'ランキング', '市況', 
    'テクニカル', '見通し', '掲示板', 'コンセンサス', '日経平均'
]

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
        # 少し待機してからアクセス
        time.sleep(2) 
        url = f"https://finance.yahoo.co.jp/quote/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
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
    text = re.sub(r'<[^>]+>', '', str(text))
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def format_description(text, source):
    if not text: return ""
    text = re.sub(r'\d{1,2}時間前', '', text)
    text = re.sub(r'\d{1,2}日前', '', text)
    text = re.sub(r'\d{4}/\d{1,2}/\d{1,2}', '', text)
    text = re.sub(r'^[-–:：\s]+', '', text)

    limit = 90
    if len(text) > limit:
        text = text[:limit] + "..."
        
    if source:
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

def fetch_history_google_slow(ticker, search_name, lang='ja', region='JP'):
    all_results = []
    
    # 検索クエリ
    query = f'{search_name} -株価 -予想 -チャート'
    print(f"  🔍 検索: {query}")

    for year in range(START_YEAR, END_YEAR + 1):
        start_date = f"01/01/{year}"
        end_date = f"12/31/{year}"
        
        retry_count = 0
        max_retries = 1

        while retry_count <= max_retries:
            try:
                # ★重要: 毎回インスタンスを作り直してクリーンな状態で検索
                googlenews = GoogleNews(lang=lang, region=region)
                googlenews.set_time_range(start_date, end_date)
                googlenews.search(query)
                results = googlenews.results()
                
                candidates = []
                for res in results:
                    title = clean_text(res.get('title', ''))
                    desc = clean_text(res.get('desc', ''))
                    media = clean_text(res.get('media', ''))
                    
                    full_text = title + " " + desc
                    
                    if len(title) < 5: continue
                    if is_boring(full_text): continue

                    priority = calc_priority(full_text)
                    event_date = datetime.date(year, 6, 15)
                    
                    candidates.append({
                        "data": {
                            "event_date": event_date,
                            "ticker_code": ticker,
                            "category": "News",
                            "title": title[:255],
                            "description": format_description(desc, media),
                            "sentiment_score": analyze_sentiment(full_text),
                            "importance": 3 + priority
                        },
                        "priority": priority
                    })

                # ソートして保存
                candidates.sort(key=lambda x: x['priority'], reverse=True)
                selected = [c['data'] for c in candidates[:SAVE_LIMIT_PER_YEAR]]
                all_results.extend(selected)
                
                print(f"    - {year}年: {len(results)}件 -> {len(selected)}件")
                
                # ★超重要: 成功してもガッツリ休む (10〜20秒)
                time.sleep(random.uniform(10.0, 20.0))
                break # 成功したらwhileを抜ける

            except Exception as e:
                print(f"    ⚠️ エラー発生 ({year}年): {e}")
                print("    🛑 3分間待機して冷却します...")
                time.sleep(180) # 3分待機
                retry_count += 1
                # リトライ時はGoogleNewsインスタンスが再生成されるので新しいセッションになる可能性が高い

    return all_results

def main():
    print("🚀 過去10年分のニュース収集 (超安全運転モード) を開始します...")
    engine = get_db_engine()

    # 途中再開などを考慮し、今回は「News」だけを消す（HistoryやEarningsは消さない）
    # もし全部やり直したい場合はこの下のコメントアウトを外して手動で調整してください
    print("🧹 ニュースデータをリセット中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News'"))

    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    total_len = len(df_comp)

    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        print(f"\n[{i+1}/{total_len}] {ticker} -------------------------")
        
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

        events = fetch_history_google_slow(ticker, search_name, lang, region)
        
        if events:
            df_events = pd.DataFrame(events)
            df_events.drop_duplicates(subset=['title'], inplace=True)
            df_events.to_sql('fact_events', engine, if_exists='append', index=False)
            print("    💾 DB保存完了")
        else:
            print("    ❌ 良いニュースなし")
            
        # ★超重要: 企業が変わるタイミングで更に長く休む (30〜60秒)
        print("    ☕ 休憩中...")
        time.sleep(random.uniform(30.0, 60.0))

    print("\n🎉 全工程完了しました！")

if __name__ == "__main__":
    main()