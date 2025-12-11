import requests
import pandas as pd
import time
import datetime
import os
from sqlalchemy import create_engine

# =========================================================
# 🔑 APIキー設定 (必ず書き換えてください)
# =========================================================
API_KEY = "63715392921541a18b2cd6d1dbc05c15" 

# ターゲット銘柄
TARGET_TICKERS = ["7203.T", "6758.T", "9984.T"]

# 検索する期間 (何年前まで遡るか)
YEARS_BACK = 10

# CSVパス
CSV_PATH = "EdinetcodeDlInfo.csv"
# =========================================================

def main():
    if "ここに" in API_KEY:
        print("❌ エラー: APIキーを設定してください。")
        return

    print("🔍 銘柄コードの紐付けを確認中...")
    ticker_map = load_ticker_map(CSV_PATH)
    target_set = set()
    
    for t in TARGET_TICKERS:
        e_code = ticker_map.get(t)
        if e_code:
            print(f"  ✅ {t} -> {e_code}")
            target_set.add(e_code)
        else:
            print(f"  ❌ {t} のEDINETコードが見つかりません")

    if not target_set:
        return

    # --- 過去10年分の日付リスト作成 ---
    search_dates = []
    today = datetime.date.today()
    current_year = today.year
    
    print(f"\n🗓️ 過去 {YEARS_BACK} 年分の決算集中日を生成中...")

    # 2024年, 2023年, ... と遡る
    for year in range(current_year, current_year - YEARS_BACK, -1):
        # 決算発表が集中する月: 5月(本決算), 8月(1Q), 11月(2Q), 2月(3Q)
        # 特に集中する「上旬〜中旬 (1日〜15日)」を狙い撃ち
        for month in [2, 5, 8, 11]: 
            for day in range(1, 16): # 1日〜15日
                try:
                    d = datetime.date(year, month, day)
                    if d <= today: # 未来の日付は含めない
                        search_dates.append(d)
                except ValueError:
                    continue # 存在しない日付(2/30等)はスキップ
    
    # 日付を降順（新しい順）にソート
    search_dates.sort(reverse=True)
    
    print(f"  -> 合計 {len(search_dates)} 日分をスキャンします。")
    print("  -> (5月, 8月, 11月, 2月の 1日～15日 を重点調査)")

    # --- 検索実行 ---
    total_found = 0
    
    # APIレート制限対策 (10秒で10回まで等の制限があるため慎重に)
    
    for target_date in search_dates:
        date_str = target_date.strftime('%Y-%m-%d')
        weekday = target_date.strftime('%a')
        
        if target_date.weekday() >= 5: # 土日はスキップ
            continue

        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {'date': date_str, 'type': 2}
        headers = {'Ocp-Apim-Subscription-Key': API_KEY}

        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            
            if res.status_code == 200:
                data = res.json()
                docs = data.get('results', [])
                
                # ターゲットを探す
                hit_docs = []
                for doc in docs:
                    if doc.get('edinetCode') in target_set:
                        dtc = doc.get('docTypeCode', '')
                        # 120:有報, 130:訂正有報, 140:四半期
                        if dtc in ['120', '130', '140']:
                            hit_docs.append(doc)
                
                if hit_docs:
                    print(f"📅 {date_str}: {len(docs)}件中 -> 🎯 {len(hit_docs)}件 HIT!")
                    for doc in hit_docs:
                        print(f"   Running... {doc['filerName']} : {doc['docDescription']}")
                        # ここで本来はダウンロード処理 (今回はリストアップのみ)
                        total_found += 1
                else:
                    # ヒットしない日はログを省略して進捗だけ表示（うるさくなるため）
                    print(f".", end="", flush=True)
                    
            else:
                print(f"x", end="", flush=True)

            # アクセス負荷軽減
            time.sleep(0.5)

        except Exception as e:
            print(f"!", end="", flush=True)
            
    print(f"\n\n🏁 完了しました。合計 {total_found} 件の書類が見つかりました。")

def load_ticker_map(csv_path):
    mapping = {}
    try:
        # エンコーディング対応
        try:
            df = pd.read_csv(csv_path, encoding='utf-8', skiprows=1)
        except:
            df = pd.read_csv(csv_path, encoding='cp932', skiprows=1)
            
        for _, row in df.iterrows():
            s_code = str(row.get('証券コード', ''))
            e_code = str(row.get('ＥＤＩＮＥＴコード', ''))
            if len(s_code) >= 4 and e_code.startswith('E'):
                clean_ticker = s_code[:4] + ".T"
                mapping[clean_ticker] = e_code
    except:
        pass
    return mapping

if __name__ == "__main__":
    main()