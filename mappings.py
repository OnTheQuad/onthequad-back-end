from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy import DateTime, Numeric

Base = declarative_base()

class Categories(Base):
	__tablename__ = 'categories'
	# Columns
	id = Column(Integer, primary_key=True)
	name = Column(String)

	def __repr__(self):
		return "<Categories(id='%s', name='%s')>" % (self.id, self.name)

class User(Base):
	__tablename__ = 'user'
	# Columns
	id = Column(Numeric(scale=32), primary_key=True)
	email = Column(String)
	name = Column(String)
	wid = Column(Integer, primary_key=True)

	def __repr__(self):
		return "<User(id='%s', email='%s', name='%s', wid='%s')>" % (
			self.id, self.email, self.name, self.wid)

class Postings(Base):
	__tablename__ = 'postings'
	# Columns
	id = Column(Integer, primary_key=True)
	owner = Column(Numeric(scale=32), ForeignKey('user.id'))
	description = Column(String)
	cost = Column(Numeric(precision=2, scale=16))
	category = Column(Integer, ForeignKey('categories.id'))
	timestamp = Column(DateTime)
	title = Column(String)