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
    """
    POST /user/register
    Request JSON Body:
    {
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "8006045606",         // exactly 10 digits
      "dob": "1990-01-01",
      "stateId": "<state_id>",
      "cityId": "<city_id>",
      "referralCode": "OPTIONAL_CODE"
    }
    Registers a new user only if the phone number is verified.
    It fetches the state name and city name from the 'india_states' collection using
    the provided stateId and cityId.
    """
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()  # exactly 10 digits
    dob = data.get("dob", "").strip()        # YYYY-MM-DD
    state_id = data.get("stateId", "").strip()
    city_id = data.get("cityId", "").strip()
    used_referral_code = data.get("referralCode")

    if not name or not is_valid_name(name):
        return jsonify({"error": "Invalid name (max 50 chars)."}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Invalid email format or length (5-100 chars)."}), 400
    if not is_valid_phone(phone):
        return jsonify({"error": "Phone must be exactly 10 digits."}), 400
    if not state_id or not city_id:
        return jsonify({"error": "State ID and City ID are required."}), 400
    try:
        dob_parsed = datetime.datetime.strptime(dob, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return jsonify({"error": "Invalid date of birth format (YYYY-MM-DD required)."}), 400

    full_phone = "+91" + phone
    # Check if phone number is verified
    if not db.verified_phone.find_one({"phone": full_phone}):
        return jsonify({"error": "Phone number is not verified. Please verify your phone first."}), 400

    # Check for existing user by email or phone
    existing_user = db.users.find_one({"$or": [{"email": email}, {"phone": phone}]})
    if existing_user:
        if existing_user.get("email") == email:
            return jsonify({"error": "Email already registered."}), 400
        else:
            return jsonify({"error": "Phone number already registered."}), 400

    # Fetch state details from the 'india_states' collection using the provided stateId
    state_doc = db.india_states.find_one({"stateId": state_id})
    if not state_doc:
        return jsonify({"error": "Invalid state ID."}), 400

    # Find the city within the state's cities list using the provided cityId
    city_obj = None
    for city in state_doc.get("cities", []):
        if city.get("cityId") == city_id:
            city_obj = city
            break
    if not city_obj:
        return jsonify({"error": "Invalid city ID for the given state."}), 400

    # Generate unique user ID and referral code
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

    # Create the user document with the state and city details
    user_doc = {
        "userId": user_id_str,
        "referralCode": referral_code,
        "referredBy": referred_by,
        "referralCount": 0,
        "name": name,
        "email": email,
        "phone": phone,  # stored as 10 digits
        "stateId": state_id,
        "stateName": state_doc.get("name"),
        "cityId": city_id,
        "cityName": city_obj.get("name"),
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
def update_user_details1():
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
    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId query param required"}), 400

    # Find the user by userId
    referrer = db.users.find_one({"userId": user_id})
    if not referrer:
        return jsonify({"error": "User not found"}), 404

    # Get the referral code for this user
    referral_code = referrer.get("referralCode")
    if not referral_code:
        return jsonify({"error": "User does not have a referral code"}), 404

    # Find all users that were referred by this referral code
    referred_users = list(db.users.find(
        {"referredBy": referral_code},
        {"_id": 0, "passwordHash": 0}
    ))

    return jsonify({
        "referralCode": referral_code,
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

@user_bp.route("/update", methods=["POST"])
def update_user_details():
    data = request.get_json() or {}
    user_id = data.get("userId")
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    update_fields = {}

    # Update name if provided
    if "name" in data:
        if not is_valid_name(data["name"]):
            return jsonify({"error": "Invalid name (max 50 chars)."}), 400
        update_fields["name"] = data["name"].strip()

    # Update email if provided
    if "email" in data:
        email = data["email"].strip()
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email format or length (5-100 chars)."}), 400
        existing_email = db.users.find_one({"email": email, "userId": {"$ne": user_id}})
        if existing_email:
            return jsonify({"error": "Email is already used by another account."}), 400
        update_fields["email"] = email

    # Disallow updating the phone number unless it is the same as before.
    if "phone" in data:
        current_user = db.users.find_one({"userId": user_id})
        current_phone = current_user.get("phone", "").strip() if current_user else ""
        new_phone = data["phone"].strip()
        if new_phone != current_phone:
            return jsonify({"error": "Phone number cannot be updated."}), 400

    # Update date of birth if provided
    if "dob" in data:
        try:
            dob_parsed = datetime.datetime.strptime(data["dob"], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return jsonify({"error": "Invalid date of birth format (YYYY-MM-DD required)."}), 400
        update_fields["dob"] = dob_parsed

    # Update location if stateId and cityId are provided
    if "stateId" in data or "cityId" in data:
        if not ("stateId" in data and "cityId" in data):
            return jsonify({"error": "Both stateId and cityId are required to update location."}), 400

        state_id = data["stateId"].strip()
        city_id = data["cityId"].strip()
        if not state_id or not city_id:
            return jsonify({"error": "Both stateId and cityId must be non-empty."}), 400

        # Fetch the state document from the 'india_states' collection
        state_doc = db.india_states.find_one({"stateId": state_id})
        if not state_doc:
            return jsonify({"error": "Invalid stateId."}), 400

        # Find the city within the state's cities list using the provided cityId
        city_obj = None
        for city in state_doc.get("cities", []):
            if city.get("cityId") == city_id:
                city_obj = city
                break
        if not city_obj:
            return jsonify({"error": "Invalid cityId for the given stateId."}), 400

        # Update the location fields
        update_fields["stateId"] = state_id
        update_fields["stateName"] = state_doc.get("name")
        update_fields["cityId"] = city_id
        update_fields["cityName"] = city_obj.get("name")

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