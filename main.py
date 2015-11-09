from oauth2client import client, crypt
from functools import wraps
from flask import Flask, request, send_file, session, abort
from flask.json import jsonify
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.sql import exists
from mappings import Categories, User, Postings

engine = create_engine("postgres://mfdtnsymomaahc:199wYivfssJqwI2C1pSAxlf8-R@ec2-54-225-194-162.compute-1.amazonaws.com:5432/d5qp2ahp0mpd3a")
Session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))

CLIENT_ID = '441857043088-ujkkfjr5f66e1j4qq02iueink9d5fcj8.apps.googleusercontent.com'

app = Flask(__name__)

# Session handler
@app.teardown_appcontext
def shutdown_session(exception=None):
    Session.remove()

# Middleware:
# Authorization View (only used for login)
@app.route('/api/auth/', methods=['POST'], strict_slashes=False)
def auth():
	if authorizer(request.form.get('id_token')):
		return '', 200
	return '', 403

# TODO: Searching here

# Helpers
# The actual authorizer that does the work
def authorizer(token):
	if not token: return False
	try:
		idinfo = client.verify_id_token(token, CLIENT_ID);
		if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
			raise crypt.AppIdentityError("Wrong issuer.")
		if idinfo['hd'] != 'uconn.edu':
			raise crypt.AppIdentityError("Wrong hosted domain.")
	except crypt.AppIdentityError:
		return False
	session = Session()
	if not session.query(exists().where(User.id == long(idinfo['sub']))).scalar():
		session.add(User(id=long(idinfo['sub']), name=idinfo['name'], email=idinfo['email']))
		session.commit()
	session.close()
	return True

# Authorization Decorator (used when other Views are accessed)
def auth_req(f):
	@wraps(f)
	def wrapper(*args, **kwargs):
		if authorizer(request.headers.get('id_token', None)):
			return f(*args, **kwargs)
		abort(403)
	return wrapper

# Takes a SQLAlchemy mapping and converts it to representational dictionary
def to_dict(row):
	res = dict()
	for c in row.__table__.columns:
		res[c.name] = getattr(row, c.name)
	return res

#### API ####
# User API:
@app.route('/api/user/', methods=['GET'], strict_slashes=False)
@auth_req
def get_user():
	session = Session()
	id = request.args.get('id')
	email = request.args.get('email')
	name = request.args.get('name')

	# Query
	query = session.query(User)
	if id: query = query.filter(User.id == id)
	if email: query = query.filter(User.email == email)
	if name: query = query.filter(User.name == name)

	# Return the JSON
	return jsonify(data=[to_dict(r) for r in query.all()])

# Postings API:
@app.route('/api/postings/', methods=['GET'], strict_slashes=False)
@auth_req
def get_postings():
	session = Session()
	id = request.args.get('id')
	owner = request.args.get('owner')
	category = request.args.get('category')
	cost = request.args.get('cost')
	max_cost = request.args.get('max_cost')

	# Query
	query = session.query(Postings)
	if id: query = query.filter(Postings.id == id)
	if owner: query = query.filter(Postings.owner == owner)
	if category: query = query.filter(Postings.category == category)
	if cost: query = query.filter(Postings.cost == cost)
	if max_cost: query = query.filter(Postings.cost <= max_cost)

	# Return the JSON
	return jsonify(data=[to_dict(r) for r in query.all()])

@app.route('/api/postings/', methods=['POST'], strict_slashes=False)
@auth_req
def post_postings():
	session = Session()


# FOR DEBUGGING
@app.route('/login/', strict_slashes=False)
def login():
	return send_file('login.html')

if __name__ == '__main__':
	app.run(debug=True)
