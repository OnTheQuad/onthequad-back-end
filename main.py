from oauth2client import client, crypt
from flask import Flask, request, send_file, session
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.sql import exists

Base = automap_base()
engine = create_engine("postgres://mfdtnsymomaahc:199wYivfssJqwI2C1pSAxlf8-R@ec2-54-225-194-162.compute-1.amazonaws.com:5432/d5qp2ahp0mpd3a")
Base.prepare(engine, reflect=True)
User = Base.classes.user
Session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))

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
	session = Session()
	if not session.query(exists().where(User.id == long(idinfo['sub']))).scalar():
		session.add(User(id=long(idinfo['sub']), name=idinfo['name'], email=idinfo['email']))
		session.commit()
	session.close()
	return idinfo['name']

@app.teardown_appcontext
def shutdown_session(exception=None):
    Session.remove()

if __name__ == '__main__':
	app.run(debug=True)