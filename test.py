from flask import Flask, request, jsonify,Blueprint
import requests
import os
from dotenv import load_dotenv

load_dotenv()
otp_bp = Blueprint("test", __name__, url_prefix="/otp")


# Firebase API key from your Firebase project.
FIREBASE_API_KEY = "AIzaSyDCShl2sjOegtX0UCgwinJlJdLS1VPv1us"

@otp_bp.route('/sendOTP', methods=['POST'])
def send_otp():
    """
    POST /sendOTP
    Request JSON Body:
    {
      "phoneNumber": "+15555551234",
      "recaptchaToken": "RECAPTCHA_TOKEN"
    }
    
    This endpoint calls Firebase to send an OTP to the given phone number.
    On success, it returns a "sessionInfo" token.
    """
    data = request.get_json()
    phone_number = data.get("phoneNumber")
    recaptcha_token = data.get("recaptchaToken")
    
    if not phone_number or not recaptcha_token:
        return jsonify({"error": "phoneNumber and recaptchaToken are required"}), 400

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendVerificationCode?key={FIREBASE_API_KEY}"
    payload = {
        "phoneNumber": phone_number,
        "recaptchaToken": recaptcha_token
    }
    
    resp = requests.post(url, json=payload)
    
    if resp.status_code == 200:
        res_data = resp.json()
        # sessionInfo token is required for OTP verification
        return jsonify({"sessionInfo": res_data.get("sessionInfo")}), 200
    else:
        return jsonify({"error": resp.json()}), resp.status_code


@otp_bp.route('/verifyOTP', methods=['POST'])
def verify_otp():
    """
    POST /verifyOTP
    Request JSON Body:
    {
      "sessionInfo": "SESSION_INFO_FROM_SEND",
      "code": "OTP_CODE_ENTERED_BY_USER"
    }
    
    This endpoint verifies the OTP with Firebase.
    On success, it returns a message "Verified successfully" along with details such as idToken.
    """
    data = request.get_json()
    session_info = data.get("sessionInfo")
    code = data.get("code")
    
    if not session_info or not code:
        return jsonify({"error": "sessionInfo and code are required"}), 400

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPhoneNumber?key={FIREBASE_API_KEY}"
    payload = {
        "sessionInfo": session_info,
        "code": code
    }
    
    resp = requests.post(url, json=payload)
    
    if resp.status_code == 200:
        res_data = resp.json()
        # The response contains idToken, phoneNumber, etc.
        return jsonify({
            "message": "Verified successfully",
            "data": res_data
        }), 200
    else:
        return jsonify({"error": resp.json()}), resp.status_code

