import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import feedparser
import yfinance as yf
from textblob import TextBlob
import time
import re

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

# 既存のランダムデータを消すかどうか
CLEAR_OLD_DATA = True
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

# ---------------------------------------------------------
# センチメント分析 (簡易版)
# ---------------------------------------------------------
def analyze_sentiment_en(text_content):
    """ 英語ニュースの感情分析 (-1.0 ~ 1.0) """
    try:
        blob = TextBlob(text_content)
        return blob.sentiment.polarity
    except:
        return 0.0

def analyze_sentiment_jp(text_content):
    """ 日本語ニュースの感情分析 (キーワードベース簡易版) """
    # 本格的な分析には 'janome' やBERTモデルが必要だが、今回はキーワードで簡易判定
    score = 0.0
    pos_words = ['増益', '最高', '好調', '上昇', '買収', '提携', '黒字', '拡大', '成功', '期待', 'ポジティブ', '配当', '自社株買い']
    neg_words = ['減益', '赤字', '下落', '不振', '中止', '延期', '撤退', '懸念', 'ネガティブ', '不祥事', '違反', '解約']
    
    for w in pos_words:
        if w in text_content: score += 0.3
    for w in neg_words:
        if w in text_content: score -= 0.3
        
    return max(-1.0, min(1.0, score))

# ---------------------------------------------------------
# 🇺🇸 米国株ニュース取得 (yfinance)
# ---------------------------------------------------------
def fetch_us_news(ticker, engine):
    print(f"  🇺🇸 {ticker} のニュースを取得中...")
    try:
        stock = yf.Ticker(ticker)
        news_list = stock.news
        
        events = []
        for n in news_list:
            # タイムスタンプ変換
            pub_date = datetime.datetime.fromtimestamp(n['providerPublishTime']).date()
            title = n['title']
            link = n['link']
            
            # センチメント分析
            score = analyze_sentiment_en(title)
            
            events.append({
                "event_date": pub_date,
                "ticker_code": ticker,
                "category": "News",
                "title": title,
                "description": f"Source: {n.get('publisher', 'Yahoo')} - {link}",
                "sentiment_score": score,
                "importance": 3
            })
        return events
    except Exception as e:
        print(f"    Error: {e}")
        return []

# ---------------------------------------------------------
# 🇯🇵 日本株ニュース取得 (Google News RSS)
# ---------------------------------------------------------
def fetch_jp_news(ticker, company_name, engine):
    # Google News RSS URL (日本語)
    # 検索クエリ: 企業名
    query = urllib.parse.quote(company_name)
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
    
    print(f"  🇯🇵 {ticker} ({company_name}) のニュースを取得中...")
    
    try:
        feed = feedparser.parse(rss_url)
        events = []
        
        # 最新5件くらいを取得
        for entry in feed.entries[:5]:
            title = entry.title
            link = entry.link
            
            # 日付パース (Tue, 04 Jun 2024 01:00:00 GMT 形式)
            try:
                dt = datetime.datetime(*entry.published_parsed[:6])
                pub_date = dt.date()
            except:
                pub_date = datetime.date.today()

            # センチメント
            score = analyze_sentiment_jp(title)

            events.append({
                "event_date": pub_date,
                "ticker_code": ticker,
                "category": "News",
                "title": title,
                "description": f"Google News - {link}",
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
    print("🚀 リアルニュース収集を開始します...")
    engine = get_db_engine()

    # 1. 既存データのクリア (オプション)
    if CLEAR_OLD_DATA:
        print("🧹 既存のイベントデータをクリアします...")
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE fact_events"))

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
            events = fetch_jp_news(ticker, short_name, engine)
        
        # 米国株
        else:
            events = fetch_us_news(ticker, engine)
            
        all_events.extend(events)
        time.sleep(1) # アクセス負荷軽減

    # 4. 保存
    if all_events:
        print(f"\n📦 {len(all_events)} 件のニュースをデータベースに保存中...")
        df_events = pd.DataFrame(all_events)
        
        # 重複チェックは簡易的に行う (日付+Ticker+タイトルが同じなら弾くなど)
        # 今回はTRUNCATEしているのでそのままINSERT
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print("✅ 完了しました！")
        
        # サンプル表示
        print("\n🔍 取得データサンプル:")
        print(df_events[['event_date', 'ticker_code', 'title']].head(10))
    else:
        print("⚠️ ニュースが取得できませんでした。")

if __name__ == "__main__":
    main()