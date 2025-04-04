from flask import Blueprint, request, jsonify
import requests
from requests.auth import HTTPBasicAuth
from db import db
import datetime
import os
from dotenv import load_dotenv

payout_bp = Blueprint("payout", __name__, url_prefix="/payout")
load_dotenv()

RAZORPAY_BASE_URL = 'https://api.razorpay.com/v1'
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAYX_ACCOUNT_NO = os.getenv("RAZORPAYX_ACCOUNT_NO")


def razorpay_post(endpoint, data):
    url = f"{RAZORPAY_BASE_URL}/{endpoint}"
    response = requests.post(url, json=data, auth=HTTPBasicAuth(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    response.raise_for_status()
    return response.json()

def map_status(status_raw):
    status_raw = status_raw.lower()
    if status_raw in ["processing"]:
        return "Processing"
    elif status_raw in ["failed", "rejected", "cancelled"]:
        return "Declined"
    elif status_raw in ["queued", "pending", "on-hold", "scheduled"]:
        return "Pending"
    elif status_raw in ["processed"]:
        return "Processed"
    else:
        return status_raw.capitalize()

@payout_bp.route("/withdraw", methods=["POST"])
def withdraw_funds():
    data = request.get_json()
    user_id = data.get("userId")
    amount = data.get("amount")  # in rupees
    payment_type = data.get("paymentType")  # 0 for UPI, 1 for bank

    if not user_id or not amount or payment_type is None:
        return jsonify({"error": "userId, amount and paymentType are required"}), 400

    user = db.users.find_one({"userId": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Check wallet balance before processing withdrawal
    wallet = db.wallet.find_one({"userId": user_id})
    if not wallet:
        return jsonify({"error": "Wallet not found for user"}), 404
    if wallet.get("balance", 0) < float(amount):
        return jsonify({"error": "Insufficient wallet balance"}), 400

    if payment_type == 1:
        payment = db.payment.find_one({"userId": user_id, "paymentMethod": 1})
        fund_account_type = "bank_account"
    elif payment_type == 0:
        payment = db.payment.find_one({"userId": user_id, "paymentMethod": 0})
        fund_account_type = "vpa"
    else:
        return jsonify({"error": "Invalid paymentType. Use 0 for UPI or 1 for Bank"}), 400

    if not payment:
        return jsonify({"error": "No payment method found for selected type."}), 400

    # Step 1: Create Contact if missing
    contact_id = user.get("razorpay_contact_id")
    if not contact_id:
        contact_data = {
            "name": user["name"],
            "email": user["email"],
            "contact": user["phone"],
            "type": "employee"
        }
        try:
            contact = razorpay_post("contacts", contact_data)
            contact_id = contact['id']
            db.users.update_one(
                {"userId": user_id},
                {"$set": {"razorpay_contact_id": contact_id}}
            )
        except requests.HTTPError as e:
            return jsonify({
                "error": "Failed to create contact",
                "details": e.response.json() if e.response else str(e)
            }), 500

    # Step 2: Create Fund Account if missing
    fund_account_id_key = f"razorpay_fund_account_id_{payment_type}"
    fund_account_type_key = f"razorpay_fund_account_type_{payment_type}"

    fund_account_id = user.get(fund_account_id_key)
    fund_account_status = "fetched"

    if not fund_account_id:
        try:
            if payment_type == 1:
                fund_payload = {
                    "contact_id": contact_id,
                    "account_type": "bank_account",
                    "bank_account": {
                        "name": payment["accountHolder"],
                        "ifsc": payment["ifsc"],
                        "account_number": payment["accountNumber"]
                    }
                }
            else:
                fund_payload = {
                    "contact_id": contact_id,
                    "account_type": "vpa",
                    "vpa": {
                        "address": payment["upiId"]
                    }
                }

            fund_account = razorpay_post("fund_accounts", fund_payload)
            fund_account_id = fund_account["id"]
            fund_account_status = "created"

            db.users.update_one(
                {"userId": user_id},
                {
                    "$set": {
                        fund_account_id_key: fund_account_id,
                        fund_account_type_key: fund_account_type
                    }
                }
            )
            print(f"✅ Fund account created: {fund_account_id}")
        except requests.HTTPError as e:
            return jsonify({
                "error": "Failed to create fund account. Please add valid bank or UPI.",
                "details": e.response.json() if e.response else str(e)
            }), 500
    else:
        print(f"✅ Fund account fetched from DB: {fund_account_id}")

    if not RAZORPAYX_ACCOUNT_NO:
        return jsonify({"error": "Missing RazorpayX account number in config"}), 500

    payout_payload = {
        "account_number": RAZORPAYX_ACCOUNT_NO,
        "fund_account_id": fund_account_id,
        "amount": int(amount) * 100,  # converting rupees to paise
        "currency": "INR",
        "mode": "IMPS" if fund_account_type == "bank_account" else "UPI",
        "purpose": "payout",
        "queue_if_low_balance": True,
        "reference_id": f"pay_{user_id[-6:]}_{int(datetime.datetime.utcnow().timestamp())}",
        "narration": "User Withdrawal"
    }

    try:
        payout = razorpay_post("payouts", payout_payload)

        # Save payout to DB
        db.payouts.insert_one({
            "userId": user_id,
            "payout_id": payout["id"],
            "amount": payout["amount"] / 100,
            "status_detail": payout["status"],
            "fund_account_id": fund_account_id,
            "fund_account_status": fund_account_status,
            "fund_account_type": fund_account_type,
            "created_at": datetime.datetime.utcnow()
        })

        # Update wallet: subtract withdrawn amount and add to withdrawn field
        db.wallet.update_one(
            {"userId": user_id},
            {
                "$inc": {"balance": -float(amount), "withdrawn": float(amount)},
                "$set": {"updatedAt": datetime.datetime.utcnow()}
            }
        )
        updated_wallet = db.wallet.find_one({"userId": user_id}, {"_id": 0})

        return jsonify({
            "status": "success",
            "payout_id": payout["id"],
            "amount": payout["amount"] / 100,
            "status_detail": payout["status"],
            "debug_info": {
                "fund_account_id": fund_account_id,
                "fund_account_type": fund_account_type,
                "fund_account_status": fund_account_status
            },
            "remaining_wallet_balance": updated_wallet.get("balance", 0)
        }), 200

    except requests.HTTPError as e:
        error_response = None
        try:
            error_response = e.response.json()
        except Exception:
            error_response = e.response.text

        print("❌ Razorpay Error Response:", error_response)

        return jsonify({
            "error": "Payout failed",
            "details": error_response
        }), 500


@payout_bp.route("/status", methods=["GET"])
def get_all_payouts_status():
    user_id = request.args.get("userId")

    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    payouts = list(db.payouts.find({"userId": user_id}).sort("created_at", -1))

    if not payouts:
        return jsonify({"message": "No payouts found for this user"}), 404

    def map_status(status_raw):
        status_raw = status_raw.lower()
        if status_raw in ["processing"]:
            return "Processing"
        elif status_raw in ["failed", "rejected", "cancelled"]:
            return "Declined"
        elif status_raw in ["queued", "pending", "on-hold", "scheduled"]:
            return "Pending"
        elif status_raw in ["processed"]:
            return "Processed"
        else:
            return status_raw.capitalize()

    total_amount = 0
    result = []

    for payout in payouts:
        amount = payout.get("amount", 0)
        total_amount += amount

        mode = "Bank" if payout.get("fund_account_type") == "bank_account" else "UPI"

        result.append({
            "payout_id": payout.get("payout_id"),
            "amount": amount,
            "withdraw_time": payout.get("created_at"),
            "mode": mode,
            "status": map_status(payout.get("status_detail", ""))
        })

    return jsonify({
        "userId": user_id,
        "total_payouts": len(result),
        "total_payout_amount": total_amount,
        "payouts": result
    }), 200

@payout_bp.route("/history", methods=["POST"])
def get_payout_history():
    data = request.get_json() or {}
    try:
        page = int(data.get("page", 0))
    except ValueError:
        return jsonify({"error": "Page must be an integer."}), 400

    try:
        per_page = int(data.get("per_page", 10))
    except ValueError:
        return jsonify({"error": "per_page must be an integer."}), 400

    searchquery = data.get("searchquery", "").strip()

    # Build filter for payouts based on searchquery.
    # We'll search for matching userIds from the users collection if a query is provided.
    filter_query = {}
    if searchquery:
        # Find matching user IDs based on search in userId or name.
        matching_users = list(db.users.find(
            {"$or": [
                {"userId": {"$regex": searchquery, "$options": "i"}},
                {"name": {"$regex": searchquery, "$options": "i"}}
            ]},
            {"userId": 1}
        ))
        user_ids = [user["userId"] for user in matching_users]
        # If no matching users, return empty result.
        if not user_ids:
            return jsonify({
                "total": 0,
                "page": page,
                "per_page": per_page,
                "total_payout_amount": 0,
                "payouts": []
            }), 200
        filter_query["userId"] = {"$in": user_ids}

    # Get total count and total payout amount for the filtered results
    total = db.payouts.count_documents(filter_query)
    agg = list(db.payouts.aggregate([
        {"$match": filter_query},
        {"$group": {"_id": None, "total_amount": {"$sum": "$amount"}}}
    ]))
    total_amount = agg[0]["total_amount"] if agg else 0

    # Fetch paginated payouts sorted by created_at (descending)
    payouts_cursor = db.payouts.find(filter_query, {"_id": 0}).sort("created_at", -1)\
        .skip(page * per_page).limit(per_page)
    payouts_list = list(payouts_cursor)

    # For each payout, lookup user name
    result = []
    for payout in payouts_list:
        user = db.users.find_one({"userId": payout.get("userId")}, {"name": 1})
        name = user.get("name") if user else ""
        result.append({
            "payout_id": payout.get("payout_id"),
            "userId": payout.get("userId"),
            "name": name,
            "amount": payout.get("amount", 0),
            "withdraw_time": payout.get("created_at"),  # assuming created_at is used as withdraw_time
            "mode": "Bank" if payout.get("fund_account_type") == "bank_account" else "UPI",
            "status": map_status(payout.get("status_detail", ""))
        })

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_payout_amount": total_amount,
        "payouts": result
    }), 200