from oauth2client import client, crypt
from flask import Flask, request, send_file, session

app = Flask(__name__)

@app.route('/login', methods=['GET'])
def login():
	return send_file('login.html')

@app.route('/login', methods=['POST'])
def login_post():
	token = request.form.get('idtoken')
	idinfo = client.verify_id_token(token, os.environ['CLIENT_ID']);
	print idinfo

if __name__ == '__main__':
	app.run(debug=True)