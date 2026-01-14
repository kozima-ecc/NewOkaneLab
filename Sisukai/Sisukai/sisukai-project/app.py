from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flasgger import Swagger
import pymysql
import pandas as pd
from sqlalchemy import text
import urllib.parse
import json
import datetime

import simulation_logic

# ===============================================
# 初期設定
# ===============================================
pymysql.install_as_MySQLdb()

app = Flask(__name__)
CORS(app)

# Swagger設定 (API仕様書の定義)
app.config['SWAGGER'] = {
    'title': 'Trade Sim API',
    'uiversion': 3
}
swagger = Swagger(app)

# MySQL接続設定
DB_USER = 'trade_viewer'
DB_PASS = 'trade_pass391' 
DB_HOST = 'mattya3340.tplinkdns.com'
DB_NAME = 'trade_sim'
DB_PORT = 3306

encoded_pass = urllib.parse.quote_plus(DB_PASS)

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ===============================================
# 2. データベースモデル定義
# ===============================================
class Company(db.Model):
    __tablename__ = 'companies'
    ticker_code = db.Column(db.String(10), primary_key=True)
    company_name = db.Column(db.String(256))
    industry_name = db.Column(db.String(100))
    market = db.Column(db.String(50))

    def to_dict(self):
        return {
            'ticker_code': self.ticker_code,
            'company_name': self.company_name,
            'industry_name': self.industry_name,
            'market': self.market
        }

class Financials(db.Model):
    __tablename__ = 'fact_financials'
    ticker_code = db.Column(db.String(10), db.ForeignKey('companies.ticker_code'), primary_key=True)
    fiscal_year = db.Column(db.Integer, primary_key=True)
    quarter = db.Column(db.SmallInteger, primary_key=True)
    net_sales = db.Column(db.BigInteger)
    operating_income = db.Column(db.BigInteger)
    net_income = db.Column(db.BigInteger)
    eps = db.Column(db.Numeric(10, 2))
    roe = db.Column(db.Float)

class SimulationHistory(db.Model):
    __tablename__ = 'simulation_history'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    title = db.Column(db.String(255))
    initial_investment = db.Column(db.BigInteger)
    monthly_investment = db.Column(db.BigInteger)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    tickers = db.Column(db.JSON)
    final_assets = db.Column(db.BigInteger)
    return_rate = db.Column(db.Float)

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M'),
            "title": self.title,
            "final_assets": self.final_assets,
            "return_rate": self.return_rate,
            "tickers": self.tickers
        }

# ===============================================
# DB初期化
# ===============================================
with app.app_context():
    try:
        db.create_all()
        print("✅ DB接続・モデル初期化完了")
    except Exception as e:
        print(f"❌ DB初期化エラー: {e}")

# ===============================================
# APIルート実装
# ===============================================

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
    tags:
      - Data
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
        companies = Company.query.all()
        return jsonify([c.to_dict() for c in companies])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate():
    """
    シミュレーション実行API
    ---
    tags:
      - Simulation
    summary: 投資条件に基づき、将来の資産推移と関連イベントを計算します
    description: |
        指定された銘柄、期間、投資額に基づいてシミュレーションを行います。
        グラフ描画用のデータ(graph_data)と、期間中のイベント(events)を返します。
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            initial_investment:
              type: number
              example: 1000000
            monthly_investment:
              type: number
              example: 50000
            start_date:
              type: string
              format: date
              example: "2015-01-01"
            end_date:
              type: string
              format: date
              example: "2024-12-31"
            tickers:
              type: array
              items:
                type: string
              example: ["7203.T", "AAPL"]
    responses:
      200:
        description: シミュレーション結果
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "JSONデータが必要です"}), 400
    
    result = simulation_logic.run_simulation_logic(data, db.engine)
    
    if "error" in result:
        return jsonify({"status": "error", "message": result["error"]}), 400
    
    return jsonify(result)

@app.route('/api/save_setting', methods=['POST'])
def save_setting():
    """
    設定保存API (DB保存機能)
    ---
    tags:
      - Simulation
    description: シミュレーションの設定と結果をデータベースに保存します。
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            title:
              type: string
              example: "マイプランA"
            initial_investment:
              type: number
            monthly_investment:
              type: number
            start_date:
              type: string
            end_date:
              type: string
            tickers:
              type: array
            final_assets:
              type: number
            return_rate:
              type: number
    responses:
      200:
        description: 保存成功
    """
    data = request.get_json()
    try:
        history = SimulationHistory(
            title=data.get('title', '無題のシミュレーション'),
            initial_investment=data.get('initial_investment'),
            monthly_investment=data.get('monthly_investment'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            tickers=json.dumps(data.get('tickers', [])),
            final_assets=data.get('final_assets'),
            return_rate=data.get('return_rate')
        )
        db.session.add(history)
        db.session.commit()
        
        print(f"💾 Saved History: {data.get('title')}")
        return jsonify({"status": "success", "message": "History saved successfully"})
    except Exception as e:
        print(f"Save Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """
    履歴取得API
    ---
    tags:
      - Simulation
    description: 保存されたシミュレーション履歴のリストを返します。
    responses:
      200:
        description: 履歴リスト
    """
    try:
        histories = SimulationHistory.query.order_by(SimulationHistory.id.desc()).all()
        return jsonify([h.to_dict() for h in histories])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ===============================================
# 起動
# ===============================================
if __name__ == '__main__':
    print("🚀 Flask API 起動中...")
    print("➡ http://127.0.0.1:8080/apidocs で仕様書を確認できます")
    # 外部公開設定 (0.0.0.0)
    
    app.run(host="0.0.0.0", port=8080, debug=True)