import requests
import pandas as pd
import time
import datetime
from sqlalchemy import create_engine

# =========================================================
# 🔑 APIキー設定
# =========================================================
API_KEY = "63715392921541a18b2cd6d1dbc05c15"  # ★必ず書き換えてください★

# ターゲット銘柄 (CSVから自動でEコードに変換します)
TARGET_TICKERS = ["7203.T", "6758.T", "9984.T"]

# データベース設定
DB_PATH = 'sqlite:///sisukai.db'
CSV_PATH = "EdinetcodeDlInfo.csv"
# =========================================================

def main():
    if "ここに" in API_KEY:
        print("❌ エラー: APIキーを設定してください。")
        return

    # 1. マッピング確認
    print("🔍 銘柄コードの紐付けを確認中...")
    ticker_map = load_ticker_map(CSV_PATH)
    
    target_edinet_codes = []
    for t in TARGET_TICKERS:
        e_code = ticker_map.get(t)
        if e_code:
            print(f"  ✅ {t} -> {e_code}")
            target_edinet_codes.append(e_code)
        else:
            print(f"  ❌ {t} のEDINETコードがCSVから見つかりません！")
    
    if not target_edinet_codes:
        print("対象となる銘柄が見つからないため終了します。")
        return

    target_set = set(target_edinet_codes)

    # 2. 検索期間の設定 (ピンポイント爆撃)
    # トヨタなどの決算が出やすい「8月上旬(1Q)」と「11月上旬(2Q)」を全日チェック
    
    # 2025年の日付リストを作成
    search_dates = []
    
    # 8月1日～8月15日 (お盆前決算ラッシュ)
    for d in range(1, 16):
        search_dates.append(datetime.date(2025, 8, d))
        
    # 11月1日～11月15日 (秋の決算ラッシュ)
    for d in range(1, 16):
        search_dates.append(datetime.date(2025, 11, d))

    print(f"\n🗓️ 決算集中日 {len(search_dates)} 日分を徹底的に調査します...")

    # 3. 検索実行
    total_found = 0
    
    for target_date in search_dates:
        date_str = target_date.strftime('%Y-%m-%d')
        weekday = target_date.strftime('%a')
        
        # 土日はスキップ (EDINETは土日更新ほぼなし)
        if target_date.weekday() >= 5:
            print(f"  {date_str} ({weekday}): 休日スキップ")
            continue

        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {'date': date_str, 'type': 2}
        headers = {'Ocp-Apim-Subscription-Key': API_KEY}

        try:
            res = requests.get(url, params=params, headers=headers, timeout=15)
            
            if res.status_code == 200:
                data = res.json()
                docs = data.get('results', [])
                print(f"  📂 {date_str} ({weekday}): 書類 {len(docs)} 件 ", end="")
                
                # ターゲットを探す
                found_today = 0
                for doc in docs:
                    if doc.get('edinetCode') in target_set:
                        # 書類タイプチェック (120:有報, 130:訂正, 140:四半期)
                        dtc = doc.get('docTypeCode', '')
                        if dtc in ['120', '130', '140']:
                            print(f"\n    🎯 HIT! {doc['filerName']} : {doc['docDescription']}")
                            found_today += 1
                            total_found += 1
                            # ここにダウンロード処理を入れる
                
                if found_today == 0:
                    print("-> 該当なし")
                    
            else:
                print(f"  ⚠️ {date_str}: APIエラー {res.status_code}")

            # 連続アクセス制限を防ぐ
            time.sleep(0.5)

        except Exception as e:
            print(f"  ❌ {date_str}: 通信エラー {e}")

    print(f"\n🏁 調査完了。合計 {total_found} 件の決算書が見つかりました。")

def load_ticker_map(csv_path):
    mapping = {}
    try:
        try:
            df = pd.read_csv(csv_path, encoding='utf-8', skiprows=1)
        except:
            df = pd.read_csv(csv_path, encoding='cp932', skiprows=1)
            
        for _, row in df.iterrows():
            # 証券コードのクリーニング
            s_code = str(row.get('証券コード', ''))
            e_code = str(row.get('ＥＤＩＮＥＴコード', ''))
            
            if len(s_code) >= 4 and e_code.startswith('E'):
                clean_ticker = s_code[:4] + ".T"
                mapping[clean_ticker] = e_code
                
    except Exception as e:
        print(f"CSV読込エラー: {e}")
        
    return mapping

if __name__ == "__main__":
    main()