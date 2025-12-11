import requests
import pandas as pd
import time
import datetime
import os
import io
import zipfile
import re
from sqlalchemy import create_engine

# =========================================================
# 🔑 設定エリア
# =========================================================
API_KEY = "63715392921541a18b2cd6d1dbc05c15" 
TARGET_TICKERS = ["7203.T", "6758.T", "9984.T"]
DB_PATH = 'sqlite:///sisukai.db'
CSV_PATH = "EdinetcodeDlInfo.csv"
# =========================================================

def main():
    if "ここに" in API_KEY:
        print("❌ エラー: APIキーを設定してください。")
        return

    engine = create_engine(DB_PATH)
    print("🔍 マッピング読み込み中...")
    ticker_map = load_ticker_map(CSV_PATH)
    
    edinet_to_ticker = {v: k for k, v in ticker_map.items() if k in TARGET_TICKERS}
    target_set = set(edinet_to_ticker.keys())

    # --- 過去10年分の日付リスト ---
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

    print(f"\n📥 {len(search_dates)} 日分をスキャンし、データを取得・保存します...")
    
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
                        
                        print(f"\n📄 発見: {filer_name}")
                        
                        success = download_and_save_keyword_search(doc_id, ticker, doc_desc, engine)
                        if success:
                            processed_count += 1
            
            print(".", end="", flush=True)
            time.sleep(0.5)

        except Exception as e:
            print(f"!", end="", flush=True)

    print(f"\n\n✅ 全処理完了: {processed_count} 件のデータをDBに保存しました。")

def parse_fiscal_info(doc_desc):
    fiscal_year = None
    quarter = None
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

# ---------------------------------------------------------
# XBRLダウンロード & キーワード検索解析 (トヨタ対策)
# ---------------------------------------------------------
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
            data_dict['fiscal_year'] = fy
            data_dict['quarter'] = q
            data_dict['ticker_code'] = ticker

            # --- 数値抽出関数 (キーワード検索 & 最大値採用) ---
            def extract_by_keywords(keywords):
                candidates = []
                for kw in keywords:
                    # タグ名に keyword が含まれるものを探す (大文字小文字無視)
                    # パターン: <Prefix:TagKeywordTag ... > Value <
                    # (?i) は大文字小文字無視フラグ
                    pattern = re.compile(r'<[a-zA-Z0-9_:]*?' + kw + r'[a-zA-Z0-9_]*? [^>]*>\s*([0-9\.\-]+)\s*<', re.IGNORECASE)
                    matches = pattern.findall(xbrl_text)
                    for val_str in matches:
                        try:
                            val = float(val_str)
                            # 1億円未満の小さすぎる数字は除外 (ノイズ対策)
                            if val > 100_000_000: 
                                candidates.append(val)
                        except: pass
                
                if candidates:
                    return max(candidates) # 最大値を採用
                return None

            # 1. 売上高 (Revenue, Sales, OperatingRevenue)
            # トヨタは "Revenue" だけで数兆円のタグがある
            data_dict['net_sales'] = extract_by_keywords(['Revenue', 'NetSales', 'OperatingRevenue'])

            # 2. 営業利益 (OperatingProfit, ProfitFromOperations)
            # トヨタIFRSは "ProfitFromOperations"
            op_val = extract_by_keywords(['OperatingProfit', 'ProfitFromOperations', 'OperatingIncome'])
            if op_val: data_dict['operating_income'] = op_val

            # 3. 純利益 (ProfitAttributableToOwners...)
            # "Profit" だけだと営業利益や粗利を拾うので "Owners" も条件にする
            net_val = extract_by_keywords(['ProfitAttributableToOwners', 'NetIncome', 'ProfitLossAttributableToOwners'])
            if net_val: data_dict['net_income'] = net_val
            
            # 4. EPS
            # EPSは値が小さいので上記関数(1億以上)は使えない。専用処理。
            eps_candidates = []
            pattern_eps = re.compile(r'<[a-zA-Z0-9_:]*?EarningsPerShare[a-zA-Z0-9_]*? [^>]*>\s*([0-9\.\-]+)\s*<', re.IGNORECASE)
            for val_str in pattern_eps.findall(xbrl_text):
                try: eps_candidates.append(float(val_str))
                except: pass
            if eps_candidates: data_dict['eps'] = max(eps_candidates)

            # DB保存
            if data_dict.get('net_sales'):
                df = pd.DataFrame([data_dict])
                try:
                    df.to_sql('fact_financials', engine, if_exists='append', index=False)
                    s_str = f"{data_dict['net_sales']:,.0f}"
                    print(f"  💾 保存成功 [{fy} Q{q}]: 売上={s_str}")
                    return True
                except Exception as e:
                    print(f"  ❌ DB保存エラー: {e}")
                    return False
            else:
                print("  ⚠️ 数値抽出失敗 (タグが見つかりませんでした)")
                return False

    except Exception as e:
        print(f"  ❌ 処理エラー: {e}")
        return False

def load_ticker_map(csv_path):
    mapping = {}
    try:
        try:
            df = pd.read_csv(csv_path, encoding='utf-8', skiprows=1)
        except:
            df = pd.read_csv(csv_path, encoding='cp932', skiprows=1)
        for _, row in df.iterrows():
            s = str(row.get('証券コード', ''))
            e = str(row.get('ＥＤＩＮＥＴコード', ''))
            if len(s) >= 4 and e.startswith('E'):
                mapping[s[:4]+".T"] = e
    except: pass
    return mapping

if __name__ == "__main__":
    main()