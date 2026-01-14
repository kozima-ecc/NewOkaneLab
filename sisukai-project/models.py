from app import db  # ここでは db を再作成しない

class Glossary(db.Model):
    __tablename__ = "Glossary"
    TermID = db.Column(db.Integer, primary_key=True)
    TermName = db.Column(db.String, nullable=False)
    Definition = db.Column(db.String, nullable=False)

class Company(db.Model):
    __tablename__ = "Company"
    CompanyID = db.Column(db.Integer, primary_key=True)
    CompanyName = db.Column(db.String, nullable=False)
    Code = db.Column(db.String)
