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
                        print(f"   Desc: {doc_desc}")
                        
                        success = download_and_save_brute_force(doc_id, ticker, doc_desc, engine)
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
# XBRLダウンロード & 総当たり解析 (最終兵器)
# ---------------------------------------------------------
def download_and_save_brute_force(doc_id, ticker, doc_desc, engine):
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

            # --- 戦略: 正規表現で数値を抜きまくる ---
            # \s* を入れて改行やスペースに対応
            
            def extract_max_value(tags_list):
                candidates = []
                for tag in tags_list:
                    # contextRef="Current..." や "Year..." を優先するが、なくても拾う
                    # 名前空間プレフィックス (ifrs-full: 等) を許容
                    # パターン: <(ns:)?TagName ... > 数値 <
                    
                    # 1. Context指定あり (優先)
                    p_strict = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*contextRef="[^"]*(Current|Year|Duration)[^"]*"[^>]*>\s*([0-9\.\-]+)\s*<')
                    matches = p_strict.findall(xbrl_text)
                    for m in matches:
                        try: candidates.append(float(m[2]))
                        except: pass

                    # 2. 指定なし (フォールバック)
                    p_loose = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*>\s*([0-9\.\-]+)\s*<')
                    matches_loose = p_loose.findall(xbrl_text)
                    for m in matches_loose:
                        try: candidates.append(float(m[1]))
                        except: pass
                
                # 候補の中から最大値を返す (売上などは最大値が正解であることが多い)
                if candidates:
                    return max(candidates)
                return None

            # 1. 売上高 (最大値戦略)
            sales_tags = [
                'NetSales', 'OperatingRevenue1', 'Revenue', 
                'SalesRevenue', 'Revenues', 'OperatingRevenue',
                'RevenueFromContractsWithCustomers', 'RevenueIFRS'
            ]
            sales_val = extract_max_value(sales_tags)
            if sales_val: data_dict['net_sales'] = sales_val

            # 2. 営業利益 (Operating...)
            # 利益系はマイナスもあり得るので最大値戦略は危険だが、
            # トヨタ等のPL構造上、営業利益タグで引っかかる数値群の中では一番絶対値が大きいものを...
            # いや、ここは素直にタグ一致を信じる
            op_tags = ['OperatingIncome', 'OperatingProfit', 'OperatingLoss']
            data_dict['operating_income'] = extract_max_value(op_tags)

            # 3. 純利益
            net_tags = ['ProfitLossAttributableToOwnersOfParent', 'NetIncome', 'ProfitLoss']
            data_dict['net_income'] = extract_max_value(net_tags)

            # 4. EPS
            eps_tags = ['BasicEarningsLossPerShare', 'EarningsPerShare', 'BasicEarningsPerShare']
            data_dict['eps'] = extract_max_value(eps_tags) # EPSも通常は正の最大値を採用でOK

            # DB保存
            if 'net_sales' in data_dict:
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