from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stats.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True)

    def __init__(self, username):
        self.username = username

    def __repr__(self):
        return '<User %r>' % self.username

class Stat(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    user = db.relationship('User',
        backref=db.backref('posts', lazy='dynamic'))

    tc = db.Column(db.Integer)
    qi = db.Column(db.Integer)

    time = db.Column(db.DateTime, primary_key=True)

    def __init__(self, user, tc, qi, time=None):
        self.user = user
        self.tc = tc
        self.qi = qi
        if time is None:
            time = datetime.utcnow()
        self.time = time

    def __repr__(self):
        return '<Stat tc=%r qi=%r>' % (self.tc, self.qi)

db.Index('user_id_time', Stat.user_id, Stat.time)