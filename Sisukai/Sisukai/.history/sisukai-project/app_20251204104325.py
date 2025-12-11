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

# ★重要: 別ファイルのロジックを読み込む
import simulation_logic

# ===============================================
# PyMySQL を MySQLdb として認識させる
# ===============================================
pymysql.install_as_MySQLdb()

# ===============================================
# Flask 初期化
# ===============================================
app = Flask(__name__)
CORS(app)

# Swagger設定
app.config['SWAGGER'] = {
    'title': 'Trade Sim API',
    'uiversion': 3
}
swagger = Swagger(app)

# ===============================================
# MySQL 接続設定
# ===============================================
DB_USER = 'root'
DB_PASS = 'root'
DB_HOST = 'localhost'
DB_NAME = 'trade_sim'
DB_PORT = 3306

encoded_pass = urllib.parse.quote_plus(DB_PASS)

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ===============================================
# モデル定義
# ===============================================
class Company(db.Model):
    __tablename__ = 'companies'
    ticker_code = db.Column(db.String(10), primary_key=True)
    company_name = db.Column(db.String(256), nullable=False)
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

# ★追加: 履歴保存用のモデル
class SimulationHistory(db.Model):
    __tablename__ = 'simulation_history'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    title = db.Column(db.String(255))
    initial_investment = db.Column(db.BigInteger)
    monthly_investment = db.Column(db.BigInteger)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    tickers = db.Column(db.JSON) # JSON型
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
# DB 初期化
# ===============================================
with app.app_context():
    try:
        db.create_all()
        print("✅ DB 初期化完了")
    except Exception as e:
        print("❌ DB 初期化エラー:", e)

# ===============================================
# API ルート
# ===============================================

@app.route('/api/companies', methods=['GET'])
def get_companies():
    """ 企業リスト取得 """
    # Companyモデルから全件取得して辞書化
    companies = Company.query.all()
    return jsonify([c.to_dict() for c in companies])

@app.route('/api/simulate', methods=['POST'])
def simulate():
    """
    シミュレーション実行
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
              example: 1000000
            monthly_investment:
              type: number
              example: 50000
            start_date:
              type: string
              example: "2015-01-01"
            end_date:
              type: string
              example: "2024-12-31"
            tickers:
              type: array
              items:
                type: string
              example: ["7203.T", "AAPL"]
    """
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "JSON必須"}), 400
    
    # ★別ファイルのロジック関数を呼び出す (db.engineを渡す)
    result = simulation_logic.run_simulation_logic(data, db.engine)
    
    if "error" in result:
        return jsonify({"status": "error", "message": result["error"]}), 400
    
    return jsonify(result)

@app.route('/api/save_setting', methods=['POST'])
def save_setting():
    """
    設定保存
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          description: 保存データ
    """
    data = request.json
    try:
        # DBへ保存
        history = SimulationHistory(
            title=data.get('title', '無題のシミュレーション'),
            initial_investment=data.get('initial_investment'),
            monthly_investment=data.get('monthly_investment'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            tickers=json.dumps(data.get('tickers', [])), # JSON文字列化
            final_assets=data.get('final_assets'),
            return_rate=data.get('return_rate')
        )
        db.session.add(history)
        db.session.commit()
        print(f"💾 Saved: {data.get('title')}")
        return jsonify({"status": "success", "message": "History saved."})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """ 履歴取得 """
    try:
        histories = SimulationHistory.query.order_by(SimulationHistory.id.desc()).all()
        return jsonify([h.to_dict() for h in histories])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Backend is running!"})

# ===============================================
# 起動
# ===============================================
if __name__ == '__main__':
    print("🚀 Flask API 起動中...")
    # 外部公開せずローカルのみ許可
    app.run(host="127.0.0.1", port=5000, debug=True)