from flask import Flask

# Flaskアプリケーションのインスタンスを作成
# production名は「Sisukai」と設定
app = Flask('Sisukai')

# トップページ（ルートURL）にアクセスがあったときの処理
@app.route('/')
def index():
    return '<h1>Hello, Sisukai!</h1>'

# デバッグモードでの実行
if __name__ == '__main__':
    app.run(debug=True)
