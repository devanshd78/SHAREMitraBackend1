from flask import Flask, request, jsonify, Blueprint
import datetime,time
from bson.objectid import ObjectId
from passlib.hash import bcrypt
import uuid
import random
import string
import re
from db import db 
from twilio.rest import Client
from dotenv import load_dotenv
import os

load_dotenv()


user_bp = Blueprint("user", __name__, url_prefix="/user")



TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise Exception("Twilio credentials must be set in the environment.")
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# In-memory OTP store for demo purposes (keyed by full phone number e.g. +918006045606)
OTP_STORE = {}


def generate_referral_code(length=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

def generate_short_id(prefix="usr"):
    suffix = uuid.uuid4().hex[:6]
    return f"{prefix}_{suffix}"

def is_valid_name(name: str) -> bool:
    return len(name) <= 50

def is_valid_email(email: str) -> bool:
    if len(email) < 5 or len(email) > 100:
        return False
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(pattern, email))

def is_valid_phone(phone: str) -> bool:
    # Expects exactly 10 digits (no country code)
    pattern = r"^[0-9]{10}$"
    return bool(re.match(pattern, phone))

@user_bp.route("/sendOTP", methods=["POST"])
def send_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        if not phone or not is_valid_phone(phone):
            return jsonify({"error": "Valid phone number (10 digits) is required"}), 400

        full_phone = "+91" + phone
        # Generate a random 6-digit OTP
        otp = ''.join(random.choices(string.digits, k=6))
        OTP_STORE[full_phone] = {"otp": otp, "timestamp": time.time()}

        try:
            twilio_client.messages.create(
                body=f"Your OTP is: {otp}",
                from_=TWILIO_PHONE_NUMBER,
                to=full_phone
            )
        except Exception as e:
            return jsonify({"error": "Failed to send OTP", "details": str(e)}), 500

        return jsonify({"message": "OTP sent successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Unexpected error occurred", "details": str(e)}), 500


@user_bp.route("/verifyOTP", methods=["POST"])
def verify_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        otp_submitted = data.get("otp", "").strip()
        if not phone or not otp_submitted:
            return jsonify({"error": "phone and otp are required"}), 400

        full_phone = "+91" + phone
        record = OTP_STORE.get(full_phone)
        if not record:
            return jsonify({"error": "OTP not found for this phone number"}), 400

        # OTP is valid for 5 minutes (300 seconds)
        if time.time() - record["timestamp"] > 300:
            return jsonify({"error": "OTP expired"}), 400

        if otp_submitted != record["otp"]:
            return jsonify({"error": "Incorrect OTP"}), 400

        # Mark phone as verified if not already verified
        if not db.verified_phone.find_one({"phone": full_phone}):
            db.verified_phone.insert_one({
                "phone": full_phone,
                "verifiedAt": datetime.datetime.utcnow()
            })
        del OTP_STORE[full_phone]
        return jsonify({"message": "Phone verified successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Unexpected error occurred", "details": str(e)}), 500


