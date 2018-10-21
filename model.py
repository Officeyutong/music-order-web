from main import db


class Submit(db.Model):
    __tablename__ = "submit"


class Song(db.Model):
    __tablename__ = "song"


class Config(db.Model):
    __tablename__ = "config"
