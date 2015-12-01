from os import environ
from oauth2client import client, crypt
from functools import wraps
from flask import Flask, request, send_file, abort
from flask import session, g
from flask.json import jsonify
from flask.ext.cors import CORS
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.session import Session
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.sql import exists
from mappings import Categories, User, Postings

CLIENT_ID = environ['WEB_CLIENT_ID']

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Session configuration
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_SQLALCHEMY'] = db
Session(app)

#### Middleware ####
# Authorization View (only used for login)
@app.route('/api/auth/', methods=['POST'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','))
def auth():
	if authorizer(request.form.get('id_token')):
		return '', 200
	return '', 403

# Logout View
@app.route('/api/logout/', strict_slashes=False)
def logout():
	# Delete the session from the database
	session.clear()
	session.modified = True
	return '', 200

# TODO: Searching here

#### Helpers ####
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

	# Add id_token as a server side session cookie
	session['id_token'] = token

	# Set some globals that might be useful for this context
	g.user = {}
	g.user['id'] = long(idinfo['sub'])

	# Database
	if not db.session.query(exists().where(User.id == long(idinfo['sub']))).scalar():
		db.session.add(User(id=long(idinfo['sub']), name=idinfo['name'], email=idinfo['email']))
		db.session.commit()
	return True

# Authorization Decorator (used when other Views are accessed)
def auth_req(f):
	@wraps(f)
	def wrapper(*args, **kwargs):
		if authorizer(session.get('id_token', None)):
			return f(*args, **kwargs)
		return '', 403
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
	id = request.args.get('id')
	email = request.args.get('email')
	name = request.args.get('name')

	# Query
	query = db.session.query(User)
	if id: query = query.filter(User.id == id)
	if email: query = query.filter(User.email == email)
	if name: query = query.filter(User.name == name)

	# Return the JSON
	return jsonify(data=[to_dict(r) for r in query.all()])

# Postings API:
@app.route('/api/postings/', methods=['GET'], strict_slashes=False)
@auth_req
def get_postings():
	id = request.args.get('id')
	owner = request.args.get('owner')
	category = request.args.get('category')
	cost = request.args.get('cost')
	max_cost = request.args.get('max_cost')

	# Query
	query = db.session.query(Postings)
	if id: query = query.filter(Postings.id == id)
	if owner: query = query.filter(Postings.owner == owner)
	if category: query = query.filter(Postings.category == category)
	if cost: query = query.filter(Postings.cost == cost)
	if max_cost: query = query.filter(Postings.cost <= max_cost)

	# Return the JSON
	return jsonify(data=[to_dict(r) for r in query.all()]), 200, {'Access-Control-Allow-Origin': '*'}

@app.route('/api/postings/', methods=['POST'], strict_slashes=False)
@auth_req
def post_postings():
	description = request.form.get('description', None)
	category = request.form.get('category', None)
	cost = request.form.get('cost', None)
	title = request.form.get('title', None)

	# Some sanity checking
	if not all([category, cost, title]):
		return '', 400

	# Else continue
	post = Postings(owner=g.user['id'], description=description, cost=cost,
		category=category, title=title)
	
	# Add entry to database and commit
	# Also prevent duplicate entries due to double clicks
	q = db.session.query(Postings)
	if not db.session.query(q.exists().where(Postings == post)).scalar():
		db.session.add(post)
		db.session.commit()

	return '',  200

# FOR DEBUGGING
@app.route('/login/', strict_slashes=False)
def login():
	return send_file('login.html')

if __name__ == '__main__':
	app.run(debug=True)
