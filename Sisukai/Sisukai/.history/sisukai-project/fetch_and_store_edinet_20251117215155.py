import requests
import pandas as pd
import time
import datetime
import os
import io
import zipfile
import re
import yfinance as yf
from sqlalchemy import create_engine

# =========================================================
# 🔑 設定エリア
# =========================================================
API_KEY = "63715392921541a18b2cd6d1dbc05c15" 

# DBパス (1つ上の階層)
DB_PATH = 'sqlite:///../sisukai.db'
CSV_PATH = "EdinetcodeDlInfo.csv"

# 取得対象リスト (重複除去済み)
ALL_TICKERS = [
    "9984.T","7203.T","8306.T","6758.T","7751.T","9983.T","7974.T","9432.T","8035.T","6861.T",
    "4502.T","7201.T","7267.T","4901.T","9434.T","8267.T","8031.T","8411.T","8591.T","7205.T",
    "8604.T","6869.T","4503.T","8058.T","9987.T","6981.T","7979.T","4063.T","5947.T","6902.T",
    "7012.T","7011.T","9101.T","9020.T","9021.T",
    "NVDA","INTC","AAPL","MSFT","AMZN","TSLA","GOOGL","META","NFLX","CRM","V","MA","JPM","BAC","DIS","CSCO","ADBE","PYPL","TXN"
]
# 重複を除去
ALL_TICKERS = list(set(ALL_TICKERS))
# =========================================================

def main():
    if "ここに" in API_KEY:
        print("❌ エラー: APIキーを設定してください。")
        return

    try:
        engine = create_engine(DB_PATH)
        print(f"📂 データベース接続: {DB_PATH}")
    except Exception as e:
        print(f"❌ DB接続エラー: {e}")
        return

    # リストを日米に分割
    jp_tickers = [t for t in ALL_TICKERS if t.endswith(".T")]
    us_tickers = [t for t in ALL_TICKERS if not t.endswith(".T")]

    print(f"🎯 対象: 日本株 {len(jp_tickers)} 銘柄, 米国株 {len(us_tickers)} 銘柄")

    # Phase 1: 米国株 (yfinance)
    if us_tickers:
        print("\n🇺🇸 米国株のデータを取得中 (yfinance)...")
        fetch_us_stocks(us_tickers, engine)

    # Phase 2: 日本株 (EDINET)
    if jp_tickers:
        print("\n🇯🇵 日本株のデータを取得中 (EDINET)...")
        fetch_jp_stocks_edinet(jp_tickers, engine)

    print("\n🏁 全工程完了！")

# =========================================================
# 🇺🇸 米国株用ロジック
# =========================================================
def fetch_us_stocks(tickers, engine):
    count = 0
    for ticker in tickers:
        try:
            print(f"  Processing: {ticker} ... ", end="")
            stock = yf.Ticker(ticker)
            q_fin = stock.quarterly_income_stmt
            
            if q_fin is None or q_fin.empty:
                print("データなし")
                continue

            data_list = []
            for date_idx in q_fin.columns:
                try:
                    month = date_idx.month
                    year = date_idx.year
                    quarter = (month - 1) // 3 + 1
                    row = q_fin[date_idx]
                    
                    net_sales = row.get('Total Revenue', row.get('Operating Revenue'))
                    op_income = row.get('Operating Income', row.get('Operating Profit'))
                    net_income = row.get('Net Income')
                    eps = row.get('Basic EPS')
                    
                    if pd.isna(net_sales) and pd.isna(net_income): continue

                    data_list.append({
                        'ticker_code': ticker,
                        'fiscal_year': year,
                        'quarter': quarter,
                        'net_sales': float(net_sales) if not pd.isna(net_sales) else None,
                        'operating_income': float(op_income) if not pd.isna(op_income) else None,
                        'net_income': float(net_income) if not pd.isna(net_income) else None,
                        'eps': float(eps) if not pd.isna(eps) else None
                    })
                except: continue

            if data_list:
                df = pd.DataFrame(data_list)
                try:
                    df.to_sql('fact_financials', engine, if_exists='append', index=False)
                    print(f"✅ {len(df)}件 保存")
                    count += 1
                except:
                    print("保存エラー(重複等)")
            else:
                print("有効データなし")
            time.sleep(1)

        except Exception as e:
            print(f"❌ エラー: {e}")
    print(f"  -> 米国株 {count} 銘柄の処理完了")

