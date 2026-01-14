import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import requests
from bs4 import BeautifulSoup
import re
import time
import datetime
from duckduckgo_search import DDGS

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

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
    pos_words = ['上場', '買収', '提携', '設立', '開発', '発売', '最高', '黒字', '受賞', '採用', '開始', '成功', '増資']
    neg_words = ['赤字', '撤退', '中止', '延期', '不祥事', '不正', '処分', '辞任', '解散', '課徴金', '訴訟', '排除']
    for w in pos_words:
        if w in text: score += 0.4
    for w in neg_words:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def find_wiki_url(ticker, company_name):
    """ DuckDuckGoで日本語WikipediaのURLを探す """
    # 検索クエリ: "銘柄コード 企業名 Wikipedia"
    # 企業名が英語でも、コードとWikipediaという単語があれば日本語Wikiがヒットしやすい
    search_query = f"{ticker} {company_name} Wikipedia"
    
    print(f"  🔍 Wikiを検索中: {search_query} ...")
    
    try:
        with DDGS() as ddgs:
            # 日本語結果を優先 (region='jp-jp')
            results = ddgs.text(search_query, region='jp-jp', max_results=3)
            for r in results:
                url = r.get('href', '')
                # 日本語WikipediaのURLのみ採用
                if 'ja.wikipedia.org/wiki/' in url:
                    return url
    except Exception as e:
        print(f"    Search Error: {e}")
        time.sleep(5) # エラー時は少し待つ
    
    return None

def fetch_history_from_url(ticker, url):
    """ 指定されたWikipedia URLから沿革を取得 """
    print(f"    📖 解析中: {url}")
    
    events = []
    try:
        res = requests.get(url)
        if res.status_code != 200:
            print("    -> アクセス失敗")
            return []

        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 年号の正規表現 (2015年 ... 2025年)
        year_pattern = re.compile(r'(' + '|'.join([str(y) for y in range(START_YEAR, END_YEAR+1)]) + r')年')
        
        # 箇条書き(li)と定義リスト(dd)と段落(p)をすべてチェック
        content_text = []
        target_tags = soup.find_all(['li', 'dd', 'p'])
        
        for tag in target_tags:
            content_text.append(tag.get_text().strip())

        for text in content_text:
            # ノイズ除去（短すぎる行や、Wikipediaのメニューなどは飛ばす）
            if len(text) < 10: continue

            # "20xx年 - 〇〇" や "20xx年（平成xx年）x月 - 〇〇" などの形式を探す
            match = year_pattern.search(text)
            if match:
                year_str = match.group(1)
                year_int = int(year_str)
                
                # 年号より後ろの部分をイベント内容とする
                # "2018年10月 - 〇〇を買収" -> "10月 - 〇〇を買収"
                # splitの回数を1回に制限
                parts = text.split(year_str + '年', 1)
                if len(parts) < 2: continue
                
                event_text = parts[1].strip()
                
                # 先頭の（平成xx年）などを除去
                event_text = re.sub(r'（[^）]+）', '', event_text).strip()
                
                # 月を解析
                month = 6 # デフォルト
                day = 15
                
                month_match = re.search(r'(\d{1,2})月', event_text)
                if month_match:
                    month = int(month_match.group(1))
                    
                    # 日付まであるか？
                    day_match = re.search(r'(\d{1,2})日', event_text)
                    if day_match:
                        day = int(day_match.group(1))

                # 不要な記号削除
                clean_desc = re.sub(r'^[-–:：\s]+', '', event_text) # 先頭のハイフン削除
                clean_desc = re.sub(r'\[\d+\]', '', clean_desc).strip() # 注釈削除 [1]
                
                if len(clean_desc) < 5: continue

                # タイトル生成
                title = clean_desc[:30] + "..." if len(clean_desc) > 30 else clean_desc
                
                score = get_sentiment_score(clean_desc)
                
                try:
                    event_date = datetime.date(year_int, month, day)
                    
                    # 重複チェック用タプルを作成してリスト内を検索してもいいが、
                    # DB保存時の重複排除に任せる
                    events.append({
                        "event_date": event_date,
                        "ticker_code": ticker,
                        "category": "History",
                        "title": title,
                        "description": f"{clean_desc} (出所: Wikipedia)",
                        "sentiment_score": score,
                        "importance": 4
                    })
                except:
                    continue

    except Exception as e:
        print(f"    Error: {e}")
        
    print(f"    -> {len(events)} 件のイベントを抽出")
    return events

def main():
    print("🚀 Wikipedia(検索機能付き)からの歴史イベント収集を開始します...")
    engine = get_db_engine()

    # 1. 既存のゴミニュースを削除
    print("🧹 過去の失敗ニュースデータを削除中...")
    with engine.begin() as conn:
        # 前回入れた変なデータや、Newsカテゴリを一掃
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News' OR category = 'History'"))

    # 2. 企業リスト
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    total_companies = len(df_comp)
    
    all_events = []

    # 3. ループ処理
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        comp_name = row['company_name']
        
        print(f"\n[{i+1}/{total_companies}] 処理中: {ticker}")
        
        # 1. URLを探す
        wiki_url = find_wiki_url(ticker, comp_name)
        
        if wiki_url:
            # 2. そのURLから沿革を抜く
            events = fetch_history_from_url(ticker, wiki_url)
            all_events.extend(events)
        else:
            print("    -> 日本語Wikipediaが見つかりませんでした。スキップします。")
        
        # 連続アクセス防止の待機
        time.sleep(2)

    # 4. 保存
    if all_events:
        print(f"\n📦 {len(all_events)} 件の歴史データを保存中...")
        df_events = pd.DataFrame(all_events)
        
        # 重複排除
        df_events.drop_duplicates(subset=['ticker_code', 'description'], inplace=True)
        
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print("✅ 完了しました！")
        
        # 確認
        print("\n🔍 データサンプル:")
        print(df_events[['event_date', 'ticker_code', 'description']].head(5))

    else:
        print("⚠️ データが取得できませんでした。")

if __name__ == "__main__":
    main()