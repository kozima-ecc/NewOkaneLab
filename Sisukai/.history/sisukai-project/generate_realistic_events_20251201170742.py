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

# フィルタリング用キーワード (これらを含む記事は捨てる)
NG_KEYWORDS = [
    '株価', '予想', '決算', '業績', '増益', '減益', '黒字', '赤字', '修正', 
    'アナリスト', 'レーティング', '目標', '配当', '優待', '四季報', 'チャート', 
    '前場', '後場', '寄り付き', '大引け', '続伸', '反落', '急騰', '急落', 
    'ストップ高', 'ストップ安', '値上がり', '値下がり', 'ランキング', '市況', 
    'サマリー', '銘柄', 'テクニカル', '来週の', '本日の', '明日の', '見通し'
]

# 優先的に残すキーワード (これらを含む記事を優先保存)
GOOD_KEYWORDS = [
    '買収', '提携', '合併', '新製品', '発売', '開始', '設立', '撤退', '中止', 
    '辞任', '就任', '交代', '不正', '問題', '事故', 'リコール', '処分', '違反', 
    '開発', '成功', '承認', '採用', '上場', '公開'
]
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def get_japanese_name(ticker, default_name):
    """ Yahoo!ファイナンスから日本語社名を取得 """
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
    text = re.sub(r'<[^>]+>', '', str(text)) # HTML除去
    text = re.sub(r'\s+', ' ', text).strip() # 空白整理
    return text

def is_boring(text):
    """ NGワードが含まれているか判定 """
    for ng in NG_KEYWORDS:
        if ng in text:
            return True
    return False

def calc_priority(text):
    """ 優先度スコアを計算 (GOODワードが含まれるほど高い) """
    score = 0
    for good in GOOD_KEYWORDS:
        if good in text:
            score += 1
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
    
    # 検索クエリに除外キーワードを追加 (Google検索自体の精度向上)
    # ※あまり長くするとエラーになるので主要なものだけ
    query = f'{search_name} -株価 -予想 -チャート'
    
    print(f"  🔍 検索: {query}")

    for year in range(START_YEAR, END_YEAR + 1):
        start_date = f"01/01/{year}"
        end_date = f"12/31/{year}"
        
        try:
            googlenews.clear()
            googlenews.set_time_range(start_date, end_date)
            googlenews.search(query)
            
            # 多めに取ってフィルタリングする (1ページ=10件程度)
            # get_page(2)までやると20件取れる
            results = googlenews.results()
            
            candidates = []
            for res in results:
                title = clean_text(res.get('title', ''))
                desc = clean_text(res.get('desc', ''))
                media = clean_text(res.get('media', ''))
                
                full_text = title + " " + desc
                
                # 1. 短すぎるゴミを除外
                if len(title) < 5: continue
                
                # 2. NGワードを含む記事を除外 (徹底的に)
                if is_boring(full_text):
                    continue

                # 日付 (正確な日付は取れないことが多いので仮置き)
                event_date = datetime.date(year, 6, 15)
                
                # 出所表記
                full_desc = desc
                if media:
                    full_desc += f" (出所: {media})"
                
                # 候補リストに追加 (優先度スコア付き)
                priority = calc_priority(full_text)
                
                candidates.append({
                    "data": {
                        "event_date": event_date,
                        "ticker_code": ticker,
                        "category": "News",
                        "title": title,
                        "description": full_desc,
                        "sentiment_score": analyze_sentiment(full_text),
                        "importance": 3 + priority # 優先度が高いほど重要度も上げる
                    },
                    "priority": priority
                })

            # 優先度順にソートして上位3件を取得
            candidates.sort(key=lambda x: x['priority'], reverse=True)
            
            selected = [c['data'] for c in candidates[:SAVE_LIMIT_PER_YEAR]]
            all_results.extend(selected)
            
            print(f"    - {year}年: {len(results)}件中 -> {len(selected)}件選抜")
            
            # ブロック回避
            time.sleep(random.uniform(3.0, 5.0))
            
        except Exception as e:
            print(f"    ! Error {year}: {e}")
            time.sleep(5)

    return all_results

def main():
    print("🚀 過去10年分の厳選ニュース収集を開始します...")
    engine = get_db_engine()

    print("🧹 既存のニュースデータを削除中...")
    with engine.begin() as conn:
        # Earnings(決算)やMarket(マクロ)は残し、News系だけ消す
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
            print("    -> 良いニュースが見つかりませんでした")
            
        time.sleep(3)

    print("\n🎉 全完了しました！")

if __name__ == "__main__":
    main()