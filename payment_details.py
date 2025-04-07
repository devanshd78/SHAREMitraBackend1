# payment_details.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import re
import requests
from bson import ObjectId

# Import the db from your db.py
from db import db

payment_details_bp = Blueprint("payment_details", __name__,url_prefix="/payment")

def validate_ifsc(ifsc_code: str):
    """
    Validate the IFSC code format and check whether it exists using the Razorpay IFSC API.
    The expected format is 11 characters: first 4 alphabets, followed by '0',
    and then 6 alphanumeric characters.
    
    Returns:
      (bool, dict or str): A tuple where:
         - first element is True if the IFSC code is valid (False otherwise),
         - second element is either the bank info (dict) if valid or an error message (str) if invalid.
    """
    pattern = r'^[A-Za-z]{4}0[A-Za-z0-9]{6}$'
    if not re.match(pattern, ifsc_code):
        return False, "IFSC code does not match the expected format (e.g., SBIN0005943)."
    
    try:
        response = requests.get(f"https://ifsc.razorpay.com/{ifsc_code}")
        if response.status_code == 200:
            data = response.json()
            return True, data  # data contains bank, branch, address, etc.
        else:
            return False, "IFSC code not found or invalid."
    except Exception as e:
        return False, f"Error while validating IFSC code: {str(e)}"

@payment_details_bp.route("/payment-details", methods=["POST"])
def payment_details():
    """
    POST /payment-details
    Creates or updates the user's payment details (bank or UPI).
    If an existing payment for the same user + method is found, it updates it;
    otherwise, it creates a new entry.

    Request Body (JSON):
      Bank Example:
      {
        "userId": "67e7a14d65d938a816d1c4f9",
        "paymentMethod": "bank",
        "accountHolder": "John Doe",
        "accountNumber": "1234567890",
        "ifsc": "SBIN0005943",
        "bankName": "State Bank of India"
      }

      UPI Example:
      {
        "userId": "67e7a14d65d938a816d1c4f9",
        "paymentMethod": "upi",
        "upiId": "john@oksbi"
      }
    """
    data = request.get_json() or {}
    payment_method = data.get("paymentMethod")  # "bank" or "upi"
    user_id = data.get("userId")

    if not payment_method:
        return jsonify({"status": 0, "msg": "Payment method not provided"}), 400
    if not user_id:
        return jsonify({"status": 0, "msg": "User ID is required"}), 400

    # Map "bank" -> 1, "upi" -> 0
    if payment_method == "bank":
        method_code = 1
    elif payment_method == "upi":
        method_code = 0
    else:
        return jsonify({"status": 0, "msg": "Invalid payment method"}), 400

    # Check if payment details already exist for user + paymentMethod
    existing_payment = db.payment.find_one({
        "userId": user_id,
        "paymentMethod": method_code
    })

    # Common fields for updating or inserting
    document = {
        "userId": user_id,
        "paymentMethod": method_code,
        "updated_at": datetime.utcnow()
    }

    # If payment method == bank, validate bank fields
    if payment_method == "bank":
        account_holder = data.get("accountHolder")
        account_number = data.get("accountNumber")
        ifsc = data.get("ifsc")
        bank_name = data.get("bankName")

        if not (account_holder and account_number and ifsc and bank_name):
            return jsonify({"status": 0, "msg": "Incomplete bank details"}), 400

        valid, bank_info = validate_ifsc(ifsc)
        if not valid:
            return jsonify({"status": 404, "msg": "Invalid IFSC code"}), 404

        document.update({
            "accountHolder": account_holder,
            "accountNumber": account_number,
            "ifsc": ifsc,
            "bankName": bank_name,
            "ifscDetails": bank_info
        })

    # If payment method == upi, validate UPI fields
    elif payment_method == "upi":
        upi_id = data.get("upiId")
        if not upi_id:
            return jsonify({"status": 0, "msg": "UPI ID not provided"}), 400

        document["upiId"] = upi_id

    # If record exists, update it. Otherwise, create a new one.
    if existing_payment:
        result = db.payment.update_one(
            {"_id": existing_payment["_id"]},
            {"$set": document}
        )
        if result.modified_count > 0:
            return jsonify({"status": 200, "msg": "Payment details updated successfully"}), 200
        else:
            return jsonify({"status": 200, "msg": "No changes detected in payment details"}), 200
    else:
        # Insert new
        document["paymentId"] = str(ObjectId())
        document["created_at"] = datetime.utcnow()

        result = db.payment.insert_one(document)
        if result.inserted_id:
            return jsonify({"status": 200, "msg": "Payment details saved successfully"}), 200
        else:
            return jsonify({"status": 500, "msg": "Failed to save payment details"}), 500

@payment_details_bp.route("/userdetail", methods=["POST"])
def get_payment_details_by_user():
    """
    POST /payment-details/user
    Fetches all payment details for a given userId.
    Expected JSON input:
      {
        "userId": "67e7a14d65d938a816d1c4f9"
      }
    If no records are found, returns an empty list with a 200 status code.
    """
    data = request.get_json() or {}
    user_id = data.get("userId", "").strip()

    if not user_id:
        return jsonify({"status": 0, "msg": "User ID is required"}), 400

    payments = list(db.payment.find({"userId": user_id}))

    # Convert _id and date fields to strings for each payment record
    for payment in payments:
        payment["_id"] = str(payment["_id"])
        if "created_at" in payment and isinstance(payment["created_at"], datetime):
            payment["created_at"] = payment["created_at"].isoformat()
        if "updated_at" in payment and isinstance(payment["updated_at"], datetime):
            payment["updated_at"] = payment["updated_at"].isoformat()

    return jsonify({
        "status": 200,
        "msg": "Payment details retrieved successfully",
        "payments": payments  # Will be an empty list if no records exist
    }), 200
    
@payment_details_bp.route("/delete", methods=["POST"])
def delete_payment_detail():
    """
    POST /delete-payment
    Deletes a particular payment detail record.
    
    Expected Request Body (JSON):
    {
      "userId": "67e7a14d65d938a816d1c4f9",
      "paymentId": "payment id string"
    }
    """
    data = request.get_json() or {}
    user_id = data.get("userId")
    payment_id = data.get("paymentId")

    if not user_id or not payment_id:
        return jsonify({"status": 0, "msg": "User ID and Payment ID are required"}), 400

    # Verify if the payment record exists and belongs to the given user
    payment = db.payment.find_one({"paymentId": payment_id, "userId": user_id})
    if not payment:
        return jsonify({"status": 404, "msg": "Payment detail not found for this user"}), 404

    result = db.payment.delete_one({"_id": payment["_id"]})
    if result.deleted_count:
        return jsonify({"status": 200, "msg": "Payment detail deleted successfully"}), 200
    else:
        return jsonify({"status": 500, "msg": "Failed to delete payment detail"}), 500