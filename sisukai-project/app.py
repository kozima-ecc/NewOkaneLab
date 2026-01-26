from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os

# =========================
# Flask 初期化
# =========================
app = Flask(__name__)
CORS(app)

# =========================
# SQLite データベース設定
# =========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "sisukai.db")
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# =========================
# モデル定義
# =========================
class Company(db.Model):
    __tablename__ = 'companies'
    ticker_code = db.Column(db.String(10), primary_key=True)
    company_name = db.Column(db.String(256), nullable=False)
    industry_name = db.Column(db.String(100))
    market = db.Column(db.String(50))

class Glossary(db.Model):
    __tablename__ = 'glossary'
    TermID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    TermName = db.Column(db.String(256), nullable=False)
    Category = db.Column(db.String(256), nullable=False)
    Definition = db.Column(db.String(256), nullable=False)
    Reading = db.Column(db.String(50), nullable=False)
    example = db.Column(db.Text, nullable=False)
    Details = db.Column(db.Text)

class Financials(db.Model):
    __tablename__ = 'fact_financials'
    ticker_code = db.Column(db.String(10), db.ForeignKey('companies.ticker_code'), primary_key=True)
    fiscal_year = db.Column(db.Integer, primary_key=True)
    quarter = db.Column(db.SmallInteger, primary_key=True)
    net_sales = db.Column(db.BigInteger)
    operating_income = db.Column(db.BigInteger)
    net_income = db.Column(db.BigInteger)
    eps = db.Column(db.Numeric(10, 2))
    # roe カラムが DB にない場合、追加しておく
    roe = db.Column(db.Float)

# =========================
# DB 初期化
# =========================
with app.app_context():
    db.create_all()
    # SQLite に roe カラムを追加（既にある場合はスキップ）
    try:
        db.engine.execute('ALTER TABLE fact_financials ADD COLUMN roe REAL')
    except Exception as e:
        print("roe カラムは既に存在する可能性があります:", e)

# =========================
# APIルート
# =========================
@app.route('/companies', methods=['GET'])
def get_companies():
    companies = Company.query.all()
    return jsonify([
        {
            'ticker_code': c.ticker_code,
            'company_name': c.company_name,
            'industry_name': c.industry_name,
            'market': c.market
        } for c in companies
    ])

@app.route('/glossary', methods=['GET'])
def get_glossary():
    items = Glossary.query.all()
    return jsonify([
        {
            'TermID': g.TermID,
            'TermName': g.TermName,
            'Category': g.Category,
            'Definition': g.Definition,
            'Reading': g.Reading,
            'example': g.example,
            'Details': g.Details
        } for g in items
    ])

# =========================
# 財務情報取得（ティッカーコード）
# =========================
@app.route('/financials/<ticker_code>', methods=['GET'])
def get_financials(ticker_code):
    financials = Financials.query.filter_by(ticker_code=ticker_code).all()
    if not financials:
        return jsonify({'message': f'{ticker_code} の財務情報は存在しません'}), 404
    return jsonify([
        {
            'ticker_code': f.ticker_code,
            'fiscal_year': f.fiscal_year,
            'quarter': f.quarter,
            'net_sales': f.net_sales,
            'operating_income': f.operating_income,
            'net_income': f.net_income,
            'eps': str(f.eps) if f.eps is not None else None,
            'roe': f.roe
        } for f in financials
    ])

# =========================
# 財務情報取得（会社名で検索したい場合）
# =========================
@app.route('/financials_by_name', methods=['GET'])
def get_financials_by_name():
    company_name = request.args.get('company_name')
    if not company_name:
        return jsonify({'message': 'company_name パラメータを指定してください'}), 400

    company = Company.query.filter(Company.company_name == company_name).first()
    if not company:
        return jsonify({'message': f'{company_name} に該当する会社は存在しません'}), 404

    financials = Financials.query.filter_by(ticker_code=company.ticker_code).all()
    return jsonify([
        {
            'ticker_code': f.ticker_code,
            'fiscal_year': f.fiscal_year,
            'quarter': f.quarter,
            'net_sales': f.net_sales,
            'operating_income': f.operating_income,
            'net_income': f.net_income,
            'eps': str(f.eps) if f.eps is not None else None,
            'roe': f.roe
        } for f in financials
    ])

# =========================
# アプリ起動
# =========================
if __name__ == '__main__':
    app.run(debug=True)
