import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse
import requests
from bs4 import BeautifulSoup
import re
import time
import datetime

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
    pos_words = ['上場', '買収', '提携', '設立', '開発', '発売', '最高', '黒字', '受賞', '採用', '開始', '成功', '増資', '好調', '選定']
    neg_words = ['赤字', '撤退', '中止', '延期', '不祥事', '不正', '処分', '辞任', '解散', '課徴金', '訴訟', '排除', '低迷', '売却']
    for w in pos_words:
        if w in text: score += 0.4
    for w in neg_words:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def get_japanese_company_name(ticker):
    """ Yahoo!ファイナンスから日本語の正式名称を取得し、余計な文字を削除 """
    try:
        url = f"https://finance.yahoo.co.jp/quote/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code != 200:
            return None
            
        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 会社名が含まれるH1タグを取得
        h1 = soup.find('h1')
        if h1:
            raw_name = h1.get_text()
        else:
            # H1がない場合はtitleタグから取得して加工
            raw_name = soup.title.string if soup.title else ""

        # --- ここが修正ポイント: ゴミ文字の徹底排除 ---
        name = raw_name
        
        # 1. Yahoo特有の接尾辞を削除
        name = name.replace('の株価・株式情報', '')
        name = name.replace(' - Yahoo!ファイナンス', '')
        
        # 2. 証券コード部分 【xxxx】 を削除
        name = re.sub(r'【.*?】', '', name)
        
        # 3. 法人格などを削除 (Wikiのタイトルは通常法人格を含まない)
        name = name.replace('株式会社', '')
        name = name.replace('(株)', '')
        name = name.replace('株)', '') # (が取れた場合用
        
        # 4. 前後の空白削除
        name = name.strip()
        
        return name
    except:
        pass
    return None

def fetch_wiki_events(ticker, jp_company_name):
    """ 日本語Wikipediaから沿革を取得 """
    
    # URL生成
    wiki_url = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(jp_company_name)}"
    print(f"  📖 Wiki解析: {jp_company_name} ({wiki_url})")

    events = []
    try:
        res = requests.get(wiki_url, timeout=10)
        
        # 404なら「_(企業)」をつけて再トライ
        if res.status_code == 404:
            wiki_url_2 = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(jp_company_name + '_(企業)')}"
            res = requests.get(wiki_url_2, timeout=10)
            if res.status_code != 200:
                print("    -> Wikiページが見つかりませんでした")
                return []
            else:
                print("    -> '_(企業)' 付きで見つかりました")

        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 年号パターン (2015年〜2025年)
        year_pattern = re.compile(r'(' + '|'.join([str(y) for y in range(START_YEAR, END_YEAR+1)]) + r')年')

        # 抽出対象: <li>(箇条書き), <dd>(定義), <p>(本文)
        target_texts = [tag.get_text() for tag in soup.find_all(['li', 'dd', 'p'])]

        count = 0
        for text in target_texts:
            # 年号が含まれているかチェック
            match = year_pattern.search(text)
            if match:
                year_str = match.group(1)
                year_int = int(year_str)
                
                # 年号で分割して、それ以降の文章を取得
                if year_str + '年' in text:
                    content = text.split(year_str + '年', 1)[1].strip()
                else:
                    continue
                
                # 短すぎるものはノイズとして除外
                if len(content) < 5: continue

                # 月の解析 (x月)
                month = 6 # デフォルト
                day = 15
                month_match = re.search(r'(\d{1,2})月', content)
                if month_match:
                    month = int(month_match.group(1))
                    # 日付 (x日)
                    day_match = re.search(r'(\d{1,2})日', content)
                    if day_match:
                        day = int(day_match.group(1))
                
                # テキスト整形
                # 先頭の記号削除 (- 〇〇, ：〇〇)
                clean_desc = re.sub(r'^[-–:：\s]+', '', content)
                # 注釈削除 ([1], [注釈1])
                clean_desc = re.sub(r'\[[^\]]+\]', '', clean_desc).strip()
                
                # センチメント
                score = get_sentiment_score(clean_desc)
                
                # タイトル (長すぎる場合は省略)
                title = clean_desc[:40] + "..." if len(clean_desc) > 40 else clean_desc
                
                try:
                    event_date = datetime.date(year_int, month, day)
                    
                    events.append({
                        "event_date": event_date,
                        "ticker_code": ticker,
                        "category": "History",
                        "title": title,
                        "description": f"{clean_desc} (出所: Wikipedia)",
                        "sentiment_score": score,
                        "importance": 4
                    })
                    count += 1
                except:
                    continue
                    
        print(f"    -> {count} 件のイベントを取得")

    except Exception as e:
        print(f"    Error: {e}")

    return events

def main():
    print("🚀 企業沿革データ収集(v2: 社名クリーニング強化版)を開始します...")
    engine = get_db_engine()

    # 1. 既存データのクリア
    print("🧹 既存のニュース・履歴データを削除中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category IN ('News', 'History')"))

    # 2. 企業リスト取得
    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    all_events = []
    
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        print(f"\n[{i+1}/{len(df_comp)}] 処理中: {ticker}")
        
        # 1. Yahooファイナンスから日本語社名を取得 (ゴミ除去済み)
        jp_name = get_japanese_company_name(ticker)
        
        if not jp_name:
            jp_name = db_name # 取得できなければDBの名前(英語かもしれない)を使う
            print(f"    (Yahooから取得失敗。DB名を使用: {jp_name})")
        
        # 2. Wikipediaから沿革を取得
        events = fetch_wiki_events(ticker, jp_name)
        all_events.extend(events)
        
        # サーバー負荷軽減
        time.sleep(2)

    # 3. 保存
    if all_events:
        print(f"\n📦 {len(all_events)} 件の歴史データを保存中...")
        df_events = pd.DataFrame(all_events)
        # 重複排除
        df_events.drop_duplicates(subset=['ticker_code', 'description'], inplace=True)
        
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print("✅ 完了しました！")
        
        print("\n🔍 取得データサンプル:")
        print(df_events[['event_date', 'ticker_code', 'title']].head(5))
    else:
        print("⚠️ データが取得できませんでした。")

if __name__ == "__main__":
    main()