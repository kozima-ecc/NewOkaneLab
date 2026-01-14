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
API_KEY = "ここにあなたのAPIキーを貼り付け" 
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
    
    # 逆引き辞書 (Eコード -> Ticker)
    edinet_to_ticker = {v: k for k, v in ticker_map.items() if k in TARGET_TICKERS}
    target_set = set(edinet_to_ticker.keys())

    if not target_set:
        print("❌ 対象銘柄が見つかりません。")
        return

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
                    # 120:有報, 140:四半期
                    if dtc in ['120', '140']:
                        ticker = edinet_to_ticker[e_code]
                        doc_id = doc['docID']
                        doc_desc = doc['docDescription']
                        filer_name = doc['filerName']
                        
                        print(f"\n📄 発見: {filer_name} ({doc_desc})")
                        
                        # データ取得 & DB保存 (自力解析モード)
                        success = download_and_save_simple(doc_id, ticker, engine)
                        if success:
                            processed_count += 1
            
            print(".", end="", flush=True)
            time.sleep(0.5)

        except Exception as e:
            print(f"!", end="", flush=True)

    print(f"\n\n✅ 全処理完了: {processed_count} 件のデータをDBに保存しました。")

# ---------------------------------------------------------
# XBRLダウンロード & 簡易解析 (Regex)
# ---------------------------------------------------------
def download_and_save_simple(doc_id, ticker, engine):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {'type': 1}
    headers = {'Ocp-Apim-Subscription-Key': API_KEY}
    
    try:
        res = requests.get(url, params=params, headers=headers, stream=True, timeout=30)
        if res.status_code != 200:
            print(f"  ❌ DL失敗: {res.status_code}")
            return False

        # ZIPを展開
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            # XBRLファイルを探す (PublicDocフォルダ内の .xbrl)
            xbrl_files = [f for f in z.namelist() if f.endswith('.xbrl') and 'PublicDoc' in f]
            if not xbrl_files:
                print("  ❌ XBRLファイルが見つかりません")
                return False
            
            # テキストとして読み込む
            with z.open(xbrl_files[0]) as f:
                # XBRLは通常UTF-8
                xbrl_text = f.read().decode('utf-8', errors='ignore')
            
            # --- 正規表現による数値抽出 ---
            # ライブラリを使わず、テキストパターンマッチングで抜く
            
            data_dict = {}
            
            # 探すタグ名リスト (IFRS / 日本基準 混合)
            target_tags = {
                'net_sales': ['NetSales', 'OperatingRevenue1', 'Revenue', 'OperatingRevenue'], 
                'operating_income': ['OperatingIncome', 'OperatingProfit'],
                'net_income': ['ProfitLossAttributableToOwnersOfParent', 'NetIncome', 'ProfitLoss'],
                'eps': ['BasicEarningsLossPerShare', 'EarningsPerShare']
            }
            
            for key, candidates in target_tags.items():
                for tag in candidates:
                    # パターン1: <タグ ... contextRef="...Current...">数値</タグ>
                    # (今年度の数値である "Current" または "Year" を含むコンテキストを優先)
                    pattern_prio = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*contextRef="[^"]*(Current|Year)[^"]*"[^>]*>([0-9\.\-]+)<')
                    match = pattern_prio.search(xbrl_text)
                    
                    if match:
                        try:
                            val = float(match.group(3))
                            data_dict[key] = val
                            break # 見つかったら次の項目へ
                        except: pass
                    
                    # パターン2: コンテキスト指定なしでとにかく数値を探す (フォールバック)
                    if key not in data_dict:
                        pattern_simple = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*>([0-9\.\-]+)<')
                        match_simple = pattern_simple.search(xbrl_text)
                        if match_simple:
                            try:
                                val = float(match_simple.group(2))
                                data_dict[key] = val
                                break
                            except: pass

            if not data_dict:
                print("  ⚠️ 数値タグが見つかりませんでした (処理スキップ)")
                return False

            # DB保存
            data_dict['ticker_code'] = ticker
            
            # 暫定値を入れる (NULL許容カラム前提)
            data_dict['fiscal_year'] = None 
            data_dict['quarter'] = None
            
            df = pd.DataFrame([data_dict])
            try:
                df.to_sql('fact_financials', engine, if_exists='append', index=False)
                
                # ログ表示 (売上だけ表示してみる)
                sales_disp = data_dict.get('net_sales', '-')
                print(f"  💾 DB保存成功: 売上={sales_disp}")
                return True
            except Exception as e:
                print(f"  ❌ DB保存エラー: {e}")
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