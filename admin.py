import re
import bcrypt
from flask import Flask, request, jsonify, Blueprint
from pymongo import MongoClient
from bson import ObjectId

admin_bp = Blueprint("admin", __name__)

client = MongoClient("mongodb://localhost:27017")
db = client["enoylity"]
admins_collection = db["admins"]

@admin_bp.route("/login", methods=["POST"])
def login_admin():
    input_data = request.get_json()
    email = input_data.get('email')
    password = input_data.get('password')

    admin = admins_collection.find_one({'email': email})
    if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password'].encode('utf-8')):
        admin['_id'] = str(admin['_id'])
        del admin['password']
        admin['role'] = "admin"
        return jsonify({
            'status': 200,
            'msg': "Login successful",
            'user': admin
        }), 200
    else:
        return jsonify({
            'status': 401,
            'msg': "Invalid email or password",
        }), 401


@admin_bp.route("/update", methods=["POST"])
def update_admin():
    data = request.get_json() or {}
    admin_id = data.get("adminId")
    if not admin_id:
        return jsonify({
            "status": 0,
            "msg": "adminId is required.",
            "class": "error"
        }), 400

    # Require both email and new password for update
    if "email" not in data or "password" not in data:
        return jsonify({
            "status": 0,
            "msg": "Both email and new password are required for update.",
            "class": "error"
        }), 400

    update_fields = {}

    # Update email with uniqueness check
    new_email = data.get("email")
    existing_admin = admins_collection.find_one({
        "email": new_email,
        "adminId": {"$ne": admin_id}
    })
    if existing_admin:
        return jsonify({
            "status": 0,
            "msg": "Another admin with this email already exists.",
            "class": "error"
        }), 409
    update_fields["email"] = new_email

    # Update password with validations
    new_password = data.get("password")
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,16}$", new_password):
        return jsonify({
            "status": 0,
            "msg": "Password must be 8-16 chars, include uppercase, lowercase, number, special char.",
            "class": "error"
        }), 400
    if "gmail" in new_password.lower():
        return jsonify({
            "status": 0,
            "msg": "Password should not contain 'gmail'.",
            "class": "error"
        }), 400
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    update_fields["password"] = hashed_password

    result = admins_collection.update_one(
        {"adminId": admin_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        return jsonify({
            "status": 0,
            "msg": "Admin not found.",
            "class": "error"
        }), 404

    updated_admin = admins_collection.find_one(
        {"adminId": admin_id},
        {"_id": 0, "password": 0}
    )

    return jsonify({
        "status": 200,
        "msg": "Admin details updated successfully.",
        "admin": updated_admin
    }), 200

def create_default_admin():
    """
    Creates a predefined admin with:
      - Email: admin@sharemitra.com
      - Password: Admin@1234
    if it does not already exist in the database.
    """
    default_email = "admin@sharemitra.com"
    default_password = "Admin@1234"
    existing_admin = admins_collection.find_one({'email': default_email})
    if not existing_admin:
        hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        admin_data = {
            "adminId": str(ObjectId()),
            "email": default_email,
            "password": hashed_password
        }
        admins_collection.insert_one(admin_data)
        print("Default admin created.")
create_default_admin()
