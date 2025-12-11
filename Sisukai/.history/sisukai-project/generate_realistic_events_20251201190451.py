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
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

START_YEAR = 2015
END_YEAR = 2024
TARGET_EVENTS_PER_COMPANY = 20
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
    try:
        time.sleep(1)
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
    candidates = []
    query = f'{search_name} {year} -株価 -予想'
    
    start_date = f"01/01/{year}"
    end_date = f"12/31/{year}"
    
    retry_count = 0
    # 再試行回数 (429が出たら粘る回数)
    max_retries = 2 

    while retry_count <= max_retries:
        try:
            googlenews = GoogleNews(lang=lang, region=region)
            googlenews.set_time_range(start_date, end_date)
            googlenews.search(query)
            results = googlenews.results()
            
            if not results:
                # 結果0件の場合でも、429エラーではないので次へ進む
                # (ただしあまりに連続で0件なら怪しいが、ここでは許容)
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
            break # 成功したらループを抜ける

        except Exception as e:
            # ここで429エラーなどをキャッチ
            print(f"    ⚠️ Error ({year}): {e}")
            print("    🛑 2分間待機します...", end="", flush=True)
            time.sleep(120) # 2分待つ
            retry_count += 1
            print(" 再開")
            
    return candidates[:FETCH_CANDIDATES_PER_YEAR]

def main():
    print("🚀 ニュース収集(途中再開・安全版)を開始します...")
    engine = get_db_engine()

    # ★重要: 全削除はしない (途中再開のため)
    # print("🧹 Newsカテゴリをリセット中...")
    # with engine.begin() as conn:
    #     conn.execute(text("DELETE FROM fact_events WHERE category = 'News'"))

    # 既にデータがある企業を確認
    existing_df = pd.read_sql("SELECT DISTINCT ticker_code FROM fact_events WHERE category = 'News'", engine)
    existing_tickers = existing_df['ticker_code'].tolist()
    print(f"  ℹ️ 既にデータがある企業数: {len(existing_tickers)} 社")

    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    total_len = len(df_comp)
    
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        # ★スキップ処理: 既にデータがあれば飛ばす
        if ticker in existing_tickers:
            print(f"[{i+1}/{total_len}] {ticker} は完了済み -> スキップ")
            continue
        
        print(f"\n[{i+1}/{total_len}] {ticker} プール作成...", end="", flush=True)
        
        # 社名取得
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
            
            print(".", end="", flush=True)
            
            # ★安全運転: 2〜4秒待機 (高速版より遅いが確実)
            time.sleep(random.uniform(2.0, 4.0))

        # 重複排除と抽選
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

        # 企業間の大休憩 (10〜20秒)
        time.sleep(random.uniform(10.0, 20.0))

    print("\n🎉 全工程完了しました！")

if __name__ == "__main__":
    main()