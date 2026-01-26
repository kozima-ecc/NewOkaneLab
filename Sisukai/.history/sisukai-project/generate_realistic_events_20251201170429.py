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

# 1年あたりの取得件数（多すぎるとブロックされるので必要最低限に）
LIMIT_PER_YEAR = 3
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
            # ノイズ除去
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
    # 連続する空白を1つに
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def analyze_sentiment(text):
    score = 0.0
    pos = ['増益', '最高', '好調', '上昇', '買収', '提携', '黒字', '成功', '期待', '新製品', 'Surge', 'Jump', 'Profit', 'High']
    neg = ['減益', '赤字', '下落', '不振', '中止', '撤退', '懸念', '不祥事', '違反', 'Plunge', 'Drop', 'Loss', 'Cut']
    for w in pos:
        if w in text: score += 0.4
    for w in neg:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def fetch_history_google(ticker, search_name, lang='ja', region='JP'):
    all_results = []
    
    # GoogleNewsインスタンス作成
    googlenews = GoogleNews(lang=lang, region=region)
    
    print(f"  🔍 検索: {search_name} ({START_YEAR}-{END_YEAR})")

    for year in range(START_YEAR, END_YEAR + 1):
        # 期間設定 (MM/DD/YYYY形式)
        start_date = f"01/01/{year}"
        end_date = f"12/31/{year}"
        
        try:
            googlenews.clear()
            googlenews.set_time_range(start_date, end_date)
            
            # 検索実行
            # 米国株の場合は英語で検索したほうが精度が高いが、今回は日本語ニュース縛りなら日本語で
            googlenews.search(search_name)
            
            results = googlenews.results()
            
            # 結果処理
            count = 0
            for res in results:
                if count >= LIMIT_PER_YEAR: break
                
                title = clean_text(res.get('title', ''))
                desc = clean_text(res.get('desc', ''))
                media = clean_text(res.get('media', ''))
                date_str = res.get('date', '')
                
                if len(title) < 5: continue # ゴミ除外

                # 日付の推定 (GoogleNewsは '2年前' とか返すことがあるので、その年の適当な日を入れる)
                # ※厳密な日付取得は難しいので、シミュレーション上は「その年の出来事」として扱う
                # 決算などの正確な日付データと組み合わせれば補完可能
                event_date = datetime.date(year, 6, 15) # 仮の日付
                
                # ディスクリプション整形
                full_desc = desc
                if media:
                    full_desc += f" (出所: {media})"
                
                all_results.append({
                    "event_date": event_date,
                    "ticker_code": ticker,
                    "category": "News",
                    "title": title,
                    "description": full_desc,
                    "sentiment_score": analyze_sentiment(title + desc),
                    "importance": 3
                })
                count += 1
            
            print(f"    - {year}年: {count}件")
            
            # ブロック回避のための待機 (非常に重要)
            # 連続アクセスすると 429 Too Many Requests が出るため
            time.sleep(random.uniform(3.0, 6.0))
            
        except Exception as e:
            print(f"    ! Error {year}: {e}")
            time.sleep(10) # エラー時は長めに休む

    return all_results

def main():
    print("🚀 Google検索による過去10年分のニュース収集を開始します...")
    engine = get_db_engine()

    # 1. 既存データのクリア
    print("🧹 過去のニュースデータを削除中...")
    with engine.begin() as conn:
        # 決算(Earnings)やマクロ(Market)は残し、ニュース系だけ消す
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News' OR category = 'History'"))

    # 2. 企業リスト
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    # 3. ループ
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        print(f"\n[{i+1}/{len(df_comp)}] {ticker}")
        
        # 検索ワードの決定
        if ticker.endswith(".T"):
            # 日本株: Yahooから日本語名を取得
            search_name = get_japanese_name(ticker, db_name)
            lang, region = 'ja', 'JP'
        else:
            # 米国株: カタカナ名で検索したいが、Yahooから取れなければ英語名で
            # Yahooファイナンスは米国株も「アップル」のように表示する場合がある
            jp_name = get_japanese_name(ticker, None)
            if jp_name and jp_name != ticker:
                search_name = jp_name # 「アップル」などが取れた場合
                lang, region = 'ja', 'JP'
            else:
                # 取れなければ英語名 (Inc.等は削除)
                search_name = db_name.replace("Inc.", "").replace("Corporation", "").replace("Corp.", "").strip()
                # それでも日本語記事が欲しいなら lang='ja' にする
                lang, region = 'ja', 'JP'

        # 検索実行
        events = fetch_history_google(ticker, search_name, lang, region)
        
        # 保存
        if events:
            df_events = pd.DataFrame(events)
            df_events.drop_duplicates(subset=['title'], inplace=True)
            df_events.to_sql('fact_events', engine, if_exists='append', index=False)
            print("    -> 保存完了")
        else:
            print("    -> データなし")
            
        # 企業間の待機 (これも重要)
        time.sleep(5)

    print("\n🎉 全完了しました！")

if __name__ == "__main__":
    main()