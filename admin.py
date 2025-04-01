import re
import bcrypt
from flask import Flask, request, jsonify, Blueprint
from pymongo import MongoClient
from bson import ObjectId

admin_bp = Blueprint("admin", __name__)

client = MongoClient("mongodb://localhost:27017")
db = client["enoylity"]
admins_collection = db["admins"]

@admin_bp.route("/register-admin", methods=["POST"])
def register_admin():
    data = request.get_json()
    admin_name = data.get('fullName')
    admin_email = data.get('email')
    admin_phonenumber = data.get('phonenumber')
    password = data.get('password')

    if not re.fullmatch(r"\d{10}", admin_phonenumber):
        return jsonify({
            'status': 0,
            'msg': "Phone number must be exactly 10 digits.",
            'class': "error"
        }), 400

    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,16}$", password):
        return jsonify({
            'status': 0,
            'msg': "Password must be 8-16 chars, include uppercase, lowercase, number, special char.",
            'class': "error"
        }), 400

    if "gmail" in password.lower():
        return jsonify({
            'status': 0,
            'msg': "Password should not contain 'gmail'.",
            'class': "error"
        }), 400

    existing_admin = admins_collection.find_one({'email': admin_email})
    if existing_admin:
        return jsonify({
            'status': 0,
            'msg': "User with this email already exists.",
            'class': "error"
        }), 409

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    admin_data = {
        "adminId": str(ObjectId()),
        "fullName": admin_name,
        "email": admin_email,
        "phonenumber": admin_phonenumber,
        "password": hashed_password
    }

    admins_collection.insert_one(admin_data)

    return jsonify({
        'status': 200,
        'msg': "Admin registered successfully",
    }), 200

@admin_bp.route("/login-admin", methods=["POST"])
def login_admin():
    input_data = request.get_json()
    email = input_data.get('email')
    password = input_data.get('password')

    admin = admins_collection.find_one({'email': email})

    if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password'].encode('utf-8')):
        admin['_id'] = str(admin['_id'])
        del admin['password']

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
