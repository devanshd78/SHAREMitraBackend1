from flask import Flask, request, jsonify, Blueprint
from pymongo import MongoClient
import bcrypt
import re
from bson import ObjectId

auth_bp = Blueprint('authentication', __name__)

# Connect to MongoDB.
client = MongoClient("mongodb://localhost:27017")
db = client["enoylity"]

@auth_bp.route("/login", methods=['POST'])
def login():
    input_data = request.get_json()
    email = input_data['email']
    password = input_data['password']
    
    # Retrieve the user by email.
    user = db.users.find_one({'email': email})

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        # Convert all ObjectId fields to strings
        user['_id'] = str(user['_id'])  # Just in case you return it later
        user['userId'] = str(user.get('userId', ''))

        return jsonify({
            'status': 1,
            'msg': "User exists",
            'user': user
        })
    else:
        return jsonify({
            'status': 0,
            'msg': "User not exists",
        })


@auth_bp.route("/register", methods=['POST'])
def register():
    input_data = request.get_json()
    
    name = input_data.get('fullName')
    email = input_data.get('email')
    phonenumber = input_data.get('phonenumber')
    password = input_data.get('password')

    # Validate phone number (10-digit numeric).
    if not re.fullmatch(r"\d{10}", phonenumber):
        return jsonify({
            'status': 0,
            'msg': "Phone number must be exactly 10 digits.",
            'class': "error"
        })

    # Validate password strength.
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,16}$", password):
        return jsonify({
            'status': 0,
            'msg': "Password must be 8-16 characters long, include uppercase, lowercase, a number, and a special character.",
            'class': "error"
        })

    if "gmail" in password.lower():
        return jsonify({
            'status': 0,
            'msg': "Password should not contain 'gmail'.",
            'class': "error"
        })

    # Check if the email is already registered.
    existing_user = db.users.find_one({'email': email})
    if existing_user:
        return jsonify({
            'status': 0,
            'msg': "User with this email already exists.",
            'class': "error"
        })

    # Limit registrations per phone number to 3.
    email_count = db.users.count_documents({'phonenumber': phonenumber})
    if email_count >= 3:
        return jsonify({
            'status': 0,
            'msg': "A maximum of 3 email addresses can be registered with this phone number.",
            'class': "error"
        })

    # Hash password.
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    # Generate a new ObjectId and convert it to string.
    new_id = str(ObjectId())
    new_user = {
        "userId": new_id,      # Store it as userId as well
        "fullName": name,
        "email": email,
        "phonenumber": phonenumber,
        "password": hashed_password.decode('utf-8')
    }

    db.users.insert_one(new_user)
    
    return jsonify({
        'status': 1,
        'msg': "User registered successfully",
    })
