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
    score = 0.0
    pos_words = ['上場', '買収', '提携', '設立', '開発', '発売', '最高', '黒字', '受賞', '採用', '開始', '成功', '増資', '好調', '選定', '完了', '新設']
    neg_words = ['赤字', '撤退', '中止', '延期', '不祥事', '不正', '処分', '辞任', '解散', '課徴金', '訴訟', '排除', '低迷', '売却', '閉鎖']
    for w in pos_words:
        if w in text: score += 0.4
    for w in neg_words:
        if w in text: score -= 0.4
    return max(-1.0, min(1.0, score))

def get_japanese_company_name(ticker):
    try:
        url = f"https://finance.yahoo.co.jp/quote/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return None
            
        soup = BeautifulSoup(res.content, 'html.parser')
        h1 = soup.find('h1')
        raw_name = h1.get_text() if h1 else (soup.title.string if soup.title else "")

        name = raw_name
        name = name.replace('の株価・株式情報', '').replace(' - Yahoo!ファイナンス', '')
        name = re.sub(r'【.*?】', '', name)
        name = name.replace('株式会社', '').replace('(株)', '').replace('株)', '')
        return name.strip()
    except:
        return None

def parse_wiki_date(text, year_int):
    """ テキストから月日を推定する """
    month = 6
    day = 15
    
    # "10月" "10月1日" などのパターン
    m_match = re.search(r'(\d{1,2})月', text)
    if m_match:
        month = int(m_match.group(1))
        d_match = re.search(r'(\d{1,2})日', text)
        if d_match:
            day = int(d_match.group(1))
    
    try:
        return datetime.date(year_int, month, day)
    except:
        return datetime.date(year_int, 6, 15)

def fetch_wiki_events(ticker, jp_company_name):
    wiki_url = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(jp_company_name)}"
    print(f"  📖 Wiki解析: {jp_company_name} ({wiki_url})")

    events = []
    try:
        res = requests.get(wiki_url, timeout=10)
        
        if res.status_code == 404:
            wiki_url_2 = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(jp_company_name + '_(企業)')}"
            res = requests.get(wiki_url_2, timeout=10)
            if res.status_code != 200:
                print("    -> ページなし")
                return []
            else:
                print("    -> '(企業)' ページを発見")

        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 年号パターン (2015 ... 2025)
        # "2015年" または "2015." などの形式に対応
        target_years = range(START_YEAR, END_YEAR + 1)
        
        # 解析対象のタグ (箇条書き、定義リスト、テーブルの行)
        target_tags = soup.find_all(['li', 'dd', 'tr'])
        
        count = 0
        for tag in target_tags:
            text = tag.get_text().strip()
            if len(text) < 5: continue

            # 年号を含むかチェック
            found_year = None
            for y in target_years:
                # "2018年" や "2018." "2018/" などをチェック
                if str(y) in text:
                    # 文脈チェック: "2018円" とかは除外したいが簡易的に通す
                    # ただし、行頭付近にあるか確認
                    if re.search(rf'{y}[年\./]', text[:20]) or re.search(rf'{y}\s', text[:10]):
                        found_year = y
                        break
            
            if found_year:
                # イベント内容の抽出
                # 年号部分より後ろを取得
                # 正規表現で "20xx年(....)" のような部分を区切りにする
                split_pattern = rf'{found_year}[年\./\s]+(?:（.*?）)?'
                parts = re.split(split_pattern, text, maxsplit=1)
                
                if len(parts) > 1:
                    content = parts[1].strip()
                else:
                    content = text # 分割できなければそのまま使う

                # クリーニング
                clean_desc = re.sub(r'^[-–:：\s]+', '', content) # 先頭記号
                clean_desc = re.sub(r'\[[^\]]+\]', '', clean_desc) # 注釈 [1]
                clean_desc = clean_desc.strip()

                if len(clean_desc) < 5: continue
                
                # 日付解析
                event_date = parse_wiki_date(clean_desc, found_year)
                
                # センチメント
                score = get_sentiment_score(clean_desc)
                
                # タイトル
                title = clean_desc[:40] + "..." if len(clean_desc) > 40 else clean_desc

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

        print(f"    -> {count} 件取得")

    except Exception as e:
        print(f"    Error: {e}")

    return events

def main():
    print("🚀 企業沿革データ収集(v3: 解析強化版)を開始します...")
    engine = get_db_engine()

    print("🧹 既存データをクリア中...")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_events WHERE category = 'History'"))

    df_comp = pd.read_sql("SELECT ticker_code, company_name FROM companies", engine)
    
    all_events = []
    
    for i, row in df_comp.iterrows():
        ticker = row['ticker_code']
        db_name = row['company_name']
        
        print(f"\n[{i+1}/{len(df_comp)}] {ticker}")
        
        jp_name = get_japanese_company_name(ticker)
        if not jp_name: jp_name = db_name
        
        events = fetch_wiki_events(ticker, jp_name)
        all_events.extend(events)
        
        time.sleep(2)

    if all_events:
        print(f"\n📦 {len(all_events)} 件を保存中...")
        df_events = pd.DataFrame(all_events)
        df_events.drop_duplicates(subset=['ticker_code', 'description'], inplace=True)
        df_events.to_sql('fact_events', engine, if_exists='append', index=False)
        print("✅ 完了！")
    else:
        print("⚠️ データなし")

if __name__ == "__main__":
    main()