import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import datetime
import time
import random
import re
from duckduckgo_search import DDGS

# =========================================================
# ⚙️ 設定エリア
# =========================================================
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'root' 
MYSQL_HOST = 'localhost'
MYSQL_DB = 'trade_sim'

# 取得する期間
START_YEAR = 2015
END_YEAR = 2025

# 各年・各社ごとの取得件数 (重要ニュースに絞るため少なめに)
MAX_RESULTS = 3
# =========================================================

def get_db_engine():
    encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD)
    conn_str = f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}/{MYSQL_DB}?charset=utf8mb4"
    return create_engine(conn_str)

def get_sentiment_score(text_content):
    """ 簡易センチメント分析 """
    score = 0.0
    text_content = str(text_content)
    pos_words = ['増益', '最高', '好調', '上昇', '買収', '提携', '黒字', '拡大', '成功', '期待', 'ポジティブ', '配当', '自社株買い', '新製品', '承認', '回復', 'ストップ高', '急伸']
    neg_words = ['減益', '赤字', '下落', '不振', '中止', '延期', '撤退', '懸念', 'ネガティブ', '不祥事', '違反', '解約', 'リストラ', '下方修正', '疑義', 'ストップ安', '急落', '逮捕', '不正']
    
    for w in pos_words:
        if w in text_content: score += 0.4
    for w in neg_words:
        if w in text_content: score -= 0.4
    return max(-1.0, min(1.0, score))

def search_ddg_historical(ticker, company_name, year):
    """ DuckDuckGoで特定年のニュースを検索 """
    
    # 検索クエリ作成: "企業名 ニュース 20xx年"
    # 米国株もカタカナ名が含まれていれば日本語記事がヒットしやすい
    # 含まれていなければ英語名で検索するが、今回は日本語記事を狙う
    
    # 会社名から余計なものを消す
    clean_name = company_name.replace("株式会社", "").replace("Inc.", "").replace("Corp.", "").replace("Ltd.", "").strip()
    
    # 検索ワード (例: "トヨタ自動車 ニュース 2018")
    query = f"{clean_name} ニュース {year}"
    
    results = []
    try:
        with DDGS() as ddgs:
            # region='jp-jp' で日本の検索結果を優先
            ddg_gen = ddgs.text(query, region='jp-jp', safesearch='off', max_results=MAX_RESULTS)
            
            for r in ddg_gen:
                title = r.get('title', '')
                body = r.get('body', '')
                href = r.get('href', '')
                
                # ドメイン名を抽出して出所に設定
                source = "Web"
                if "http" in href:
                    try:
                        source = urllib.parse.urlparse(href).netloc.replace('www.', '')
                    except:
                        pass

                # 日付の推定
                # 過去のニュース検索だと正確な日付(月日)がメタデータにないことが多い。
                # そのため、「その年のランダムな日」または「6月30日(中間)」を割り当てる。
                # シミュレーション用としては「その年に起きたこと」として扱う。
                
                # 記事本文に "X月X日" があればそれを採用するロジックを入れると精度が上がるが、
                # ここでは簡易的に「その年のランダムな営業日」とする
                rand_month = random.randint(1, 12)
                rand_day = random.randint(1, 28)
                event_date = datetime.date(year, rand_month, rand_day)

                # センチメント
                score = get_sentiment_score(title + body)

                results.append({
                    "event_date": event_date,
                    "ticker_code": ticker,
                    "category": "News",
                    "title": title,
                    "description": f"{body} (出所: {source})",
                    "sentiment_score": score,
                    "importance": 3
                })
                
    except Exception as e:
        print(f"    Error searching {query}: {e}")
        # エラー時は少し待つ
        time.sleep(5)
        
    return results

def main():
    print("🚀 過去10年分のリアルニュース収集(DuckDuckGo版)を開始します...")
    print(f"   対象期間: {START_YEAR}年 ～ {END_YEAR}年")
    
    engine = get_db_engine()

    # 1. 既存データのクリア (決算データなども一旦消すならここ。今回はNewsだけ消すか全消しか選ぶ)
    # ユーザー要望「全て削除(テーブルリセット)」に従い全削除
    print("🧹 イベントテーブルを完全にリセットします...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE fact_events"))

    # 2. 企業リスト取得
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    total_companies = len(df_comp)
    
    # 3. ループ処理
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        comp_name = row['company_name']
        
        print(f"\n[{i+1}/{total_companies}] {comp_name} ({ticker}) の歴史を収集中...")
        
        company_events = []
        
        # 年ごとに検索
        for year in range(START_YEAR, END_YEAR + 1):
            print(f"  - {year}年...", end="", flush=True)
            
            events = search_ddg_historical(ticker, comp_name, year)
            company_events.extend(events)
            
            print(f" {len(events)}件取得", end="", flush=True)
            
            # 待機 (重要: 連続アクセスを防ぐ)
            time.sleep(random.uniform(1.0, 2.0))
        
        # 1社分終わったら保存
        if company_events:
            df_save = pd.DataFrame(company_events)
            df_save.drop_duplicates(subset=['title'], inplace=True) # 重複排除
            df_save.to_sql('fact_events', engine, if_exists='append', index=False)
            print(" -> 保存完了")
        else:
            print(" -> データなし")

    print("\n🎉 全データの収集が完了しました！")

if __name__ == "__main__":
    main()