import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import feedparser
from textblob import TextBlob
import time
import re
from bs4 import BeautifulSoup

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

# Trueにすると、実行時に既存のイベントデータを全削除します（推奨）
RESET_ALL_DATA = True
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

# ---------------------------------------------------------
# テキスト処理 & センチメント分析
# ---------------------------------------------------------
def clean_html(html_text):
    """ HTMLタグを除去してプレーンテキストにする """
    try:
        return BeautifulSoup(html_text, "html.parser").get_text()
    except:
        return html_text

def analyze_sentiment_en(text_content):
    """ 英語センチメント (-1.0 ~ 1.0) """
    try:
        blob = TextBlob(text_content)
        return blob.sentiment.polarity
    except:
        return 0.0

def analyze_sentiment_jp(text_content):
    """ 日本語簡易センチメント """
    score = 0.0
    text_content = str(text_content)
    # ポジティブワード
    pos_words = ['増益', '最高', '好調', '上昇', '買収', '提携', '黒字', '拡大', '成功', '期待', 'ポジティブ', '配当', '自社株買い', '新製品', '承認', '提携', 'デビュー', '回復']
    # ネガティブワード
    neg_words = ['減益', '赤字', '下落', '不振', '中止', '延期', '撤退', '懸念', 'ネガティブ', '不祥事', '違反', '解約', 'リストラ', '下方修正', '疑義']
    
    for w in pos_words:
        if w in text_content: score += 0.3
    for w in neg_words:
        if w in text_content: score -= 0.3
        
    return max(-1.0, min(1.0, score))

# ---------------------------------------------------------
# Google News RSS取得 (日米共通ロジック)
# ---------------------------------------------------------
def fetch_google_news(ticker, query_name, lang='ja', region='JP'):
    """
    Google News RSSからニュースと要約を取得
    lang: 'ja' or 'en'
    region: 'JP' or 'US'
    """
    # 検索クエリ: 企業名
    enc_query = urllib.parse.quote(query_name)
    
    if lang == 'ja':
        rss_url = f"https://news.google.com/rss/search?q={enc_query}&hl=ja&gl=JP&ceid=JP:ja"
    else:
        rss_url = f"https://news.google.com/rss/search?q={enc_query}&hl=en-US&gl=US&ceid=US:en"
    
    print(f"  Fetching news for: {query_name} ({ticker}) ...")
    
    try:
        feed = feedparser.parse(rss_url)
        events = []
        
        # 最新3件を取得 (多すぎるとノイズになるため)
        for entry in feed.entries[:3]:
            title = entry.title
            link = entry.link
            
            # 日付パース
            try:
                dt = datetime.datetime(*entry.published_parsed[:6])
                pub_date = dt.date()
            except:
                pub_date = datetime.date.today()

            # ★ここが重要: 要約(description)を取得してHTMLタグを除去
            raw_summary = entry.get('description', '')
            clean_summary = clean_html(raw_summary)
            
            # 要約が短すぎる場合はタイトルを使う
            if len(clean_summary) < 10:
                description = title
            else:
                description = clean_summary

            # センチメント分析 (タイトル + 要約)
            full_text = f"{title} {description}"
            if lang == 'ja':
                score = analyze_sentiment_jp(full_text)
            else:
                score = analyze_sentiment_en(full_text)

            events.append({
                "event_date": pub_date,
                "ticker_code": ticker,
                "category": "News",
                "title": title,
                "description": description, # URLではなく要約を入れる
                "sentiment_score": score,
                "importance": 3
            })
            
        return events
    except Exception as e:
        print(f"    Error: {e}")
        return []

# ---------------------------------------------------------
# メイン処理
# ---------------------------------------------------------
def main():
    print("🚀 リアルニュース収集(v3: 要約取得版)を開始します...")
    engine = get_db_engine()

    # 1. 掃除 (URLだけのデータや古い失敗データを削除)
    with engine.begin() as conn:
        if RESET_ALL_DATA:
            print("🧹 イベントテーブルを全消去してリセットします (TRUNCATE)...")
            conn.execute(text("TRUNCATE TABLE fact_events"))
        else:
            print("🧹 'Source:' や 'Google News' で始まるURLだけのデータを削除します...")
            # URLっぽい記述の行を削除
            sql = """
                DELETE FROM fact_events 
                WHERE description LIKE 'Source:%' 
                   OR description LIKE 'Google News -%'
                   OR description LIKE 'http%'
            """
            conn.execute(text(sql))

    # 2. 企業リスト取得
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    all_events = []

    # 3. ループ処理
    for _, row in df_comp.iterrows():
        ticker = row['ticker_code']
        comp_name = row['company_name']
        
        # 日本株 (.T)
        if ticker.endswith(".T"):
            # 正式名称から「株式会社」などを取って検索しやすくする
            short_name = comp_name.replace("株式会社", "").replace("Corp.", "").replace("Ltd.", "").strip()
            # 日本語ニュース取得
            events = fetch_google_news(ticker, short_name, lang='ja', region='JP')
        
        # 米国株 (yfinanceを使わずGoogle News英語版を使う -> 安定して要約が取れる)
        else:
            # 英語ニュース取得
            events = fetch_google_news(ticker, ticker, lang='en', region='US')
            
        all_events.extend(events)
        time.sleep(1) # マナー待機

    # 4. 保存
    if all_events:
        print(f"\n📦 {len(all_events)} 件のニュースをデータベースに保存中...")
        df_events = pd.DataFrame(all_events)
        
        # 重複排除 (念のため)
        df_events.drop_duplicates(subset=['ticker_code', 'title'], inplace=True)
        
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print("✅ 完了しました！")
        
        # 確認表示
        print("\n🔍 取得データサンプル (descriptionを確認):")
        print(df_events[['ticker_code', 'title', 'description']].head(5))
    else:
        print("⚠️ ニュースが取得できませんでした。")

if __name__ == "__main__":
    main()