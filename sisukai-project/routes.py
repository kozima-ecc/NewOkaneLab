from flask import Blueprint, jsonify
from models import Glossary, Company  # db はここでは使わない

api = Blueprint('api', __name__)

@api.route('/glossary', methods=['GET'])
def get_glossary():
    items = Glossary.query.order_by(Glossary.TermName).all()
    return jsonify([{
        'TermID': g.TermID,
        'TermName': g.TermName,
        'Definition': g.Definition
    } for g in items])

@api.route('/companies', methods=['GET'])
def get_companies():
    items = Company.query.order_by(Company.CompanyName).all()
    return jsonify([{
        'CompanyID': c.CompanyID,
        'CompanyName': c.CompanyName,
        'Code': c.Code
    } for c in items])
