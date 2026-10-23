"""Reusable PyMongo connection helper."""
import os
from functools import lru_cache
from pymongo import MongoClient

@lru_cache(maxsize=1)
def get_mongo_client():
    return MongoClient(os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
                       serverSelectionTimeoutMS=5000)

def get_database():
    return get_mongo_client()[os.getenv("MONGODB_DATABASE", "splitmate")]
