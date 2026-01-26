import requests
import pandas as pd
import time
import datetime
import os
import sys
import io
import zipfile
from sqlalchemy import create_engine, text

# =========================================================
# 🔑 設定エリア
# =========================================================
API_KEY = "ここにあなたのAPIキーを貼り付け" 
TARGET_TICKERS = ["7203.T", "6758.T", "9984.T"]
DB_PATH = 'sqlite:///sisukai.db'
CSV_PATH = "EdinetcodeDlInfo.csv"
# =========================================================

# --- Arelleのエラー回避パッチ ---
import collections
try:
    collections.MutableMapping = collections.abc.MutableMapping
    collections.Iterable = collections.abc.Iterable
    collections.Mapping = collections.abc.Mapping
except AttributeError:
    pass

# XBRL解析には edinet-xbrl ライブラリを使うのが簡単ですが、
# ここではライブラリ依存を減らすため、あるいは arelle を使うならその設定が必要。
# 今回は「ダウンロードして保存」までを確実に行い、解析は簡易的に行います。
# もし `edinet-xbrl` が入っていればそれを使います。

try:
    from edinet_xbrl.edinet_xbrl_parser import EdinetXbrlParser
    USE_PARSER = True
except ImportError:
    USE_PARSER = False
    print("⚠️ edinet-xbrl ライブラリが見つかりません。pip install edinet-xbrl を推奨します。")

# ---------------------------------------------------------
# メイン処理
# ---------------------------------------------------------
def main():
    if "ここに" in API_KEY:
        print("❌ エラー: APIキーを設定してください。")
        return

    engine = create_engine(DB_PATH)
    parser = EdinetXbrlParser() if USE_PARSER else None

    print("🔍 マッピング読み込み中...")
    ticker_map = load_ticker_map(CSV_PATH)
    # 逆引き辞書 (Eコード -> Ticker)
    edinet_to_ticker = {v: k for k, v in ticker_map.items() if k in TARGET_TICKERS}
    target_set = set(edinet_to_ticker.keys())

    if not target_set:
        print("❌ 対象銘柄が見つかりません。")
        return

    # --- 過去10年分の日付リスト (前回のロジックと同じ) ---
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
                        
                        print(f"\n📥 DL中: {ticker} ({doc_desc})")
                        
                        # データ取得 & DB保存
                        success = download_and_save_to_db(doc_id, ticker, engine, parser)
                        if success:
                            processed_count += 1
            
            print(".", end="", flush=True)
            time.sleep(0.5)

        except Exception as e:
            print(f"!", end="", flush=True)

    print(f"\n\n✅ 全処理完了: {processed_count} 件のデータをDBに保存しました。")

# ---------------------------------------------------------
# XBRLダウンロード & 解析 & DB保存
# ---------------------------------------------------------
def download_and_save_to_db(doc_id, ticker, engine, parser):
    # 書類取得API (type=1: XBRLを含むZIP)
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {'type': 1}
    headers = {'Ocp-Apim-Subscription-Key': API_KEY}
    
    try:
        res = requests.get(url, params=params, headers=headers, stream=True, timeout=30)
        if res.status_code != 200:
            print(f"  -> DL失敗: {res.status_code}")
            return False

        # ZIPをメモリ上で開く
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            # xbrlファイルを探す (通常 .../PublicDoc/*.xbrl)
            xbrl_files = [f for f in z.namelist() if f.endswith('.xbrl') and 'PublicDoc' in f]
            if not xbrl_files:
                return False
            
            # 一時ファイルに保存して解析ライブラリに渡す
            temp_xbrl = f"temp_{doc_id}.xbrl"
            with open(temp_xbrl, 'wb') as f:
                f.write(z.read(xbrl_files[0]))
            
            # 解析
            data_dict = {}
            if parser:
                edinet_obj = parser.parse_file(temp_xbrl)
                
                # 欲しいタグ (IFRSと日本基準でタグ名が違うので両方探す)
                tags = {
                    'net_sales': ['NetSales', 'OperatingRevenue1', 'Revenue'], # 売上
                    'operating_income': ['OperatingIncome', 'OperatingProfit'], # 営業利益
                    'net_income': ['ProfitLossAttributableToOwnersOfParent', 'NetIncome'], # 純利益
                    'eps': ['BasicEarningsLossPerShare', 'EarningsPerShare'] # EPS
                }
                
                for key, tag_candidates in tags.items():
                    for tag in tag_candidates:
                        val = edinet_obj.get_data_by_tag(tag)
                        if val:
                            # コンテキスト（今年度/連結）の選別が必要だが
                            # ここでは簡易的に「見つかった最初の数値」を取得
                            # (実際はもっと複雑なロジックが必要)
                            try:
                                data_dict[key] = float(val.get_value())
                                break
                            except:
                                pass

            # 一時ファイル削除
            os.remove(temp_xbrl)
            
            # DB保存用データ作成
            if data_dict:
                # 日付等の推測 (簡易)
                # ※本来はXBRL内のコンテキスト日付を見るべき
                data_dict['ticker_code'] = ticker
                # 会計年度等は別途補完が必要だが、とりあえずNULLでもデータを入れる
                
                # SQLでINSERT
                # (pandas経由だと楽)
                df = pd.DataFrame([data_dict])
                df.to_sql('fact_financials', engine, if_exists='append', index=False)
                print(f"  -> DB保存成功: {data_dict}")
                return True
            else:
                print("  -> 数値抽出できず")
                return False

    except Exception as e:
        print(f"  -> エラー: {e}")
        return False

def load_ticker_map(csv_path):
    # (前回の関数と同じ)
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