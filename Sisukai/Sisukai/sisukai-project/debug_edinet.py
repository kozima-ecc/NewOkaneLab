import requests
import pandas as pd
import io
import zipfile

def diagnose_edinet():
    print("=== 1. EDINETコードリストの取得テスト ===")
    # 金融庁が公開している「EDINETコードリスト」のURL
    url = "https://disclosure.edinet-fsa.go.jp/E01EW/BL/PBL/stsp0225/00/download?path=1"
    
    try:
        print(f"ダウンロード中: {url}")
        res = requests.get(url, timeout=30)
        
        if res.status_code != 200:
            print(f"❌ 失敗: ステータスコード {res.status_code}")
            return

        print("✅ ダウンロード成功。ZIP解凍と読み込みを開始します...")
        
        # ZIPをメモリ上で解凍してCSVを読み込む
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            # ZIPの中にあるファイル名を探す
            csv_filename = [f for f in z.namelist() if f.endswith('.csv')][0]
            print(f"CSVファイル発見: {csv_filename}")
            
            with z.open(csv_filename) as f:
                # cp932 (Shift_JIS) で読み込むのがコツ
                df = pd.read_csv(f, encoding='cp932', skiprows=1)
                
        print(f"✅ リスト読み込み成功: 全 {len(df)} 件")
        
        # 必要な列があるか確認
        # 「証券コード」と「ＥＤＩＮＥＴコード」という列名が重要
        print(f"列名チェック: {df.columns[:5]}")

    except Exception as e:
        print(f"❌ エラー発生: {e}")
        return

    print("\n=== 2. 銘柄コードのマッピングテスト ===")
    target_tickers = ["7203", "6758", "9984"] # トヨタ, ソニー, SBG
    
    for ticker in target_tickers:
        # 証券コードは4桁の数字＋0 (例: 72030) になっていることが多いので調整
        # ※データフレームの仕様に合わせて検索
        
        # 証券コード列を文字列に変換して検索
        search_code = str(ticker) + "0"
        
        # 検索
        # 列名は実際のCSVに合わせて調整が必要だが、通常は「証券コード」
        found = df[df['証券コード'].astype(str) == search_code]
        
        if not found.empty:
            edinet_code = found.iloc[0]['ＥＤＩＮＥＴコード']
            name = found.iloc[0]['提出者名']
            print(f"✅ 成功: {ticker} -> {edinet_code} ({name})")
        else:
            print(f"❌ 失敗: {ticker} に対応するEDINETコードが見つかりません。")
            # デバッグ用に一部を表示
            print(f"  (参考) 証券コード列のサンプル: {df['証券コード'].head().tolist()}")

if __name__ == "__main__":
    diagnose_edinet()