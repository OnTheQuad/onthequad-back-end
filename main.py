from os import environ
from oauth2client import client, crypt
from functools import wraps
from flask import Flask, request, send_file, escape
from flask import session, g
from flask.json import jsonify
from flask.ext.cors import cross_origin, CORS
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.session import Session
from sqlalchemy.sql import exists
from sqlalchemy.dialects.postgresql import array
from sqlalchemy import func
from models import db, Categories, User, Postings
from sphinxsearch import SphinxClient
import logging

CLIENT_ID = environ['WEB_CLIENT_ID']
SEARCH_HOST = environ['SEARCH_HOST']
SEARCH_PORT = int(environ['SEARCH_PORT'])

app = Flask(__name__)

app.config['DEBUG'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session configuration
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_SQLALCHEMY'] = db

db.init_app(app)

with app.app_context():
    Session(app)

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
        logging.getLogger('Main').info('Unauthorized access')
        return '', 403
    return wrapper

# Takes a SQLAlchemy mapping and converts it to representational dictionary
def to_dict(row):
    res = dict()
    for c in row.__table__.columns:
        res[c.name] = getattr(row, c.name)
    return res

# Takes a query and a sorting option, returns the query sorted by that option
def sort_query(q, sort):
    s_dict = {
        'newest':       Postings.timestamp.desc(),
        'oldest':       Postings.timestamp.asc(),
        'highest_cost': Postings.cost.desc(),
        'lowest_cost':  Postings.cost.asc(),
        }
    return q.order_by(s_dict.get(sort, Postings.timestamp.asc()))

#### Middleware ####
# Authorization View (only used for login)
@app.route('/api/auth/', methods=['POST'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
def auth():
    token = request.form.get('id_token')
    if authorizer(token):
        # Add id_token as a server side session cookie
        session['id_token'] = token
        return '', 200
    return '', 403

# Logout View
@app.route('/api/logout/', strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
def logout():
    # Delete the session from the database
    session.clear()
    session.modified = True
    return '', 200

# Searching View
@app.route('/api/search/', strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def search():
    keywords = request.args.get('keywords')
    client = SphinxClient()
    client.SetServer(SEARCH_HOST, SEARCH_PORT)
    q = client.Query(keywords)
    if not q:
        return '', 200
    ids = []
    for res in q['matches']:
        ids.append(res['id'])
    # First construct the subquery
    s_ids = db.session.query(func.unnest(array(ids)).label('id')).subquery('s_ids')
    query = Postings.query.join(s_ids, Postings.id == s_ids.c.id)

    per_page = request.args.get('per_page', default=20)
    try:
        per_page = int(per_page)
    except ValueError:
        per_page = 20
    page = request.args.get('page', default=1)
    try:
        page = int(page)
    except ValueError:
        page = 1

    sort = request.args.get('sort', default='relevance')
    if sort != 'relevance':
        query = sort_query(query, sort)

    page = query.paginate(page, per_page, error_out=False)

    # Return the JSON
    return jsonify(data=[to_dict(r) for r in page.items], num_pages=page.pages), 200

#### API ####
# User API:
@app.route('/api/user/', methods=['GET'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def get_user():
    id = request.args.get('id')
    email = request.args.get('email')
    name = request.args.get('name')

    # Query
    query = User.query
    if id: query = query.filter(User.id == id)
    if email: query = query.filter(User.email == email)
    if name: query = query.filter(User.name == name)

    # Return the JSON
    return jsonify(data=[to_dict(r) for r in query.all()])

# Postings API:
@app.route('/api/postings/', methods=['GET'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True, allow_headers=['*'])
@auth_req
def get_postings():
    try:
        id = request.args.get('id')
        if id: id = int(escape(id))
        owner = request.args.get('owner')
        if owner: owner = int(escape(owner))
        category = request.args.get('category')
        if category: category = int(escape(category))
        cost = request.args.get('cost')
        if cost: cost = float(escape(cost))
        max_cost = request.args.get('max_cost')
        if max_cost: max_cost = float(escape(max_cost))
    except ValueError:
        return '', 400

    per_page = request.args.get('per_page', default=20)
    try:
        per_page = int(per_page)
    except ValueError:
        per_page = 20
    page = request.args.get('page', default=1)
    try:
        page = int(page)
    except ValueError:
        page = 1


    # Query
    query = Postings.query
    if id: query = query.filter(Postings.id == id)
    if owner: query = query.filter(Postings.owner == owner)
    if category: query = query.filter(Postings.category == category)
    if cost: query = query.filter(Postings.cost == cost)
    if max_cost: query = query.filter(Postings.cost <= max_cost)

    # Sorting
    sort = request.args.get('sort', default='newest')
    query = sort_query(query, sort)

    page = query.paginate(page, per_page, error_out=False)

    # Return the JSON
    return jsonify(data=[to_dict(r) for r in page.items], num_pages=page.pages), 200

@app.route('/api/postings/', methods=['POST'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def post_postings():
    description = request.form.get('description')
    if description: description = escape(description)
    category = request.form.get('category')
    if category: category = escape(category)
    cost = request.form.get('cost')
    if cost: cost = escape(cost)
    title = request.form.get('title')
    if title: title = escape(title)
    try:
        category = int(category)
        if not db.session.query(exists().where(Categories.id == category)):
            return '', 400
    except ValueError:
        return '', 400
    # If we don't have a numeric cost, make it free
    try:
        cost = float(cost)
    except ValueError:
        cost = 0.0

    # Some sanity checking
    if not all([category, cost, title]):
        return '', 400

    # Else continue
    post = Postings(owner=g.user['id'], description=description, cost=cost,
        category=category, title=title)
    
    # Add entry to database and commit
    # Also prevent duplicate entries due to double clicks
    if not db.session.query(exists().where((Postings.owner==g.user['id']) &
        (Postings.description==description) & (Postings.category==category) &
        (Postings.title==title))).scalar():
        db.session.add(post)
        db.session.commit()

    return '',  200

@app.route('/api/postings/', methods=['DELETE'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def delete_postings():
    id = request.args.get('id')

    # Only the owner of this post can delete it
    query = Postings.query
    posting = query.filter(Postings.id == id).first()
    if not posting:
        return '', 400

    # Verify this person is the owner
    if not g.user['id'] == posting.owner:
        return '', 403

    # Else continue with the delete
    db.session.delete(posting)
    db.session.commit()
    return '', 200


@app.route('/api/postings/', methods=['PUT'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def put_postings():
    id = request.form.get('id')
    # Some error handling
    if not id:
        return '', 400
    id = escape(id)

    description = request.form.get('description')
    if description: description = escape(description)
    category = request.form.get('category')
    if category: category = escape(category)
    cost = request.form.get('cost')
    if cost: cost = escape(cost)
    title = request.form.get('title')
    if title: title = escape(title)
    try:
        category = int(category)
        if not db.session.query(exists().where(Categories.id == category)):
            return '', 400
    except ValueError:
        return '', 400
    # If we don't have a numeric cost, make it free
    try:
        cost = float(cost)
    except ValueError:
        cost = 0.0

    # Else continue
    post = Postings.query(Postings.id==id & Postings.owner==g.user['id']).first()

    # Some sanity checking
    if not all([post, category, cost, title]):
        return '', 400

    if description: post.description = description
    if category: post.category = category
    if cost: post.cost = cost
    if title: post.title = title

    db.session.commit()

    return '', 200

if __name__ == '__main__':
    app.run()
