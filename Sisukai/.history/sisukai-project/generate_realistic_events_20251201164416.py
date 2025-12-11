import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import time
import random
from GoogleNews import GoogleNews
import dateparser
import re

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

# 取得期間設定
START_YEAR = 2015
END_YEAR = 2024

# 1社・1年あたり何件保存するか (重要ニュースだけに絞るため少なめに)
TOP_N_PER_YEAR = 3
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def clean_text(text):
    if not text: return ""
    # HTMLタグや余計な空白を除去
    text = re.sub(r'<[^>]+>', '', str(text))
    text = text.replace('&nbsp;', ' ').strip()
    return text

def parse_news_date(date_str):
    """ '2年前', '2020/01/01' などの表記を日付オブジェクトに変換 """
    if not date_str:
        return None
    try:
        dt = dateparser.parse(str(date_str))
        if dt:
            return dt.date()
    except:
        pass
    return None

def get_sentiment_score(text_content):
    """ 簡易センチメント分析 """
    score = 0.0
    pos_words = ['増益', '最高', '好調', '上昇', '買収', '提携', '成功', '新製品', '再開', '急騰', 'Surge', 'Jump', 'Record', 'Profit', 'Buy', 'Deal']
    neg_words = ['減益', '赤字', '下落', '不振', '中止', '延期', '撤退', '不祥事', '急落', 'Plunge', 'Drop', 'Loss', 'Cut', 'Fail']
    
    for w in pos_words:
        if w in text_content: score += 0.3
    for w in neg_words:
        if w in text_content: score -= 0.3
    return max(-1.0, min(1.0, score))

def fetch_historical_news_by_year(ticker, search_word, lang, region, engine):
    all_found = []
    
    # GoogleNewsインスタンスの初期化
    googlenews = GoogleNews(lang=lang, region=region)
    
    print(f"  📅 {ticker} ({search_word}) の過去ニュースを検索中...")
    
    # 年ごとにループ
    for year in range(START_YEAR, END_YEAR + 1):
        # 期間設定 (1/1 ~ 12/31)
        start_date = f"01/01/{year}"
        end_date = f"12/31/{year}"
        
        try:
            # 設定をクリアして再検索
            googlenews.clear()
            googlenews.set_time_range(start_date, end_date)
            googlenews.search(search_word)
            
            results = googlenews.results()
            
            # 結果が取れなかった場合、少し待って再試行
            if not results:
                time.sleep(2)
                googlenews.search(search_word)
                results = googlenews.results()

            count = 0
            for res in results:
                if count >= TOP_N_PER_YEAR: break
                
                title = clean_text(res.get('title', ''))
                desc = clean_text(res.get('desc', ''))
                media = clean_text(res.get('media', ''))
                date_str = res.get('date', '')
                
                # 日付解析
                event_date = parse_news_date(date_str)
                # 日付が取れなかった、あるいは検索範囲外の日付(最近のニュースが混ざるバグ対策)の場合は補正
                if not event_date or event_date.year != year:
                    # 強制的にその年の中頃にしておく（シミュレーション用データとしては「その年にあった」ことが重要）
                    event_date = datetime.date(year, 6, 15)

                # センチメント
                score = get_sentiment_score(title + desc)
                
                # 詳細文の整形
                full_desc = desc
                if media:
                    full_desc += f" (出所: {media})"

                if len(title) > 5: # 短すぎるゴミを除外
                    all_found.append({
                        "event_date": event_date,
                        "ticker_code": ticker,
                        "category": "News", # 過去ニュース
                        "title": title,
                        "description": full_desc,
                        "sentiment_score": score,
                        "importance": 3
                    })
                    count += 1
            
            print(f"    - {year}年: {count}件", end="", flush=True)
            
            # アクセスブロック回避のための待機
            time.sleep(random.uniform(2.0, 4.0))
            
        except Exception as e:
            print(f"X", end="", flush=True)
            time.sleep(5) # エラー時は長めに休む
            
    print("") # 改行
    
    # DBへ保存 (1社終わるごとにコミット)
    if all_found:
        df = pd.DataFrame(all_found)
        # 重複排除
        df.drop_duplicates(subset=['title'], inplace=True)
        try:
            df.to_sql('fact_events', engine, if_exists='append', index=False)
        except:
            pass # 重複エラーなどは無視

def main():
    print("🚀 過去10年分のリアルニュース収集を開始します...")
    print(f"   対象期間: {START_YEAR}年 ～ {END_YEAR}年")
    print("   ※時間がかかります (目安: 1社あたり約30秒～1分)")
    
    engine = get_db_engine()

    # 1. 過去の自動生成データ(MarketMoveやEarnings以外)を一掃
    print("🧹 過去のランダム生成イベントを削除中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category = 'News' OR category = 'Product' OR category = 'Scandal'"))

    # 2. 企業リスト取得
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    # 3. ループ処理
    total_companies = len(df_comp)
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        comp_name = row['company_name']
        
        print(f"\n[{i+1}/{total_companies}] 処理中: {ticker}")
        
        if ticker.endswith(".T"):
            # 日本株: 企業名(日本語)で検索
            # (株式会社などを除去)
            short_name = comp_name.replace("株式会社", "").replace("Corp.", "").replace("Ltd.", "").strip()
            fetch_historical_news_by_year(ticker, short_name, 'ja', 'JP', engine)
        else:
            # 米国株: 企業名(英語)で検索
            # (GoogleNewsライブラリは英語検索の方が精度が良い)
            short_name = comp_name.replace("Inc.", "").replace("Corporation", "").replace("Corp.", "").replace("Co.", "").strip()
            fetch_historical_news_by_year(ticker, short_name, 'en', 'US', engine)

    print("\n🎉 全工程完了しました！")

if __name__ == "__main__":
    main()