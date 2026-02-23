import os

mongo_uri = "mongodb://admin:Xinghuaxin070419@182.92.128.249:27017/?authSource=admin"


class Config:
    # SECRET_KEY = os.environ.get('SECRET_KEY') or ""
    USER = os.environ.get('SECRET_KEY') or "admin"
    PASSWORD = os.environ.get('SECRET_KEY') or "Xinghuaxin070419"
