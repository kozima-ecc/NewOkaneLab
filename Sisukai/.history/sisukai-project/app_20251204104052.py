from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flasgger import Swagger
import pymysql
import urllib.parse
import json
import datetime
from sqlalchemy import text

# ★ここで別ファイルのロジックをインポート
import simulation_logic

# ===============================================
# 初期設定
# ===============================================
pymysql.install_as_MySQLdb()

app = Flask(__name__)
CORS(app)

app.config['SWAGGER'] = {
    'title': 'Trade Sim API',
    'uiversion': 3
}
swagger = Swagger(app)

# MySQL設定
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
# モデル定義 (DBテーブル定義)
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
# APIルート定義
# ===============================================

@app.route('/api/companies', methods=['GET'])
def get_companies():
    """ 企業リスト取得API """
    try:
        # ロジックファイル側の関数を呼び出し (engineを渡す)
        companies = simulation_logic.get_companies_list(db.engine)
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
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "JSONデータが必要です"}), 400
    
    # ★ロジックファイル側の関数を呼び出し (engineを渡す)
    result = simulation_logic.run_simulation_logic(data, db.engine)
    
    if "error" in result:
        return jsonify({"status": "error", "message": result["error"]}), 400
    
    return jsonify(result)

@app.route('/api/save_setting', methods=['POST'])
def save_setting():
    """
    シミュレーション結果保存API
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
        return jsonify({"status": "success", "message": "保存しました"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """ 履歴一覧取得API """
    try:
        histories = SimulationHistory.query.order_by(SimulationHistory.id.desc()).all()
        return jsonify([h.to_dict() for h in histories])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Backend is running!"})

if __name__ == '__main__':
    print("🚀 Flask API 起動中... (Separate Logic Mode)")
    app.run(host="0.0.0.0", port=80, debug=False)