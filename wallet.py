from flask import Blueprint, request, jsonify
import datetime
from db import db  # Adjust this import based on your project's structure

wallet_bp = Blueprint("wallet", __name__, url_prefix="/wallet")

def update_wallet_after_task(user_id: str, task_id: str, price: float):
    """
    Update the user's wallet after completing a task.
    It increments the total earning and balance by the given task price and appends the task details.
    If no wallet exists for the given user_id, it returns an error.
    """
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
    user_id = request.args.get("userId", "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    wallet = db.wallet.find_one({"userId": user_id}, {"_id": 0})
    if not wallet:
        return jsonify({"error": "Wallet not found"}), 404

    wallet["no_of_tasks_done"] = len(wallet.get("tasks", []))
    wallet["remaining_balance"] = wallet.get("balance", 0)
    return jsonify(wallet), 200