from flask import Blueprint, request
import datetime
from db import db  # Adjust this import based on your project's structure
from utils import format_response  # Centralized response formatter

wallet_bp = Blueprint("wallet", __name__, url_prefix="/wallet")

def update_wallet_after_task(user_id: str, task_id: str, price: float):
    """
    Update the user's wallet after completing a task.
    It increments the total earning and balance by the given task price and appends the task details.
    If no wallet exists for the given user_id, it returns an error.
    """
    try:
        wallet = db.wallet.find_one({"userId": user_id})
        if not wallet:
            return {"error": "Invalid user. Wallet not found."}
        
        db.wallet.update_one(
            {"userId": user_id},
            {
                "$inc": {"total_earning": price, "balance": price},
                "$push": {"tasks": {"taskId": task_id, "price": price}},
                "$set": {"updatedAt": datetime.datetime.utcnow()}
            }
        )
        return {"message": "Wallet updated successfully."}
    except Exception as e:
        return {"error": f"Server error: {str(e)}"}

@wallet_bp.route("/info", methods=["GET"])
def get_wallet_info():
    """
    GET /wallet/info?userId=<user_id>

    Returns wallet details including:
      - userId
      - total number of tasks done (calculated from the tasks array)
      - tasks list (each with taskId and price)
      - total_earning (sum of incomes from tasks)
      - withdrawn (total withdrawal amount)
      - remaining_balance (current balance)
    """
    try:
        user_id = request.args.get("userId", "").strip()
        if not user_id:
            return format_response(False, "userId is required", None, 400)

        wallet = db.wallet.find_one({"userId": user_id}, {"_id": 0})
        if not wallet:
            return format_response(False, "Wallet not found", None, 404)

        wallet["no_of_tasks_done"] = len(wallet.get("tasks", []))
        wallet["remaining_balance"] = wallet.get("balance", 0)
        return format_response(True, "Wallet info retrieved successfully", wallet, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)