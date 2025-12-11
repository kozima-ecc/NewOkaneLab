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
                        doc_desc = doc['docDescription'] # 例: 四半期報告書－第100期第3四半期(2023/10/01－...)
                        filer_name = doc['filerName']
                        
                        print(f"\n📄 発見: {filer_name}")
                        print(f"   Desc: {doc_desc}")
                        
                        # データ取得 & DB保存
                        success = download_and_save_enhanced(doc_id, ticker, doc_desc, engine)
                        if success:
                            processed_count += 1
            
            print(".", end="", flush=True)
            time.sleep(0.5)

        except Exception as e:
            print(f"!", end="", flush=True)

    print(f"\n\n✅ 全処理完了: {processed_count} 件のデータをDBに保存しました。")

# ---------------------------------------------------------
# 年・四半期の抽出ロジック
# ---------------------------------------------------------
def parse_fiscal_info(doc_desc):
    """
    書類のタイトルから会計年度と四半期を推測する
    例: "四半期報告書－第120期第3四半期(2023/10/01－2023/12/31)"
    """
    fiscal_year = None
    quarter = None
    
    try:
        # 1. 四半期の抽出
        if "第1四半期" in doc_desc: quarter = 1
        elif "第2四半期" in doc_desc: quarter = 2
        elif "第3四半期" in doc_desc: quarter = 3
        elif "第4四半期" in doc_desc: quarter = 4
        elif "有価証券報告書" in doc_desc: quarter = 4 # 通期
        
        # 2. 年度の抽出 (期間の後ろの日付を使う)
        # パターン: (YYYY/MM/DD－YYYY/MM/DD) または (平成YY年...－令和YY年...)
        # 西暦の日付抽出 (20xx/xx/xx)
        date_matches = re.findall(r'(20\d{2})/(\d{1,2})/\d{1,2}', doc_desc)
        
        if date_matches:
            # 期間の「終了日」を使うのが確実 (リストの最後)
            end_year, end_month = int(date_matches[-1][0]), int(date_matches[-1][1])
            
            # 日本の会計年度ルール (3月決算基準)
            # 4月〜12月終了なら、その年が会計年度
            # 1月〜3月終了なら、前の年が会計年度
            if end_month >= 4:
                fiscal_year = end_year
            else:
                fiscal_year = end_year - 1
        else:
            # 日付がない場合、和暦等の可能性があるが今回は簡易的にスキップ
            # 現在の日付から推測も危険なのでNone
            pass

    except:
        pass
        
    return fiscal_year, quarter

# ---------------------------------------------------------
# XBRLダウンロード & 解析 (強化版)
# ---------------------------------------------------------
def download_and_save_enhanced(doc_id, ticker, doc_desc, engine):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {'type': 1}
    headers = {'Ocp-Apim-Subscription-Key': API_KEY}
    
    try:
        res = requests.get(url, params=params, headers=headers, stream=True, timeout=30)
        if res.status_code != 200:
            print(f"  ❌ DL失敗: {res.status_code}")
            return False

        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xbrl_files = [f for f in z.namelist() if f.endswith('.xbrl') and 'PublicDoc' in f]
            if not xbrl_files:
                return False
            
            with z.open(xbrl_files[0]) as f:
                xbrl_text = f.read().decode('utf-8', errors='ignore')
            
            data_dict = {}
            
            # --- 年・四半期の解析 ---
            fy, q = parse_fiscal_info(doc_desc)
            data_dict['fiscal_year'] = fy
            data_dict['quarter'] = q
            
            # --- 数値抽出 (トヨタ/IFRS対応・強化版) ---
            
            # 探すタグのリスト (優先順位順)
            # トヨタ対策: 'Revenue' が単独で使われることが多い
            target_tags = {
                'net_sales': [
                    'NetSales', 'OperatingRevenue1', 'Revenue', 
                    'SalesRevenue', 'Revenues', 'OperatingRevenue'
                ], 
                'operating_income': [
                    'OperatingIncome', 'OperatingProfit', 'OperatingLoss'
                ],
                'net_income': [
                    'ProfitLossAttributableToOwnersOfParent', 'NetIncome', 'ProfitLoss',
                    'ProfitLossAttributableToOwnersOfParentSummary'
                ],
                'eps': [
                    'BasicEarningsLossPerShare', 'EarningsPerShare', 'BasicEarningsPerShare'
                ]
            }
            
            # コンテキスト(contextRef)の優先順位キーワード
            # 1. CurrentYearDuration: 当該期間 (一番欲しい)
            # 2. CurrentYearInstant: 当該時点 (BS科目用)
            # 3. Current: 緩い一致
            # 4. 指定なし: とにかく数値 (フォールバック)
            
            for key, candidates in target_tags.items():
                found_val = None
                
                for tag in candidates:
                    # 正規表現のパターンを3段階で試す
                    
                    # パターンA: 厳格なコンテキスト (Duration/Instant)
                    p_strict = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*contextRef="[^"]*(CurrentYear|CurrentQuarter)[^"]*"[^>]*>([0-9\.\-]+)<')
                    m = p_strict.search(xbrl_text)
                    if m: 
                        found_val = float(m.group(3))
                        break
                    
                    # パターンB: 緩いコンテキスト (Current)
                    p_loose = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*contextRef="[^"]*Current[^"]*"[^>]*>([0-9\.\-]+)<')
                    m = p_loose.search(xbrl_text)
                    if m:
                        found_val = float(m.group(2))
                        break

                    # パターンC: トヨタ/IFRS特有 (コンテキストが日付指定の場合など)
                    # タグ名が一致して、値が数値であるものをとりあえず拾う (最後の手段)
                    # ただし、数値が小さすぎる(1以下)や "Prior" (前年) を避ける工夫が必要だが、
                    # 今回は「取れないよりはマシ」として拾う
                    p_force = re.compile(r'<([a-zA-Z0-9_]+:)?' + tag + r'[^>]*contextRef="[^"]*"[^>]*>([0-9\.\-]+)<')
                    # contextRefの中身を問わない（ただし空ではない）
                    m = p_force.search(xbrl_text)
                    if m:
                        val = float(m.group(2))
                        # 明らかにおかしい値（ゼロなど）以外を採用
                        if val != 0:
                            found_val = val
                            break

                if found_val is not None:
                    data_dict[key] = found_val

            # DB保存
            data_dict['ticker_code'] = ticker
            
            # 売上が取れていれば成功とみなす
            if 'net_sales' in data_dict:
                df = pd.DataFrame([data_dict])
                try:
                    df.to_sql('fact_financials', engine, if_exists='append', index=False)
                    
                    # ログ整形
                    sales_str = f"{data_dict['net_sales']:,.0f}" if data_dict.get('net_sales') else "-"
                    fy_str = f"{fy} Q{q}" if fy else "FY? Q?"
                    print(f"  💾 保存成功 [{fy_str}]: 売上={sales_str}")
                    return True
                except Exception as e:
                    print(f"  ❌ DB保存エラー: {e}")
                    return False
            else:
                print("  ⚠️ 数値抽出失敗 (タグ不一致)")
                # デバッグ用: どんなタグがあるか少し覗く? (今回は省略)
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