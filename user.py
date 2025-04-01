from flask import Blueprint, request, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from passlib.hash import bcrypt
import uuid
import random
import string
import datetime
import re
from db import db  

user_bp = Blueprint("user", __name__, url_prefix="/user")

def generate_referral_code(length=6):
    """ Generate a unique referral code with uppercase letters & digits. """
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

def generate_short_id(prefix="usr"):
    """ Generate a short ID, e.g. usr_ab12cd. """
    suffix = uuid.uuid4().hex[:6]
    return f"{prefix}_{suffix}"

def is_valid_name(name: str) -> bool:
    """ Check if name length <= 50. """
    return len(name) <= 50

def is_valid_email(email: str) -> bool:
    """
    Check basic length & pattern for email.
    You can add more robust regex if desired.
    """
    if len(email) < 5 or len(email) > 100:
        return False
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(pattern, email))

def is_valid_phone(phone: str) -> bool:
    """ Check phone is exactly 10 digits. """
    pattern = r"^[0-9]{10}$"
    return bool(re.match(pattern, phone))

def is_valid_password(password: str) -> bool:
    """
    Check password constraints:
    - 8 to 16 chars
    - at least one uppercase, one lowercase, one digit, and one special char
    """
    pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,16}$'
    return bool(re.match(pattern, password))

@user_bp.route("/register", methods=["POST"])
def register():
    """
    Registers a new user with:
      - name (max 50 chars)
      - email (unique, 5-100 chars)
      - phone (unique, 10 digits)
      - password (8–16 chars, must include uppercase, lowercase, digit, special char)
    
    Body JSON example:
    {
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "1234567890",
      "password": "Abc@1234"
    }
    """
    data = request.json or {}
    name = data.get("name", "")
    email = data.get("email", "")
    phone = data.get("phone", "")
    password = data.get("password", "")

    if not name or not is_valid_name(name):
        return jsonify({"error": "Invalid name (max 50 chars)."}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Invalid email format or length (5-100 chars)."}), 400
    if not is_valid_phone(phone):
        return jsonify({"error": "Phone must be exactly 10 digits."}), 400
    if not is_valid_password(password):
        return jsonify({
            "error": "Password must be 8-16 chars with uppercase, lowercase, digit, and special char."
        }), 400

    existing_user = db.users.find_one({
        "$or": [{"email": email}, {"phone": phone}]
    })
    if existing_user:
        if existing_user["email"] == email:
            return jsonify({"error": "Email already registered."}), 400
        else:
            return jsonify({"error": "Phone number already registered."}), 400

    user_id_str = str(ObjectId())  

    referral_code = generate_referral_code(6)
    while db.users.find_one({"referralCode": referral_code}):
        referral_code = generate_referral_code(6)

    password_hash = bcrypt.hash(password)

    user_doc = {
        "userId": user_id_str,         
        "referralCode": referral_code,
        "name": name,
        "email": email,
        "phone": phone,
        "passwordHash": password_hash,
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }

    db.users.insert_one(user_doc)

    return jsonify({
        "message": "User registered successfully",
        "userId": user_id_str,
    }), 201

@user_bp.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email", "")
    phone = data.get("phone", "")
    password = data.get("password", "")

    if not password:
        return jsonify({"error": "Password is required"}), 400
    if not email and not phone:
        return jsonify({"error": "Either email or phone is required"}), 400

    query = {"email": email} if email else {"phone": phone}

    # Find user without passwordHash and referralCode
    user_doc = db.users.find_one(query, {
        "_id": 0,
        "passwordHash": 0,
        "referralCode": 0  # Explicitly exclude referralCode
    })
    if not user_doc:
        return jsonify({"error": "Invalid credentials"}), 401

    # Fetch passwordHash only
    stored_hash = db.users.find_one(query, {"passwordHash": 1})
    if not stored_hash:
        return jsonify({"error": "Invalid credentials"}), 401

    if not bcrypt.verify(password, stored_hash["passwordHash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "message": "Login successful",
        "user": user_doc
    }), 200

@user_bp.route("/getlist", methods=["GET"])
def get_user_list():
    """
    Returns a list of all users (excluding passwordHash).
    """
    users_cursor = db.users.find({}, {
        "_id": 0, 
        "passwordHash": 0
    })
    users_list = list(users_cursor)
    return jsonify(users_list), 200

@user_bp.route("/getbyid", methods=["GET"])
def get_user_by_id():
    """
    GET /user/getbyid?userId=<someId>
    Example: /user/getbyid?userId=usr_abc123
    """
    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId query parameter is required"}), 400

    user_doc = db.users.find_one({"userId": user_id}, {
        "_id": 0,
        "passwordHash": 0
    })
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"status": 200,
        "user": user_doc}), 200

