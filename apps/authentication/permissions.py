from datetime import datetime, timezone
from infrastructure.database.mongodb import get_database
from django.contrib.auth.hashers import make_password, check_password
from pymongo.errors import DuplicateKeyError


def users():
    return get_database()["users"]


def verification_codes():
    return get_database()["verification_codes"]


def ensure_indexes():
    users().create_index("email", unique=True)
    verification_codes().create_index("expires_at", expireAfterSeconds=0)


def create_user(full_name, email, password):
    email = email.strip().lower()
    ensure_indexes()

    user = {
        "full_name": full_name.strip(),
        "email": email,
        "password_hash": make_password(password),
        "is_email_verified": False,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = users().insert_one(user)
        user["_id"] = result.inserted_id
        return user
    except DuplicateKeyError:
        return None


def get_user_by_email(email):
    return users().find_one({"email": email.strip().lower()})


def get_user_by_id(user_id):
    from bson import ObjectId

    if not ObjectId.is_valid(user_id):
        return None

    return users().find_one({"_id": ObjectId(user_id)})


def check_user_password(user, password):
    return bool(
        user
        and user.get("is_active", True)
        and check_password(password, user["password_hash"])
    )


def save_code(email, code, purpose, expires_at):
    verification_codes().delete_many({
        "email": email,
        "purpose": purpose,
    })

    verification_codes().insert_one({
        "email": email,
        "code_hash": make_password(code),
        "purpose": purpose,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    })


def verify_code(email, code, purpose):
    record = verification_codes().find_one({
        "email": email,
        "purpose": purpose,
    })

    if not record:
        return False

    if record["expires_at"] <= datetime.now(timezone.utc):
        verification_codes().delete_one({"_id": record["_id"]})
        return False

    if not check_password(code, record["code_hash"]):
        return False

    verification_codes().delete_one({"_id": record["_id"]})
    return True


def mark_email_verified(email):
    users().update_one(
        {"email": email},
        {"$set": {"is_email_verified": True}},
    )


def update_password(email, password):
    users().update_one(
        {"email": email},
        {"$set": {"password_hash": make_password(password)}},
    )