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
import dateparser

# =========================================================
# ⚙️ 設定エリア (高速化チューニング済み)
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

START_YEAR = 2015
END_YEAR = 2024

# 1社あたりの目標イベント数
TARGET_EVENTS_PER_COMPANY = 20

# 1年あたり検索してプールする候補数
FETCH_CANDIDATES_PER_YEAR = 5

# フィルタリング用
NG_KEYWORDS = [
    '株価', '予想', '決算', '業績', '増益', '減益', '黒字', '赤字', 
    'アナリスト', 'レーティング', '目標', '配当', '優待', 'チャート', 
    '前場', '後場', '寄り付き', '大引け', '続伸', '反落', '急騰', '急落', 
    'ストップ高', 'ストップ安', '値上がり', '値下がり', 'ランキング', '市況', 
    'テクニカル', '見通し', '掲示板', 'コンセンサス', '日経平均'
]
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def get_japanese_name(ticker, default_name):
    """ Yahoo!ファイナンスから日本語社名を取得 (高速化: 待機なし) """
    try:
        # time.sleep(1) # 削除: ここでの待機は不要と判断
        url = f"https://finance.yahoo.co.jp/quote/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5) # タイムアウト短縮
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

def is_match_year(date_str, target_year):
    if not date_str: return False
    if str(target_year) in date_str: return True
    
    current_year = datetime.datetime.now().year
    if "年前" in date_str:
        try:
            years_ago = int(re.search(r'(\d+)年前', date_str).group(1))
            if (current_year - years_ago) == target_year:
                return True
        except:
            pass
            
    try:
        dt = dateparser.parse(date_str)
        if dt and dt.year == target_year: return True
    except:
        pass
    return False

def analyze_sentiment(text):
    score = 0.0
    pos = ['増益', '最高', '好調', '上昇', '買収', '提携', '成功', '期待', '新製品', '承認', '開始']
    neg = ['減益', '赤字', '下落', '不振', '中止', '撤退', '懸念', '不祥事', '違反', '辞任', '不正']
    for w in pos:
        if w in text: score += 0.4
    for w in neg:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def search_candidates(ticker, search_name, year, lang, region):
    """ 指定年のニュース候補を取得 (高速 & リトライ) """
    candidates = []
    query = f'{search_name} {year} -株価 -予想'
    
    start_date = f"01/01/{year}"
    end_date = f"12/31/{year}"
    
    retry_count = 0
    max_retries = 3 # リトライ回数を増やして粘り強く

    while retry_count <= max_retries:
        try:
            googlenews = GoogleNews(lang=lang, region=region)
            googlenews.set_time_range(start_date, end_date)
            googlenews.search(query)
            results = googlenews.results()
            
            if not results:
                # 0件でも即リトライせず、とりあえず次へ行く (高速化優先)
                # 本当にBANされてたら次のリクエストでエラーが出るはず
                break

            for res in results:
                title = clean_text(res.get('title', ''))
                desc = clean_text(res.get('desc', ''))
                media = clean_text(res.get('media', ''))
                date_str = res.get('date', '')
                
                full_text = title + " " + desc
                
                if len(title) < 5: continue
                if is_boring(full_text): continue
                
                if not is_match_year(date_str, year):
                    if str(year) not in title and str(year) not in desc:
                        continue

                rand_day = random.randint(1, 28)
                rand_month = random.randint(1, 12)
                event_date = datetime.date(year, rand_month, rand_day)

                candidates.append({
                    "raw_title": title,
                    "data": {
                        "event_date": event_date,
                        "ticker_code": ticker,
                        "category": "News",
                        "title": title[:255],
                        "description": format_description(desc, media),
                        "sentiment_score": analyze_sentiment(full_text),
                        "importance": 3
                    }
                })
            break # 成功

        except Exception as e:
            print(f"    ⚠️ Error: {e}", end="", flush=True)
            print(" 🛑 3分待機(冷却)...", end="", flush=True)
            time.sleep(180) # ここだけはしっかり休む (保険)
            retry_count += 1
            
    return candidates[:FETCH_CANDIDATES_PER_YEAR]

def main():
    print("🚀 ニュース収集(高速・ランダム選抜版)を開始します...")
    engine = get_db_engine()

    print("🧹 Newsカテゴリをリセット中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News'"))

    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    total_len = len(df_comp)
    
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        print(f"\n[{i+1}/{total_len}] {ticker} プール作成...", end="", flush=True)
        
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

        company_pool = []
        print(f" [{search_name}] ", end="", flush=True)

        # 10年分ループ
        for year in range(START_YEAR, END_YEAR + 1):
            cands = search_candidates(ticker, search_name, year, lang, region)
            company_pool.extend(cands)
            
            print(".", end="", flush=True) # 進捗表示をドットで簡略化
            
            # ★高速化: 待機時間を 0.5〜1.0秒 に短縮
            time.sleep(random.uniform(0.5, 1.0))

        # --- 抽選フェーズ ---
        unique_pool = []
        seen_titles = set()
        for item in company_pool:
            if item['raw_title'] not in seen_titles:
                unique_pool.append(item)
                seen_titles.add(item['raw_title'])
        
        final_selection = []
        if len(unique_pool) > TARGET_EVENTS_PER_COMPANY:
            final_selection = random.sample(unique_pool, TARGET_EVENTS_PER_COMPANY)
        else:
            final_selection = unique_pool

        # 保存
        if final_selection:
            save_data = [item['data'] for item in final_selection]
            save_data.sort(key=lambda x: x['event_date'])
            df_save = pd.DataFrame(save_data)
            df_save.to_sql('fact_events', engine, if_exists='append', index=False)
            print(f" ✅ {len(final_selection)}件保存", end="", flush=True)
        else:
            print(" ❌ なし", end="", flush=True)

        # ★高速化: 企業間待機も 2〜4秒 に短縮
        time.sleep(random.uniform(2.0, 4.0))

    print("\n🎉 全工程完了しました！")

if __name__ == "__main__":
    main()