@user_bp.route("/delete", methods=["POST"])
def delete_user():
    data = request.json or {}
    user_id = data.get("userId")

    if not user_id:
        return jsonify({"error": "userId is required in the body"}), 400

    result = db.users.delete_one({"userId": user_id})
    if result.deleted_count == 0:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"message": "User deleted successfully"}), 200


@user_bp.route("/updatedetails", methods=["POST"])
def update_user_details():
    data = request.json or {}
    user_id = data.get("userId")

    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    update_fields = {}
    if "name" in data:
        if not is_valid_name(data["name"]):
            return jsonify({"error": "Invalid name (max 50 chars)."}), 400
        update_fields["name"] = data["name"]

    if "email" in data:
        if not is_valid_email(data["email"]):
            return jsonify({"error": "Invalid email or length exceeded."}), 400
        
        existing_email = db.users.find_one(
            {"email": data["email"], "userId": {"$ne": user_id}}
        )
        if existing_email:
            return jsonify({"error": "Email is already used by another account."}), 400
        
        update_fields["email"] = data["email"]

    if "phone" in data:
        if not is_valid_phone(data["phone"]):
            return jsonify({"error": "Phone must be exactly 10 digits."}), 400
        
        existing_phone = db.users.find_one(
            {"phone": data["phone"], "userId": {"$ne": user_id}}
        )
        if existing_phone:
            return jsonify({"error": "Phone number is already used by another account."}), 400
        
        update_fields["phone"] = data["phone"]

    if not update_fields:
        return jsonify({"error": "No valid fields to update."}), 400

    update_fields["updatedAt"] = datetime.datetime.utcnow()

    result = db.users.update_one(
        {"userId": user_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        return jsonify({"error": "User not found."}), 404

    return jsonify({"status":200, "message": "User details updated."}), 200

@user_bp.route("/updatepassword", methods=["POST"])
def update_password():
    
    data = request.json or {}
    user_id = data.get("userId")
    old_password = data.get("oldPassword", "")
    new_password = data.get("newPassword", "")

    if not user_id or not old_password or not new_password:
        return jsonify({"error": "userId, oldPassword, and newPassword are required"}), 400

    if not is_valid_password(new_password):
        return jsonify({
            "error": (
                "Password must be 8-16 chars, include uppercase, lowercase, "
                "digit, and special character."
            )
        }), 400

    user_doc = db.users.find_one({"userId": user_id})
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    if not bcrypt.verify(old_password, user_doc["passwordHash"]):
        return jsonify({"error": "Old password is incorrect"}), 401

    new_hash = bcrypt.hash(new_password)
    db.users.update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "passwordHash": new_hash,
                "updatedAt": datetime.datetime.utcnow()
            }
        }
    )
    return jsonify({"message": "Password updated successfully"}), 200

@user_bp.route("/referral", methods=["GET"])
def get_referral_info():
    user_id = request.args.get("userId", "")

    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    user_doc = db.users.find_one(
        {"userId": user_id},
        {"referralCode": 1, "referralCount": 1, "_id": 0}
    )

    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "referralCode": user_doc.get("referralCode", ""),
        "referralCount": user_doc.get("referralCount", 0)
    }), 200