import os
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["github_bot"]
reviews_collection = db["reviews"]


def save_review(repo: str, pr_number: int, pr_title: str, review: str):
    reviews_collection.insert_one({
        "repo": repo,
        "pr_number": pr_number,
        "pr_title": pr_title,
        "review": review,
        "timestamp": datetime.utcnow(),
    })


def get_reviews(repo: str = None) -> list:
    query = {"repo": repo} if repo else {}
    return list(reviews_collection.find(query, {"_id": 0}).sort("timestamp", -1))