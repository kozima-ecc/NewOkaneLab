import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import feedparser
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

# True: 実行時に「ニュース」データを全消去してリセットします
RESET_NEWS_DATA = True
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

# ---------------------------------------------------------
# テキスト処理
# ---------------------------------------------------------
def clean_html_and_format(text_content):
    """ HTMLタグ除去 & ノイズ除去 """
    try:
        soup = BeautifulSoup(text_content, "html.parser")
        text = soup.get_text(separator=" ").strip()
        
        # Google News特有のノイズ除去
        text = text.replace("&nbsp;", " ")
        text = re.sub(r'\.\.\.$', '', text) # 末尾の...を消す
        
        return text
    except:
        return text_content

def analyze_sentiment_jp(text_content):
    """ 日本語簡易センチメント (-1.0 ~ 1.0) """
    score = 0.0
    text_content = str(text_content)
    
    # ポジティブワード (株価上昇要因)
    pos_words = [
        '増益', '最高益', '好調', '上昇', '買収', '提携', '黒字', '拡大', '成功', '期待', 
        'ポジティブ', '増配', '自社株買い', '新製品', '承認', '回復', 'ストップ高', 
        '急伸', '続伸', '反発', '上振れ', '上方修正'
    ]
    # ネガティブワード (株価下落要因)
    neg_words = [
        '減益', '赤字', '下落', '不振', '中止', '延期', '撤退', '懸念', 'ネガティブ', 
        '不祥事', '違反', '解約', 'リストラ', '下方修正', '疑義', 'ストップ安', 
        '急落', '続落', '反落', '下振れ', '失望'
    ]
    
    for w in pos_words:
        if w in text_content: score += 0.4
    for w in neg_words:
        if w in text_content: score -= 0.4
        
    return max(-1.0, min(1.0, score))

# ---------------------------------------------------------
# Google News RSS取得 (全て日本語環境で検索)
# ---------------------------------------------------------
def fetch_google_news_jp(ticker, search_query):
    """
    日本語のGoogleニュースを検索する
    ticker: DB登録用の銘柄コード
    search_query: 検索に使うキーワード
    """
    # 日本のニュース、日本語言語設定で検索
    enc_query = urllib.parse.quote(search_query)
    rss_url = f"https://news.google.com/rss/search?q={enc_query}&hl=ja&gl=JP&ceid=JP:ja"
    
    print(f"  Fetching news for: {search_query} ...")
    
    try:
        feed = feedparser.parse(rss_url)
        events = []
        
        # 最新3件を取得
        for entry in feed.entries[:3]:
            title = entry.title
            link = entry.link
            
            # ノイズフィルタ (スポーツなどの誤爆を除外)
            if ticker in ['V', 'MA']: # Visa, Mastercardなどが誤爆しやすい
                if any(x in title for x in ['vs', 'VS', 'サッカー', '試合', '選手権', '勝']):
                    continue

            # 日付パース
            try:
                dt = datetime.datetime(*entry.published_parsed[:6])
                pub_date = dt.date()
            except:
                pub_date = datetime.date.today()

            # 詳細(description)の取得とクリーニング
            # Google Newsは description にニュース提供元やスニペットを入れる
            raw_summary = entry.get('description', '')
            
            # HTMLタグを除去して綺麗なテキストにする
            clean_summary = clean_html_and_format(raw_summary)
            
            # サイト名(Google News - xxx)のようなゴミが残っていたら削除
            if "Google News" in clean_summary:
                clean_summary = clean_summary.split("Google News")[0].strip()

            # 要約が取れなかった場合はタイトルをコピー
            if len(clean_summary) < 5:
                description = title
            else:
                description = clean_summary

            # センチメント分析 (タイトル + 要約)
            score = analyze_sentiment_jp(f"{title} {description}")

            events.append({
                "event_date": pub_date,
                "ticker_code": ticker,
                "category": "News",
                "title": title,
                "description": description,
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
    print(" ニュース収集を開始します...")
    engine = get_db_engine()

    # 1. 掃除 (中途半端な翻訳データやURLのみのデータを削除)
    with engine.begin() as conn:
        if RESET_NEWS_DATA:
            print(" イベントテーブルを整理します...")
            # Earnings(決算)とMarket(マクロ)以外のニュース系データを全削除
            sql = """
                DELETE FROM fact_events 
                WHERE category NOT IN ('Earnings', 'Market', 'Politics', 'Economy', 'Disaster', 'Medical', 'Geopolitics', 'Social')
            """
            conn.execute(text(sql))
            print("   -> 削除完了")

    # 2. 企業リスト取得
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    all_events = []

    # 3. ループ処理
    for _, row in df_comp.iterrows():
        ticker = row['ticker_code']
        comp_name = row['company_name']
        
        # 検索クエリの作成
        if ticker.endswith(".T"):
            # 日本株: 「企業名」で検索 (例: トヨタ自動車)
            # (株式会社などを除去)
            search_word = comp_name.replace("株式会社", "").replace("Corp.", "").replace("Ltd.", "").strip()
        else:
            # 米国株: 「ティッカー + 株」または「企業名(英語) + 株」で検索
            # これにより "Apple 株" "NVDA 株" のような金融ニュースがヒットする
            # (英語名そのままでも日本のGoogle Newsは日本語記事を返してくれる)
            
            # 例: "NVDA" -> "NVDA 株" (金融情報を強制)
            # 例: "Visa Inc." -> "Visa"
            simple_name = comp_name.replace("Inc.", "").replace("Corporation", "").replace("Corp.", "").replace("Co.", "").strip()
            
            # ティッカーが一般的な単語(V, MA)の場合は社名を使う
            if len(ticker) <= 2:
                search_word = f"{simple_name} 株"
            else:
                search_word = f"{ticker} 株" # ティッカーの方がノイズが少ないことが多い

        # 共通関数で取得 (すべて日本語で返ってくる)
        events = fetch_google_news_jp(ticker, search_word)
            
        all_events.extend(events)
        time.sleep(1) # サーバー負荷軽減

    # 4. 保存
    if all_events:
        print(f"\n {len(all_events)} 件のニュースをデータベースに保存中...")
        df_events = pd.DataFrame(all_events)
        
        # 重複排除
        df_events.drop_duplicates(subset=['ticker_code', 'title'], inplace=True)
        
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print(" 完了しました！")
        
        # 確認表示
        print("\n 取得データサンプル:")
        print(df_events[['ticker_code', 'title']].head(5))
        print("\n 詳細(description)サンプル:")
        for d in df_events['description'].head(3):
            print(f" - {d}")
    else:
        print(" ニュースが取得できませんでした。")

if __name__ == "__main__":
    main()