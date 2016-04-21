from os import environ
from math import isinf, isnan
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
from sphinxsearch import SphinxClient, SPH_SORT_ATTR_DESC, SPH_SORT_ATTR_ASC, SPH_MATCH_EXTENDED2
import logging

import os
from flask import Flask, request, redirect, url_for
from werkzeug import secure_filename

ALLOWED_EXTENSIONS = set(['png','jpeg','jpg'])

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
app.config['UPLOAD_FOLDER'] = '/var/www/images/'
db.init_app(app)

with app.app_context():
    Session(app)

#### Helpers ####

# Image upload allowed
def allowed_file(filename):
   return '.' in filename and \
      filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

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

# Takes a string and tries to return the corresponding integer
# Else, it returns the default
def to_int(s, default=None):
    try:
        return int(s)
    except:
        return default

# Same as above, however also ignores NaN and inf
# We don't need or want these for this application
def to_float(s, default=None):
    try:
        f = float(s)
        if isnan(f) or isinf(f):
            return default
        return f
    except:
        return default

# Takes a SQLAlchemy mapping and converts it to representational dictionary
def to_dict(row, email):
    res = {'email':email}
    for c in row.__table__.columns:
        res[c.name] = getattr(row, c.name)
    return res

# Searching helper
# Workflow for search calls to get_postings
def search():
    keywords = request.args.get('keywords')
    sort = request.args.get('sort')
    client = SphinxClient()
    client.SetServer(SEARCH_HOST, SEARCH_PORT)

    # Sorting mode
    if sort == 'newest':
        client.SetSortMode(SPH_SORT_ATTR_DESC, 'date_added')
    elif sort == 'oldest':
        client.SetSortMode(SPH_SORT_ATTR_ASC, 'date_added')
    elif sort == 'highest_cost':
        client.SetSortMode(SPH_SORT_ATTR_DESC, 'cost')
    elif sort == 'lowest_cost':
        client.SetSortMode(SPH_SORT_ATTR_ASC, 'cost')
    
    # Filter by category
    category = to_int(request.args.get('category'))
    if category:
        client.SetFilter('category', [category])

    # Paging
    per_page = to_int(request.args.get('per_page', default=20))
    page = to_int(request.args.get('page', default=1))
    if page < 1: page = 1

    # Use our SphinxSearch query to construct our page
    client.SetLimits(per_page*(page-1), per_page)

    # Set search mode to extended2
    client.SetMatchMode(SPH_MATCH_EXTENDED2)

    # Construct the query
    search_q = ['@!owner', keywords, '@*', keywords]
    owner = request.args.get('owner')
    if owner:
        search_q.append('@owner')
        search_q.append(owner)

    # Handle the query
    q = client.Query(' '.join(search_q))
    if not q:
        return 'Could not complete search', 400
    # Handle failing to find results
    if not q['matches']:
        return jsonify(data=[], num_pages=0), 200
    
    # Otherwise generate a list of ids
    ids = []
    for res in q['matches']:
        ids.append(res['id'])

    # If there are no matches
    if not ids:
        return jsonify(data=[], num_pages=0), 200

    # First construct the subquery
    s_ids = db.session.query(func.unnest(array(ids)).label('id')).subquery('s_ids')

    # Then create the query
    query = Postings.query.join(s_ids, Postings.id == s_ids.c.id)
    query = query.join(User, User.id == Postings.owner).add_columns(User.email)

    # Return the JSON
    return jsonify(data=[to_dict(r, email) for r, email in query.all()], num_pages=((q['total']/per_page)+1)), 200


# Browse helper
# Separate workflow for non-search get_postings
def browse():
    id = request.args.get('id')
    if id: id = to_int(escape(id))
    owner = request.args.get('owner')
    if owner: owner = to_int(escape(owner))
    category = request.args.get('category')
    if category: category = to_int(escape(category))
    cost = request.args.get('cost')
    if cost: cost = to_float(escape(cost))
    max_cost = request.args.get('max_cost')
    if max_cost: max_cost = to_float(escape(max_cost))

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

    query = query.join(User, User.id == Postings.owner).add_columns(User.email)

    # Sorting
    sort = request.args.get('sort', default='newest')
    s_dict = {
        'newest':       Postings.timestamp.desc(),
        'oldest':       Postings.timestamp.asc(),
        'highest_cost': Postings.cost.desc(),
        'lowest_cost':  Postings.cost.asc(),
        }

    query = query.order_by(s_dict.get(sort, Postings.timestamp.asc()))

    # Paginate
    page = query.paginate(page, per_page, error_out=False)

    # Return the JSON
    return jsonify(data=[to_dict(r, email) for r,email in page.items], num_pages=page.pages), 200

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

#### API ####
# Postings API:
# Get a posting
@app.route('/api/postings/', methods=['GET'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def get_postings():
    if request.args.get('keywords'):
        return search()
    else:
        return browse()

# Add a new posting
@app.route('/api/postings/', methods=['POST'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def post_postings():
    for f in request.files.getlist('images'):
        if allowed_file(f.filename):
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    description = request.form.get('description')
    if description: description = escape(description)
    category = request.form.get('category')
    if category: category = escape(category)
    cost = request.form.get('cost')
    if cost: cost = escape(cost)
    title = request.form.get('title')
    if title:
        title = escape(title)
    else:
        return 'No title given', 400

    # Error checking and conversion
    try:
        category = float(category)
        if not db.session.query(exists().where(Categories.id == category)):
            return 'Bad category', 400
    except (ValueError, TypeError):
        return 'Bad category', 400
    try:
        cost = float(cost)
    except (ValueError, TypeError):
        return 'No cost given', 400


    # Check othr valid floats
    if isnan(category) or isnan(cost) or isinf(category) or isinf(cost):
        return 'Invalid cost or category', 400

    # Else continue
    post = Postings(owner=g.user['id'], description=description, cost=cost,
        category=int(category), title=title)
    
    # Add entry to database and commit
    # Also prevent duplicate entries due to double clicks
    if not db.session.query(exists().where((Postings.owner==g.user['id']) &
        (Postings.description==description) & (Postings.category==category) &
        (Postings.title==title))).scalar():
        db.session.add(post)
        db.session.commit()

    return '',  200

# Deleting a posting
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

# Updating a posting
@app.route('/api/postings/', methods=['PUT'], strict_slashes=False)
@cross_origin(origins=environ['CORS_URLS'].split(','), supports_credentials=True)
@auth_req
def put_postings():
    id = request.form.get('id')
    # Some error handling
    if not id:
        return 'Bad ID', 400
    id = escape(id)

    description = request.form.get('description')
    if description: description = escape(description)
    category = request.form.get('category')
    if category:
        category = escape(category)
        if not db.session.query(exists().where(Categories.id == category)):
            return 'Bad category', 400
    cost = request.form.get('cost')
    if cost:
        cost = escape(cost)
        try:
            cost = float(cost)
            if any([isnan(cost), isinf(cost)]):
                return 'Bad cost', 400
        except (ValueError, TypeError):
            return 'Bad cost', 400
    title = request.form.get('title')
    if title: title = escape(title)

    # Else continue
    q = db.session.query(Postings)
    q = q.filter(Postings.id==id)
    q = q.filter(Postings.owner==g.user['id'])
    post = q.first()

    # Some sanity checking
    if not post:
        return 'No post with that given ID', 400

    if description: post.description = description
    if category: post.category = category
    if cost: post.cost = cost
    if title: post.title = title

    # Update the timestamp
    post.timestamp = func.now()

    db.session.commit()

    return '', 200

if __name__ == '__main__':
    app.run()