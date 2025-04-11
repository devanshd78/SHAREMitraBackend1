import datetime
import time
import random
import string
import re
import uuid
from bson.objectid import ObjectId
from flask import Blueprint, request
from db import db  # Adjust this import to match your actual db.py
from twilio.rest import Client
from dotenv import load_dotenv
import os

# Import the centralized response formatter from your utils module.
from utils import format_response

load_dotenv()

user_bp = Blueprint("user", __name__, url_prefix="/user")

# Twilio configuration
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
            return format_response(False, "Valid phone number (10 digits) is required", None, 400)

        full_phone = "+91" + phone
        otp = ''.join(random.choices(string.digits, k=6))
        OTP_STORE[full_phone] = {"otp": otp, "timestamp": time.time()}

        try:
            twilio_client.messages.create(
                body=f"Your OTP is: {otp}",
                from_=TWILIO_PHONE_NUMBER,
                to=full_phone
            )
        except Exception as e:
            return format_response(False, "Failed to send OTP", {"details": str(e)}, 500)

        return format_response(True, "OTP sent successfully", None, 200)
    except Exception as e:
        return format_response(False, "Unexpected error occurred", {"details": str(e)}, 500)


@user_bp.route("/verifyOTP", methods=["POST"])
def verify_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        otp_submitted = data.get("otp", "").strip()
        if not phone or not otp_submitted:
            return format_response(False, "phone and otp are required", None, 400)

        full_phone = "+91" + phone
        record = OTP_STORE.get(full_phone)
        if not record:
            return format_response(False, "OTP not found for this phone number", None, 400)

        if time.time() - record["timestamp"] > 300:
            return format_response(False, "OTP expired", None, 400)

        if otp_submitted != record["otp"]:
            return format_response(False, "Incorrect OTP", None, 400)

        if not db.verified_phone.find_one({"phone": full_phone}):
            db.verified_phone.insert_one({
                "phone": full_phone,
                "verifiedAt": datetime.datetime.utcnow()
            })
        del OTP_STORE[full_phone]
        return format_response(True, "Phone verified successfully", None, 200)
    except Exception as e:
        return format_response(False, "Unexpected error occurred", {"details": str(e)}, 500)


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
      "referedby": "OPTIONAL_REFERRAL_CODE"
    }
    Registers a new user only if the phone is verified.
    """
    try:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        dob = data.get("dob", "").strip()
        state_id = data.get("stateId", "").strip()
        city_id = data.get("cityId", "").strip()
        used_referral_code = data.get("referedby")
        
        if not name or not is_valid_name(name):
            return format_response(False, "Invalid name (max 50 chars).", None, 400)
        if not is_valid_email(email):
            return format_response(False, "Invalid email format or length (5-100 chars).", None, 400)
        if not is_valid_phone(phone):
            return format_response(False, "Phone must be exactly 10 digits.", None, 400)
        if not state_id or not city_id:
            return format_response(False, "State ID and City ID are required.", None, 400)
        try:
            dob_parsed = datetime.datetime.strptime(dob, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return format_response(False, "Invalid date of birth format (YYYY-MM-DD required).", None, 400)

        full_phone = "+91" + phone
        if not db.verified_phone.find_one({"phone": full_phone}):
            return format_response(False, "Phone number is not verified. Please verify your phone first.", None, 400)

        # Use case-insensitive email search.
        existing_user = db.users.find_one({
            "$or": [
                {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
                {"phone": phone}
            ]
        })
        if existing_user:
            if existing_user.get("email").lower() == email.lower():
                return format_response(False, "Email already registered.", None, 400)
            else:
                return format_response(False, "Phone number already registered.", None, 400)

        state_doc = db.india_states.find_one({"stateId": state_id})
        if not state_doc:
            return format_response(False, "Invalid state ID.", None, 400)

        city_obj = None
        for city in state_doc.get("cities", []):
            if city.get("cityId") == city_id:
                city_obj = city
                break
        if not city_obj:
            return format_response(False, "Invalid city ID for the given state.", None, 400)

        user_id_str = str(ObjectId())
        referral_code = generate_referral_code(6)
        while db.users.find_one({"referralCode": referral_code}):
            referral_code = generate_referral_code(6)

        referred_by = None
        if used_referral_code:
            referrer = db.users.find_one({"referralCode": used_referral_code})
            if not referrer:
                return format_response(False, "Invalid referral code.", None, 400)
            referred_by = {
                "userId": referrer.get("userId"),
                "name": referrer.get("name"),
                "phone": referrer.get("phone")
            }
            db.users.update_one(
                {"referralCode": used_referral_code},
                {"$inc": {"referralCount": 1}}
            )

        user_doc = {
            "userId": user_id_str,
            "referralCode": referral_code,
            "referredBy": referred_by,
            "referralCount": 0,
            "name": name,
            "email": email,
            "phone": phone,
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
        
        return format_response(True, "User registered successfully", {"userId": user_id_str}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@user_bp.route("/login/sendOTP", methods=["POST"])
def login_send_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        if not phone or not is_valid_phone(phone):
            return format_response(False, "Valid phone number (10 digits) is required", None, 400)

        if not db.users.find_one({"phone": phone}):
            return format_response(False, "Phone number not registered", None, 400)

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
            return format_response(False, "Failed to send OTP", {"details": str(e)}, 500)

        return format_response(True, "OTP sent for login", None, 200)
    except Exception as e:
        return format_response(False, "Unexpected error occurred", {"details": str(e)}, 500)


@user_bp.route("/login/verifyOTP", methods=["POST"])
def login_verify_otp():
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "").strip()
        otp_submitted = data.get("otp", "").strip()
        if not phone or not otp_submitted:
            return format_response(False, "phone and otp are required", None, 400)

        full_phone = "+91" + phone
        record = OTP_STORE.get(full_phone)
        if not record:
            return format_response(False, "OTP not found for this phone number", None, 400)

        if time.time() - record["timestamp"] > 300:
            return format_response(False, "OTP expired", None, 400)
        if otp_submitted != record["otp"]:
            return format_response(False, "Incorrect OTP", None, 400)

        del OTP_STORE[full_phone]
        user_doc = db.users.find_one({"phone": phone}, {"_id": 0, "passwordHash": 0})
        if not user_doc:
            return format_response(False, "User not found.", None, 404)

        return format_response(True, "Login OTP verified successfully", {"user": user_doc}, 200)
    except Exception as e:
        return format_response(False, "Unexpected error occurred", {"details": str(e)}, 500)


@user_bp.route("/getlist", methods=["POST"])
def get_user_list():
    try:
        data = request.get_json() or {}
        keyword = data.get("keyword", "")
        try:
            page = int(data.get("page", 0))
        except ValueError:
            return format_response(False, "Page must be an integer.", None, 400)
        try:
            per_page = int(data.get("per_page", 50))
        except ValueError:
            return format_response(False, "per_page must be an integer.", None, 400)

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
        return format_response(True, "User list retrieved successfully", {
            "total": total_items,
            "page": page,
            "per_page": per_page,
            "users": users_list
        }, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@user_bp.route("/getbyid", methods=["GET"])
def get_user_by_id():
    try:
        user_id = request.args.get("userId")
        if not user_id:
            return format_response(False, "userId query parameter is required", None, 400)
        user_doc = db.users.find_one({"userId": user_id}, {"_id": 0, "passwordHash": 0})
        if not user_doc:
            return format_response(False, "User not found", None, 404)
        # Format datetime fields as GMT string if available.
        for field in ["createdAt", "updatedAt"]:
            if field in user_doc and user_doc[field]:
                try:
                    user_doc[field] = user_doc[field].strftime("%a, %d %b %Y %H:%M:%S GMT")
                except Exception:
                    pass
        return format_response(True, "User retrieved successfully", user_doc, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@user_bp.route("/delete", methods=["POST"])
def delete_user():
    try:
        data = request.json or {}
        user_id = data.get("userId")
        if not user_id:
            return format_response(False, "userId is required in the body", None, 400)
        result = db.users.delete_one({"userId": user_id})
        if result.deleted_count == 0:
            return format_response(False, "User not found", None, 404)
        return format_response(True, "User deleted successfully", None, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@user_bp.route("/referrals", methods=["GET"])
def get_referrals():
    try:
        user_id = request.args.get("userId")
        if not user_id:
            return format_response(False, "userId query param required", None, 400)
        referrer = db.users.find_one({"userId": user_id})
        if not referrer:
            return format_response(False, "User not found", None, 404)
        referral_code = referrer.get("referralCode")
        if not referral_code:
            return format_response(False, "User does not have a referral code", None, 404)
        referred_users = list(db.users.find(
            {"referredBy": referral_code},
            {"_id": 0, "passwordHash": 0}
        ))
        return format_response(True, "Referral details retrieved successfully", {
            "referralCode": referral_code,
            "referralCount": len(referred_users),
            "referredUsers": referred_users
        }, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@user_bp.route("/dummy", methods=["POST"])
def dummy_login():
    try:
        data = request.get_json() or {}
        email = data.get("email", "")
        phone = data.get("phone", "")
        if not email and not phone:
            return format_response(False, "Either email or phone is required", None, 400)

        if email:
            # Case-insensitive email search.
            query = {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
        else:
            query = {"phone": phone}

        user_doc = db.users.find_one(query, {
            "_id": 0,
            "passwordHash": 0,
            "referralCode": 0
        })
        if not user_doc:
            return format_response(False, "User not found", None, 404)
        return format_response(True, "Dummy login successful", {"user": user_doc}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@user_bp.route("/update", methods=["POST"])
def update_user_details():
    try:
        data = request.get_json() or {}
        user_id = data.get("userId")
        if not user_id:
            return format_response(False, "userId is required", None, 400)

        update_fields = {}

        if "name" in data:
            if not is_valid_name(data["name"]):
                return format_response(False, "Invalid name (max 50 chars).", None, 400)
            update_fields["name"] = data["name"].strip()

        if "email" in data:
            email = data["email"].strip()
            if not is_valid_email(email):
                return format_response(False, "Invalid email format or length (5-100 chars).", None, 400)
            # Case-insensitive search for duplicate email.
            existing_email = db.users.find_one({
                "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"},
                "userId": {"$ne": user_id}
            })
            if existing_email:
                return format_response(False, "Email is already used by another account.", None, 400)
            update_fields["email"] = email

        if "phone" in data:
            current_user = db.users.find_one({"userId": user_id})
            current_phone = current_user.get("phone", "").strip() if current_user else ""
            new_phone = data["phone"].strip()
            if new_phone != current_phone:
                return format_response(False, "Phone number cannot be updated.", None, 400)

        if "dob" in data:
            try:
                dob_parsed = datetime.datetime.strptime(data["dob"], "%Y-%m-%d").date().isoformat()
            except ValueError:
                return format_response(False, "Invalid date of birth format (YYYY-MM-DD required).", None, 400)
            update_fields["dob"] = dob_parsed

        if "stateId" in data or "cityId" in data:
            if not ("stateId" in data and "cityId" in data):
                return format_response(False, "Both stateId and cityId are required to update location.", None, 400)
            state_id = data["stateId"].strip()
            city_id = data["cityId"].strip()
            if not state_id or not city_id:
                return format_response(False, "Both stateId and cityId must be non-empty.", None, 400)
            state_doc = db.india_states.find_one({"stateId": state_id})
            if not state_doc:
                return format_response(False, "Invalid stateId.", None, 400)
            city_obj = None
            for city in state_doc.get("cities", []):
                if city.get("cityId") == city_id:
                    city_obj = city
                    break
            if not city_obj:
                return format_response(False, "Invalid cityId for the given stateId.", None, 400)
            update_fields["stateId"] = state_id
            update_fields["stateName"] = state_doc.get("name")
            update_fields["cityId"] = city_id
            update_fields["cityName"] = city_obj.get("name")

        if not update_fields:
            return format_response(False, "No valid fields to update.", None, 400)

        update_fields["updatedAt"] = datetime.datetime.utcnow()
        result = db.users.update_one({"userId": user_id}, {"$set": update_fields})
        if result.matched_count == 0:
            return format_response(False, "User not found.", None, 404)
        return format_response(True, "User details updated.", None, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)