from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy import DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY

db = SQLAlchemy()

class Categories(db.Model):
	__tablename__ = 'categories'
	# Columns
	id = Column(Integer, primary_key=True)
	name = Column(String)

	def __repr__(self):
		return "<Categories(id='%s', name='%s')>" % (self.id, self.name)

class User(db.Model):
	__tablename__ = 'user'
	# Columns
	id = Column(Numeric(scale=32), primary_key=True)
	email = Column(String)
	name = Column(String)
	wid = Column(Integer, primary_key=True)

	def __repr__(self):
		return "<User(id='%s', email='%s', name='%s', wid='%s')>" % (
			self.id, self.email, self.name, self.wid)

class Postings(db.Model):
	__tablename__ = 'postings'
	# Columns
	id = Column(Integer, primary_key=True)
	owner = Column(Numeric(scale=32), ForeignKey('user.id'))
	description = Column(String)
	cost = Column(Numeric(precision=2, scale=16))
	category = Column(Integer, ForeignKey('categories.id'))
	timestamp = Column(DateTime, default=func.now())
	title = Column(String)
	image = Column(ARRAY(String))

	def __repr__(self):
		return "<Postings(id='%s', owner='%s', description='%s', cost='%s', category='%s', timestamp='%s', title='%s')>" % (
			self.id, self.owner, self.description, self.cost, self.category, self.timestamp, self.title)