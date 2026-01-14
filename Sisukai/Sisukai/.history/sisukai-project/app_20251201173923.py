from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger
import simulation_logic

app = Flask(__name__)
CORS(app)

# Swaggerの設定
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
        description: サーバー稼働状況
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
    summary: 投資条件に基づき、将来の資産推移と関連イベントを計算します
    description: |
        指定された銘柄、期間、投資額に基づいてシミュレーションを行います。
        レスポンスの `graph_data` は、フロントエンドでチャートを描画するために
        日付と資産額がペアになった時系列データとして返されます。
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            initial_investment:
              type: number
              description: 初期投資額 (円)
              example: 1000000
            monthly_investment:
              type: number
              description: 毎月の積立額 (円)
              example: 50000
            start_date:
              type: string
              format: date
              description: 開始日 (YYYY-MM-DD)
              example: "2015-01-01"
            end_date:
              type: string
              format: date
              description: 終了日 (YYYY-MM-DD)
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
              description: |
                  グラフ描画用の時系列データリスト。
                  日付(X軸)と、その日の資産評価額・元本(Y軸)が含まれます。
              items:
                type: object
                properties:
                  date:
                    type: string
                    description: 日付 (YYYY-MM-DD)
                    example: "2015-01-01"
                  total_assets:
                    type: number
                    description: その日の資産評価額合計 (円)
                    example: 1050000
                  invested_amount:
                    type: number
                    description: その日までの投資元本合計 (円)
                    example: 1000000
            events:
              type: array
              description: 期間中に発生した関連ニュース・イベントのリスト
              items:
                type: object
                properties:
                  date:
                    type: string
                    example: "2018-11-19"
                  ticker:
                    type: string
                    example: "7201.T"
                  title:
                    type: string
                    example: "カルロス・ゴーン会長逮捕"
                  description:
                    type: string
                    example: "金融商品取引法違反の疑いで..."
                  sentiment:
                    type: number
                    example: -0.9
            summary:
              type: object
              description: 最終結果のサマリー
              properties:
                final_assets:
                  type: number
                  description: 最終資産額
                total_invested:
                  type: number
                  description: 投資元本合計
                return_rate:
                  type: number
                  description: 損益率 (%)
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
    description: 現在の入力設定を保存します（現在はログ出力のみ）
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