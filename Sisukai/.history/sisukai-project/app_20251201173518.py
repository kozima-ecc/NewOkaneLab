from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger  # 追加
import simulation_logic

app = Flask(__name__)
CORS(app)

# Swaggerの設定 (日本語化などはできませんが、UIは見やすいです)
app.config['SWAGGER'] = {
    'title': 'Trade Sim API',
    'uiversion': 3
}
swagger = Swagger(app)

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    ヘルスチェック用API
    ---
    responses:
      200:
        description: サーバーが正常に稼働している場合に返されます
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
            message:
              type: string
              example: Backend is running!
    """
    return jsonify({"status": "ok", "message": "Backend is running!"})

@app.route('/api/companies', methods=['GET'])
def get_companies():
    """
    企業リスト取得API
    ---
    description: データベースに登録されている全企業のリストを返します
    responses:
      200:
        description: 成功
        schema:
          type: array
          items:
            type: object
            properties:
              ticker_code:
                type: string
                example: 7203.T
              company_name:
                type: string
                example: トヨタ自動車
    """
    try:
        companies = simulation_logic.get_companies_list()
        return jsonify(companies)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    """
    シミュレーション実行API
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            initial_investment:
              type: number
              description: 初期投資額
              example: 1000000
            monthly_investment:
              type: number
              description: 毎月の積立額
              example: 50000
            start_date:
              type: string
              format: date
              description: 開始日
              example: "2015-01-01"
            end_date:
              type: string
              format: date
              description: 終了日
              example: "2024-12-31"
            tickers:
              type: array
              description: 投資する銘柄コードのリスト
              items:
                type: string
              example: ["7203.T", "AAPL"]
    responses:
      200:
        description: シミュレーション結果
        schema:
          type: object
          properties:
            graph_data:
              type: array
              items:
                type: object
                properties:
                  date:
                    type: string
                  total_assets:
                    type: number
            events:
              type: array
              items:
                type: object
                properties:
                  date:
                    type: string
                  title:
                    type: string
                  description:
                    type: string
            summary:
              type: object
    """
    try:
        data = request.json
        result = simulation_logic.run_simulation_logic(data)
        return jsonify(result)
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/save_setting', methods=['POST'])
def save_setting():
    """
    設定保存API
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          description: 保存する任意のJSONデータ
    responses:
      200:
        description: 保存成功
    """
    data = request.json
    print(f"💾 User Settings Saved: {data}")
    return jsonify({"message": "Settings saved successfully"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)