# =========================================================
# 🇯🇵 日本株用ロジック
# =========================================================
def fetch_jp_stocks_edinet(target_tickers, engine):
    print("  🔍 EDINETマッピング読み込み中...")
    ticker_map = load_ticker_map(CSV_PATH)
    
    edinet_to_ticker = {v: k for k, v in ticker_map.items() if k in target_tickers}
    target_set = set(edinet_to_ticker.keys())

    if not target_set:
        print("  ❌ 対象銘柄のマッピングに失敗しました。")
        return

    search_dates = []
    today = datetime.date.today()
    for year in range(today.year, today.year - 10, -1):
        for month in [2, 5, 8, 11]: 
            for day in range(1, 16):
                try:
                    d = datetime.date(year, month, day)
                    if d <= today: search_dates.append(d)
                except: continue
    search_dates.sort(reverse=True)

    print(f"  📥 {len(search_dates)} 日分をスキャン開始...")
    processed_count = 0
    
    for target_date in search_dates:
        if target_date.weekday() >= 5: continue

        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {'date': target_date.strftime('%Y-%m-%d'), 'type': 2}
        headers = {'Ocp-Apim-Subscription-Key': API_KEY}

        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            if res.status_code != 200:
                time.sleep(0.5)
                continue
                
            docs = res.json().get('results', [])
            for doc in docs:
                e_code = doc.get('edinetCode')
                if e_code in target_set:
                    dtc = doc.get('docTypeCode', '')
                    if dtc in ['120', '140']:
                        ticker = edinet_to_ticker[e_code]
                        doc_id = doc['docID']
                        doc_desc = doc['docDescription']
                        filer_name = doc['filerName']
                        
                        print(f"\n  📄 発見: {filer_name} ({doc_desc})")
                        success = download_and_save_keyword_search(doc_id, ticker, doc_desc, engine)
                        if success: processed_count += 1
            print(".", end="", flush=True)
            time.sleep(0.5)
        except Exception as e:
            print(f"!", end="", flush=True)

    print(f"\n  ✅ 日本株処理完了: {processed_count} 件保存")

def parse_fiscal_info(doc_desc):
    fiscal_year = None; quarter = None
    try:
        if "第1四半期" in doc_desc: quarter = 1
        elif "第2四半期" in doc_desc: quarter = 2
        elif "第3四半期" in doc_desc: quarter = 3
        elif "第4四半期" in doc_desc: quarter = 4
        elif "有価証券報告書" in doc_desc: quarter = 4 
        date_matches = re.findall(r'(20\d{2})/(\d{1,2})/\d{1,2}', doc_desc)
        if date_matches:
            end_year, end_month = int(date_matches[-1][0]), int(date_matches[-1][1])
            if end_month >= 4: fiscal_year = end_year
            else: fiscal_year = end_year - 1
    except: pass
    return fiscal_year, quarter

def download_and_save_keyword_search(doc_id, ticker, doc_desc, engine):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {'type': 1}
    headers = {'Ocp-Apim-Subscription-Key': API_KEY}
    try:
        res = requests.get(url, params=params, headers=headers, stream=True, timeout=30)
        if res.status_code != 200: return False
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xbrl_files = [f for f in z.namelist() if f.endswith('.xbrl') and 'PublicDoc' in f]
            if not xbrl_files: return False
            with z.open(xbrl_files[0]) as f:
                xbrl_text = f.read().decode('utf-8', errors='ignore')
            
            data_dict = {}
            fy, q = parse_fiscal_info(doc_desc)
            data_dict['fiscal_year'] = fy; data_dict['quarter'] = q; data_dict['ticker_code'] = ticker

            def extract_by_keywords(keywords):
                candidates = []
                for kw in keywords:
                    pattern = re.compile(r'<[a-zA-Z0-9_:]*?' + kw + r'[a-zA-Z0-9_]*? [^>]*>\s*([0-9\.\-]+)\s*<', re.IGNORECASE)
                    matches = pattern.findall(xbrl_text)
                    for val_str in matches:
                        try:
                            val = float(val_str)
                            if val > 100_000_000: candidates.append(val)
                        except: pass
                return max(candidates) if candidates else None

            # IFRS対応強化: タグ名を網羅
            data_dict['net_sales'] = extract_by_keywords(['Revenue', 'NetSales', 'OperatingRevenue', 'Sales'])
            op_val = extract_by_keywords(['OperatingProfit', 'ProfitFromOperations', 'OperatingIncome'])
            if op_val: data_dict['operating_income'] = op_val
            net_val = extract_by_keywords(['ProfitAttributableToOwners', 'NetIncome', 'ProfitLossAttributableToOwners', 'ProfitLoss'])
            if net_val: data_dict['net_income'] = net_val
            
            eps_candidates = []
            pattern_eps = re.compile(r'<[a-zA-Z0-9_:]*?EarningsPerShare[a-zA-Z0-9_]*? [^>]*>\s*([0-9\.\-]+)\s*<', re.IGNORECASE)
            for val_str in pattern_eps.findall(xbrl_text):
                try: eps_candidates.append(float(val_str))
                except: pass
            if eps_candidates: data_dict['eps'] = max(eps_candidates)

            # 【改良】売上が取れなくても、利益が取れていれば保存する
            if data_dict.get('net_sales') or data_dict.get('net_income') or data_dict.get('operating_income'):
                df = pd.DataFrame([data_dict])
                try:
                    df.to_sql('fact_financials', engine, if_exists='append', index=False)
                    s_str = f"{data_dict.get('net_sales', 0):,.0f}"
                    print(f"    💾 保存: 売上={s_str}")
                    return True
                except: return False
            else: return False
    except: return False

def load_ticker_map(csv_path):
    mapping = {}
    try:
        try: df = pd.read_csv(csv_path, encoding='utf-8', skiprows=1)
        except: df = pd.read_csv(csv_path, encoding='cp932', skiprows=1)
        for _, row in df.iterrows():
            s = str(row.get('証券コード', ''))
            e = str(row.get('ＥＤＩＮＥＴコード', ''))
            if len(s) >= 4 and e.startswith('E'):
                mapping[s[:4]+".T"] = e
    except: pass
    return mapping

if __name__ == "__main__":
    main()