@user_bp.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()  # exactly 10 digits
        dob = data.get("dob", "").strip()        # YYYY-MM-DD
        city = data.get("city", "").strip()
        state = data.get("state", "").strip()
        used_referral_code = data.get("referralCode")

        if not name or not is_valid_name(name):
            return jsonify({"error": "Invalid name (max 50 chars)."}), 400
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email format or length (5-100 chars)."}), 400
        if not is_valid_phone(phone):
            return jsonify({"error": "Phone must be exactly 10 digits."}), 400
        if not city or not state:
            return jsonify({"error": "City and state are required."}), 400

        try:
            dob_parsed = datetime.datetime.strptime(dob, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return jsonify({"error": "Invalid date of birth format (YYYY-MM-DD required)."}), 400

        full_phone = "+91" + phone
        # Check if phone number is verified
        if not db.verified_phone.find_one({"phone": full_phone}):
            return jsonify({"error": "Phone number is not verified. Please verify your phone first."}), 400

        # Check for existing user
        existing_user = db.users.find_one({"$or": [{"email": email}, {"phone": phone}]})
        if existing_user:
            if existing_user.get("email") == email:
                return jsonify({"error": "Email already registered."}), 400
            else:
                return jsonify({"error": "Phone number already registered."}), 400

        user_id_str = str(ObjectId())
        referral_code = generate_referral_code(6)
        while db.users.find_one({"referralCode": referral_code}):
            referral_code = generate_referral_code(6)

        referred_by = None
        if used_referral_code:
            referrer = db.users.find_one({"referralCode": used_referral_code})
            if not referrer:
                return jsonify({"error": "Invalid referral code."}), 400
            referred_by = used_referral_code
            db.users.update_one({"referralCode": used_referral_code}, {"$inc": {"referralCount": 1}})

        user_doc = {
            "userId": user_id_str,
            "referralCode": referral_code,
            "referredBy": referred_by,
            "referralCount": 0,
            "name": name,
            "email": email,
            "phone": phone,  # stored as 10 digits
            "state": state,
            "city": city,
            "dob": dob_parsed,
            "razorpay_contact_id": None,
            "razorpay_fund_account_id": None,
            "totalPayoutAmount": 0,
            "createdAt": datetime.datetime.utcnow(),
            "updatedAt": datetime.datetime.utcnow()
        }
        db.users.insert_one(user_doc)
        
        # Create wallet document for the user
        wallet_doc = {
            "userId": user_id_str,
            "total_earning": 0,
            "withdrawn": 0,
            "balance": 0,
            "tasks": [],
            "createdAt": datetime.datetime.utcnow(),
            "updatedAt": datetime.datetime.utcnow()
        }
        db.wallet.insert_one(wallet_doc)

        return jsonify({
            "message": "User registered successfully",
            "userId": user_id_str
        }), 201
    except Exception as e:
        return jsonify({"error": "Unexpected error occurred", "details": str(e)}), 500


@user_bp.route("/login/sendOTP", methods=["POST"])
def login_send_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        if not phone or not is_valid_phone(phone):
            return jsonify({"error": "Valid phone number (10 digits) is required"}), 400

        # Check if phone is registered
        if not db.users.find_one({"phone": phone}):
            return jsonify({"error": "Phone number not registered"}), 400

        full_phone = "+91" + phone
        otp = ''.join(random.choices(string.digits, k=6))
        OTP_STORE[full_phone] = {"otp": otp, "timestamp": time.time()}

        try:
            twilio_client.messages.create(
                body=f"Your OTP for login is: {otp}",
                from_=TWILIO_PHONE_NUMBER,
                to=full_phone
            )
        except Exception as e:
            return jsonify({"error": "Failed to send OTP", "details": str(e)}), 500

        return jsonify({"message": "OTP sent for login"}), 200
    except Exception as e:
        return jsonify({"error": "Unexpected error occurred", "details": str(e)}), 500


@user_bp.route("/login/verifyOTP", methods=["POST"])
def login_verify_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        otp_submitted = data.get("otp", "").strip()
        if not phone or not otp_submitted:
            return jsonify({"error": "phone and otp are required"}), 400

        full_phone = "+91" + phone
        record = OTP_STORE.get(full_phone)
        if not record:
            return jsonify({"error": "OTP not found for this phone number"}), 400

        # OTP valid for 5 minutes (300 seconds)
        if time.time() - record["timestamp"] > 300:
            return jsonify({"error": "OTP expired"}), 400

        if otp_submitted != record["otp"]:
            return jsonify({"error": "Incorrect OTP"}), 400

        del OTP_STORE[full_phone]
        user_doc = db.users.find_one({"phone": phone}, {"_id": 0, "passwordHash": 0})
        if not user_doc:
            return jsonify({"error": "User not found."}), 404

        return jsonify({
            "message": "Login OTP verified successfully",
            "user": user_doc
        }), 200
    except Exception as e:
        return jsonify({"error": "Unexpected error occurred", "details": str(e)}), 500

@user_bp.route("/getlist", methods=["POST"])
def get_user_list():
    data = request.get_json() or {}
    keyword = data.get("keyword", "")
    try:
        page = int(data.get("page", 0))
    except ValueError:
        return jsonify({"error": "Page must be an integer."}), 400
    try:
        per_page = int(data.get("per_page", 50))
    except ValueError:
        return jsonify({"error": "per_page must be an integer."}), 400

    query = {}
    if keyword:
        query = {
            "$or": [
                {"name": {"$regex": keyword, "$options": "i"}},
                {"email": {"$regex": keyword, "$options": "i"}},
                {"phone": {"$regex": keyword, "$options": "i"}}
            ]
        }

    total_items = db.users.count_documents(query)
    users_cursor = db.users.find(query, {"_id": 0, "passwordHash": 0}).skip(page * per_page).limit(per_page)
    users_list = list(users_cursor)

    return jsonify({
        "total": total_items,
        "page": page,
        "per_page": per_page,
        "users": users_list
    }), 200

@user_bp.route("/getbyid", methods=["GET"])
def get_user_by_id():
    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId query parameter is required"}), 400

    user_doc = db.users.find_one(
        {"userId": user_id},
        {"_id": 0, "passwordHash": 0}
    )
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    # Format datetime fields into GMT string format if they exist
    for field in ["createdAt", "updatedAt"]:
        if field in user_doc and user_doc[field]:
            try:
                user_doc[field] = user_doc[field].strftime("%a, %d %b %Y %H:%M:%S GMT")
            except Exception:
                pass

    return jsonify(user_doc), 200

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

    return jsonify({"message": "User details updated."}), 200



@user_bp.route("/referrals", methods=["GET"])
def get_referrals():
    referral_code = request.args.get("referralCode")
    if not referral_code:
        return jsonify({"error": "referralCode query param required"}), 400

    referrer = db.users.find_one({"referralCode": referral_code})
    if not referrer:
        return jsonify({"error": "Invalid referral code"}), 404

    referred_users = list(db.users.find(
        {"referredBy": referral_code},
        {"_id": 0, "passwordHash": 0}
    ))

    return jsonify({
        "referralCount": len(referred_users),
        "referredUsers": referred_users
    }), 200

@user_bp.route("/dummy", methods=["POST"])
def dummy_login():
    data = request.json or {}
    email = data.get("email", "")
    phone = data.get("phone", "")

    if not email and not phone:
        return jsonify({"error": "Either email or phone is required"}), 400

    query = {"email": email} if email else {"phone": phone}

    # Find user without passwordHash and referralCode
    user_doc = db.users.find_one(query, {
        "_id": 0,
        "passwordHash": 0,
        "referralCode": 0
    })
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "message": "Dummy login successful",
        "user": user_doc
    }), 200
