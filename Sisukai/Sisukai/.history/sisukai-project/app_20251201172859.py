from flask import Flask, request, jsonify
from flask_cors import CORS
import simulation_logic

app = Flask(__name__)
# フロントエンド(localhost:3000など)からのアクセスを許可
CORS(app)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Backend is running!"})

# 1. 企業リスト取得API
@app.route('/api/companies', methods=['GET'])
def get_companies():
    try:
        companies = simulation_logic.get_companies_list()
        return jsonify(companies)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. シミュレーション実行API
@app.route('/api/simulate', methods=['POST'])
def simulate():
    try:
        # フロントからのJSONデータを受け取る
        # {
        #   "initial_investment": 1000000,
        #   "monthly_investment": 50000,
        #   "tickers": ["7203.T", "AAPL"],
        #   "start_date": "2015-01-01",
        #   "end_date": "2024-12-31"
        # }
        data = request.json
        result = simulation_logic.run_simulation_logic(data)
        return jsonify(result)
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

# 3. 設定保存API (簡易実装: ログに出すだけ。必要ならDBに保存するテーブルを作る)
@app.route('/api/save_setting', methods=['POST'])
def save_setting():
    data = request.json
    # ここで本来は `user_settings` テーブルなどにINSERTする
    print(f"💾 User Settings Saved: {data}")
    return jsonify({"message": "Settings saved successfully"})

if __name__ == '__main__':
    # デバッグモードで起動 (ポート5000)
    app.run(debug=True, port=5000)