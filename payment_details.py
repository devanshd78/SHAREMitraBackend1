from flask import Blueprint, request
from datetime import datetime
import re
import requests
from bson import ObjectId
from db import db
from utils import format_response  # Centralized response formatter

payment_details_bp = Blueprint("payment", __name__, url_prefix="/payment")

def validate_ifsc(ifsc_code: str):
    """
    Validate the IFSC code format and check whether it exists using the Razorpay IFSC API.
    Expected format: 11 characters — first 4 alphabets, followed by '0', then 6 alphanumeric characters.
    
    Returns:
      (bool, dict or str): Tuple where:
         - True if the IFSC code is valid; False otherwise.
         - Second element is bank info (dict) if valid or an error message (str) if invalid.
    """
    pattern = r'^[A-Za-z]{4}0[A-Za-z0-9]{6}$'
    if not re.match(pattern, ifsc_code):
        return False, "IFSC code does not match the expected format (e.g., SBIN0005943)."
    
    try:
        response = requests.get(f"https://ifsc.razorpay.com/{ifsc_code}")
        if response.status_code == 200:
            data = response.json()
            return True, data  # Contains bank, branch, address, etc.
        else:
            return False, "IFSC code not found or invalid."
    except Exception as e:
        return False, f"Error while validating IFSC code: {str(e)}"

@payment_details_bp.route("/create", methods=["POST"])
def payment_details():
    """
    POST /payment-details
    Creates or updates the user's payment details (bank or UPI).
    
    Request Body Examples:
    
      Bank:
      {
        "userId": "67e7a14d65d938a816d1c4f9",
        "paymentMethod": "bank",
        "accountHolder": "John Doe",
        "accountNumber": "1234567890",
        "ifsc": "SBIN0005943",
        "bankName": "State Bank of India"
      }
      
      UPI:
      {
        "userId": "67e7a14d65d938a816d1c4f9",
        "paymentMethod": "upi",
        "upiId": "john@oksbi"
      }
    """
    try:
        data = request.get_json() or {}
        payment_method = data.get("paymentMethod")
        user_id = data.get("userId")

        if not payment_method:
            return format_response(False, "Payment method not provided", None, 400)
        if not user_id:
            return format_response(False, "User ID is required", None, 400)

        # Map payment method to code: bank -> 1, upi -> 0.
        if payment_method == "bank":
            method_code = 1
        elif payment_method == "upi":
            method_code = 0
        else:
            return format_response(False, "Invalid payment method", None, 400)

        # Check if payment details already exist for user & method.
        existing_payment = db.payment.find_one({
            "userId": user_id,
            "paymentMethod": method_code
        })

        # Common fields for both updating and inserting.
        document = {
            "userId": user_id,
            "paymentMethod": method_code,
            "updated_at": datetime.utcnow()
        }

        if payment_method == "bank":
            account_holder = data.get("accountHolder")
            account_number = data.get("accountNumber")
            ifsc = data.get("ifsc")
            bank_name = data.get("bankName")
            
            if not (account_holder and account_number and ifsc and bank_name):
                return format_response(False, "Incomplete bank details", None, 400)

            valid, bank_info = validate_ifsc(ifsc)
            if not valid:
                return format_response(False, "Invalid IFSC code", None, 404)

            document.update({
                "accountHolder": account_holder,
                "accountNumber": account_number,
                "ifsc": ifsc,
                "bankName": bank_name,
                "ifscDetails": bank_info
            })

        elif payment_method == "upi":
            upi_id = data.get("upiId")
            if not upi_id:
                return format_response(False, "UPI ID not provided", None, 400)
            document["upiId"] = upi_id

        # Update existing record or insert new one.
        if existing_payment:
            result = db.payment.update_one(
                {"_id": existing_payment["_id"]},
                {"$set": document}
            )
            if result.modified_count > 0:
                return format_response(True, "Payment details updated successfully", None, 200)
            else:
                return format_response(True, "No changes detected in payment details", None, 200)
        else:
            document["paymentId"] = str(ObjectId())
            document["created_at"] = datetime.utcnow()
            result = db.payment.insert_one(document)
            if result.inserted_id:
                return format_response(True, "Payment details saved successfully", None, 200)
            else:
                return format_response(False, "Failed to save payment details", None, 500)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@payment_details_bp.route("/userdetail", methods=["POST"])
def get_payment_details_by_user():
    """
    POST /payment-details/userdetail
    Fetches all payment details for a given userId.
    
    Expected JSON:
    {
      "userId": "67e7a14d65d938a816d1c4f9"
    }
    
    If no records are found, returns an empty list.
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("userId", "").strip()
        if not user_id:
            return format_response(False, "User ID is required", None, 400)

        payments = list(db.payment.find({"userId": user_id}))
        for payment in payments:
            payment["_id"] = str(payment["_id"])
            if "created_at" in payment and isinstance(payment["created_at"], datetime):
                payment["created_at"] = payment["created_at"].isoformat()
            if "updated_at" in payment and isinstance(payment["updated_at"], datetime):
                payment["updated_at"] = payment["updated_at"].isoformat()

        return format_response(True, "Payment details retrieved successfully", {"payments": payments}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@payment_details_bp.route("/delete", methods=["POST"])
def delete_payment_detail():
    """
    POST /payment-details/delete
    Deletes a particular payment detail record.
    
    Expected JSON:
    {
      "userId": "67e7a14d65d938a816d1c4f9",
      "paymentId": "payment id string"
    }
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("userId")
        payment_id = data.get("paymentId")

        if not user_id or not payment_id:
            return format_response(False, "User ID and Payment ID are required", None, 400)

        # Verify record exists and belongs to the user.
        payment = db.payment.find_one({"paymentId": payment_id, "userId": user_id})
        if not payment:
            return format_response(False, "Payment detail not found for this user", None, 404)

        result = db.payment.delete_one({"_id": payment["_id"]})
        if result.deleted_count:
            return format_response(True, "Payment detail deleted successfully", None, 200)
        else:
            return format_response(False, "Failed to delete payment detail", None, 500)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)