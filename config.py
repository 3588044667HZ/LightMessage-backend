import os

# mongo_uri = "mongodb://admin:Xinghuaxin070419@182.92.128.249:27017/?authSource=admin"
from dotenv import load_dotenv

load_dotenv()


class Config:
    # SECRET_KEY = os.environ.get('SECRET_KEY') or ""
    USER = os.environ.get('USER')
    PASSWORD = os.environ.get('SECRET_KEY')
    HOST = os.environ.get('MONGO_HOST')
    PORT = os.environ.get('MONGO_PORT')
    AUTH_SOURCE = os.environ.get('MONGO_AUTH_SOURCE')

    # __getattr__ = os.environ.get('MONGO_METHOD')
    def __getattr__(self, item):
        if item == "mongo_uri":
            return f"mongodb://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/?authSource={self.AUTH_SOURCE}"
        else:
            return super().__getattribute__(item)
