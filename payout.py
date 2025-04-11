import os
import datetime
import requests
from requests.auth import HTTPBasicAuth
from flask import Blueprint, request, jsonify
from db import db
from dotenv import load_dotenv
from utils import format_response  # Centralized response formatter
import logging

# Configure logging.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

def razorpay_get(endpoint):
    url = f"{RAZORPAY_BASE_URL}/{endpoint}"
    response = requests.get(url, auth=HTTPBasicAuth(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
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
    try:
        data = request.get_json() or {}
        user_id = data.get("userId")
        amount = data.get("amount")  # in rupees
        payment_type = data.get("paymentType")  # 0 for UPI, 1 for bank

        if not user_id or not amount or payment_type is None:
            return format_response(False, "userId, amount and paymentType are required", None, 400)

        user = db.users.find_one({"userId": user_id})
        if not user:
            return format_response(False, "User not found", None, 404)

        # Check wallet balance.
        wallet = db.wallet.find_one({"userId": user_id})
        if not wallet:
            return format_response(False, "Wallet not found for user", None, 404)
        if wallet.get("balance", 0) < float(amount):
            return format_response(False, "Insufficient wallet balance", None, 400)

        # Determine payment method.
        if payment_type == 1:
            payment = db.payment.find_one({"userId": user_id, "paymentMethod": 1})
            fund_account_type = "bank_account"
        elif payment_type == 0:
            payment = db.payment.find_one({"userId": user_id, "paymentMethod": 0})
            fund_account_type = "vpa"
        else:
            return format_response(False, "Invalid paymentType. Use 0 for UPI or 1 for Bank", None, 400)

        if not payment:
            return format_response(False, "No payment method found for selected type.", None, 400)

        # Step 1: Create Razorpay Contact if missing.
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
                logger.exception("Failed to create Razorpay contact:")
                details = e.response.json() if e.response else str(e)
                return format_response(False, "Failed to create contact", {"details": details}, 500)

        # Step 2: Create or fetch Fund Account.
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
                    {"$set": {
                        fund_account_id_key: fund_account_id,
                        fund_account_type_key: fund_account_type
                    }}
                )
                logger.info("Fund account created: %s", fund_account_id)
            except requests.HTTPError as e:
                logger.exception("Failed to create fund account:")
                details = e.response.json() if e.response else str(e)
                return format_response(False, "Failed to create fund account. Please add valid bank or UPI.", {"details": details}, 500)
        else:
            logger.info("Fund account fetched from DB: %s", fund_account_id)

        if not RAZORPAYX_ACCOUNT_NO:
            return format_response(False, "Missing RazorpayX account number in config", None, 500)

        payout_payload = {
            "account_number": RAZORPAYX_ACCOUNT_NO,
            "fund_account_id": fund_account_id,
            "amount": int(amount) * 100,  # rupees to paise
            "currency": "INR",
            "mode": "IMPS" if fund_account_type == "bank_account" else "UPI",
            "purpose": "payout",
            "queue_if_low_balance": True,
            "reference_id": f"pay_{user_id[-6:]}_{int(datetime.datetime.utcnow().timestamp())}",
            "narration": "User Withdrawal"
        }
        try:
            payout = razorpay_post("payouts", payout_payload)
        except requests.HTTPError as e:
            details = e.response.json() if e.response else str(e)
            logger.exception("Payout failed:")
            return format_response(False, "Payout failed", {"details": details}, 500)

        # Save payout record to DB.
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

        # Update wallet: subtract withdrawn amount and increment withdrawn field.
        db.wallet.update_one(
            {"userId": user_id},
            {
                "$inc": {"balance": -float(amount), "withdrawn": float(amount)},
                "$set": {"updatedAt": datetime.datetime.utcnow()}
            }
        )
        updated_wallet = db.wallet.find_one({"userId": user_id}, {"_id": 0})

        return format_response(True, "Payout successful", {
            "payout_id": payout["id"],
            "amount": payout["amount"] / 100,
            "status_detail": payout["status"],
            "debug_info": {
                "fund_account_id": fund_account_id,
                "fund_account_type": fund_account_type,
                "fund_account_status": fund_account_status
            },
            "remaining_wallet_balance": updated_wallet.get("balance", 0)
        }, 200)

    except Exception as e:
        logger.exception("Unexpected error in withdraw_funds:")
        return format_response(False, f"Server error: {str(e)}", None, 500)

@payout_bp.route("/status", methods=["GET"])
def get_all_payouts_status():
    try:
        user_id = request.args.get("userId")
        if not user_id:
            return format_response(False, "userId is required", None, 400)

        payouts = list(db.payouts.find({"userId": user_id}).sort("created_at", -1))

        total_amount = 0
        result = []
        for payout in payouts:
            # Fetch updated status from Razorpay.
            try:
                updated_info = razorpay_get(f"payouts/{payout['payout_id']}")
                new_status = updated_info.get("status", "")
                if new_status and new_status.lower() != payout.get("status_detail", "").lower():
                    db.payouts.update_one(
                        {"payout_id": payout["payout_id"]},
                        {"$set": {"status_detail": new_status}}
                    )
                    payout["status_detail"] = new_status
            except Exception as ex:
                logger.warning("Failed to update status for payout %s: %s", payout['payout_id'], str(ex))

            total_amount += payout.get("amount", 0)
            mode = "Bank" if payout.get("fund_account_type") == "bank_account" else "UPI"
            result.append({
                "payout_id": payout.get("payout_id"),
                "amount": payout.get("amount", 0),
                "withdraw_time": payout.get("created_at"),
                "mode": mode,
                "status": map_status(payout.get("status_detail", ""))
            })

        return format_response(True, "Payout statuses retrieved successfully", {
            "userId": user_id,
            "total_payouts": len(result),
            "total_payout_amount": total_amount,
            "payouts": result
        }, 200)
    except Exception as e:
        logger.exception("Error in get_all_payouts_status:")
        return format_response(False, f"Server error: {str(e)}", None, 500)

@payout_bp.route("/history", methods=["POST"])
def get_payout_history():
    try:
        data = request.get_json() or {}
        try:
            page = int(data.get("page", 0))
        except ValueError:
            return format_response(False, "Page must be an integer.", None, 400)
        try:
            per_page = int(data.get("per_page", 10))
        except ValueError:
            return format_response(False, "per_page must be an integer.", None, 400)

        searchquery = data.get("searchquery", "").strip()
        filter_query = {}
        if searchquery:
            matching_users = list(db.users.find(
                {"$or": [
                    {"userId": {"$regex": searchquery, "$options": "i"}},
                    {"name": {"$regex": searchquery, "$options": "i"}}
                ]},
                {"userId": 1}
            ))
            user_ids = [user["userId"] for user in matching_users]
            if not user_ids:
                return format_response(True, "No matching records found.", {
                    "total": 0, "page": page, "per_page": per_page, "total_payout_amount": 0, "payouts": []
                }, 200)
            filter_query["userId"] = {"$in": user_ids}

        total = db.payouts.count_documents(filter_query)
        agg = list(db.payouts.aggregate([
            {"$match": filter_query},
            {"$group": {"_id": None, "total_amount": {"$sum": "$amount"}}}
        ]))
        total_amount = agg[0]["total_amount"] if agg else 0

        payouts_cursor = db.payouts.find(filter_query, {"_id": 0}).sort("created_at", -1)\
            .skip(page * per_page).limit(per_page)
        payouts_list = list(payouts_cursor)

        result = []
        for payout in payouts_list:
            try:
                updated_info = razorpay_get(f"payouts/{payout['payout_id']}")
                new_status = updated_info.get("status", "")
                if new_status and new_status.lower() != payout.get("status_detail", "").lower():
                    db.payouts.update_one(
                        {"payout_id": payout["payout_id"]},
                        {"$set": {"status_detail": new_status}}
                    )
                    payout["status_detail"] = new_status
            except Exception as ex:
                logger.warning("Failed to update status for payout %s: %s", payout['payout_id'], str(ex))
            mode = "Bank" if payout.get("fund_account_type") == "bank_account" else "UPI"
            user = db.users.find_one({"userId": payout.get("userId")}, {"name": 1})
            name = user.get("name") if user else ""
            result.append({
                "payout_id": payout.get("payout_id"),
                "userId": payout.get("userId"),
                "name": name,
                "amount": payout.get("amount", 0),
                "withdraw_time": payout.get("created_at"),
                "mode": mode,
                "status": map_status(payout.get("status_detail", ""))
            })

        return format_response(True, "Payout history retrieved successfully", {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_payout_amount": total_amount,
            "payouts": result
        }, 200)
    except Exception as e:
        logger.exception("Error in get_payout_history:")
        return format_response(False, f"Server error: {str(e)}", None, 500)