from oauth2client import client, crypt
from flask import Flask, request, send_file, session
import pprint

CLIENT_ID = '441857043088-ujkkfjr5f66e1j4qq02iueink9d5fcj8.apps.googleusercontent.com'

app = Flask(__name__)

@app.route('/login', methods=['GET'])
def login():
	return send_file('login.html')

@app.route('/auth', methods=['POST'])
def auth():
	token = request.form.get('idtoken')
	try:
		idinfo = client.verify_id_token(token, CLIENT_ID);
		if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
			raise crypt.AppIdentityError("Wrong issuer.")
		if idinfo['hd'] != 'uconn.edu':
			raise crypt.AppIdentityError("Wrong hosted domain.")
	except crypt.AppIdentityError:
		return 'invalid', 403
	pprint.pprint(idinfo)
	return idinfo['name']

if __name__ == '__main__':
	app.run(debug=True)