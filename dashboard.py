from flask import Blueprint, request, jsonify
import datetime
from db import db  # Ensure this imports your configured PyMongo instance
from bson import ObjectId

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dash")

def parse_date(date_str):
    """Parse a date string in YYYY-MM-DD format and return a datetime object."""
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None

def convert_objectids(data):
    """
    Recursively converts ObjectId instances in a dict or list to strings.
    This helps in serializing MongoDB documents using Flask's jsonify.
    """
    if isinstance(data, list):
        return [convert_objectids(item) for item in data]
    elif isinstance(data, dict):
        new_data = {}
        for key, value in data.items():
            if isinstance(value, ObjectId):
                new_data[key] = str(value)
            elif isinstance(value, (list, dict)):
                new_data[key] = convert_objectids(value)
            else:
                new_data[key] = value
        return new_data
    else:
        return data

def aggregate_weekly(data, amount_key="amount"):
    weekly = {}
    for record in data:
        # Try 'created_at' first, then 'createdAt'
        record_date = record.get("created_at") or record.get("createdAt")
        if not record_date:
            continue
        day = record_date.day
        week = ((day - 1) // 7) + 1
        if amount_key:
            weekly[week] = weekly.get(week, 0) + record.get(amount_key, 0)
        else:
            weekly[week] = weekly.get(week, 0) + 1
    return [{"week": week, "total": weekly[week]} for week in sorted(weekly)]

def aggregate_daily(data, amount_key="amount"):
    daily = {}
    for record in data:
        record_date = record.get("created_at") or record.get("createdAt")
        if not record_date:
            continue
        day_str = record_date.strftime("%Y-%m-%d")
        if amount_key:
            daily[day_str] = daily.get(day_str, 0) + record.get(amount_key, 0)
        else:
            daily[day_str] = daily.get(day_str, 0) + 1
    return [{"date": day, "total": daily[day]} for day in sorted(daily)]

# =================== Expense Endpoint ===================

@dashboard_bp.route("/expense", methods=["POST"])
def get_expense_dashboard():
    """
    POST /dash/expense

    JSON body parameters (one of the following is required):

      1. Single Date Case:
         { "date": "YYYY-MM-DD" }
         - Returns payout details and total expense for that day.
         - The provided date must not be in the future.

      2. Date Range Case:
         { "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }
         - Returns total expense for that range and graph data.
         - Enforces:
             • start_date ≤ end_date
             • Neither start_date nor end_date can be in the future.
         - Graph data is aggregated weekly if range spans 7+ days; otherwise, daily.
    """
    try:
        data = request.get_json() or {}
        date_str = data.get("date")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        today = datetime.datetime.utcnow().date()

        # Require one of the two parameter sets.
        if not date_str and not (start_date_str and end_date_str):
            return jsonify({"error": "Please provide either a single 'date' or both 'start_date' and 'end_date'."}), 400

        # Single Date Case.
        if date_str and not (start_date_str or end_date_str):
            dt = parse_date(date_str)
            if not dt:
                return jsonify({"error": "Invalid date format for 'date'. Use YYYY-MM-DD."}), 400
            if dt.date() > today:
                return jsonify({"error": "The provided date cannot be in the future."}), 400
            start = dt
            end = dt + datetime.timedelta(days=1)
            query = {"created_at": {"$gte": start, "$lt": end}}
            cursor = db.payouts.find(query)
            payouts = list(cursor)
            payouts = convert_objectids(payouts)
            total_expense = sum(item.get("amount", 0) for item in payouts)
            return jsonify({
                "total_expense": total_expense,
                "details": payouts
            }), 200

        # Date Range Case.
        if start_date_str and end_date_str:
            start = parse_date(start_date_str)
            end = parse_date(end_date_str)
            if not start or not end:
                return jsonify({"error": "Invalid date format for range. Use YYYY-MM-DD."}), 400
            if start > end:
                return jsonify({"error": "start_date must be less than or equal to end_date."}), 400
            if start.date() > today or end.date() > today:
                return jsonify({"error": "Dates cannot be in the future."}), 400
            # Include the full end day.
            end = end + datetime.timedelta(days=1)
            query = {"created_at": {"$gte": start, "$lt": end}}
            cursor = db.payouts.find(query)
            payouts = list(cursor)
            payouts = convert_objectids(payouts)
            total_expense = sum(item.get("amount", 0) for item in payouts)
            # Use weekly aggregation if range spans 7+ days; otherwise, daily.
            if (end - start).days >= 7:
                graph_data = aggregate_weekly(payouts, amount_key="amount")
            else:
                graph_data = aggregate_daily(payouts, amount_key="amount")
            return jsonify({
                "total_expense": total_expense,
                "graph": graph_data
            }), 200

        return jsonify({"error": "Invalid parameters."}), 400

    except Exception as e:
        return jsonify({"error": "Server error", "message": str(e)}), 500

# =================== User Registration Endpoint ===================

@dashboard_bp.route("/user", methods=["POST"])
def get_user_registrations():
    """
    POST /dash/user

    JSON body parameters (one of the following is required):

      1. Single Date Case:
         { "date": "YYYY-MM-DD" }
         - Returns total number of users registered on that day and user details.
         - The provided date must not be in the future.

      2. Date Range Case:
         { "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }
         - Returns total number of users registered in that range and graph data.
         - Enforces:
             • start_date ≤ end_date
             • Neither start_date nor end_date can be in the future.
         - Graph data is aggregated weekly if range spans 7+ days; otherwise, daily.

      3. Default Case (no parameters):
         - Uses the current month's registration data.
         - Returns full user details (sensitive fields excluded) and a weekly aggregated graph.
    """
    try:
        data = request.get_json() or {}
        date_str = data.get("date")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        today = datetime.datetime.utcnow().date()

        # Default Case: If no parameters, use current month's data.
        if not date_str and not (start_date_str and end_date_str):
            start = datetime.datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = datetime.datetime.utcnow()
            query = {"createdAt": {"$gte": start, "$lt": end}}
            cursor = db.users.find(query, {"passwordHash": 0})
            users = list(cursor)
            users = convert_objectids(users)
            total_registrations = len(users)
            graph_data = aggregate_weekly(users, amount_key=None)
            return jsonify({
                "total_registrations": total_registrations,
                "graph": graph_data
            }), 200

        # Single Date Case.
        if date_str and not (start_date_str or end_date_str):
            dt = parse_date(date_str)
            if not dt:
                return jsonify({"error": "Invalid date format for 'date'. Use YYYY-MM-DD."}), 400
            if dt.date() > today:
                return jsonify({"error": "The provided date cannot be in the future."}), 400
            start = dt
            end = dt + datetime.timedelta(days=1)
            query = {"createdAt": {"$gte": start, "$lt": end}}
            cursor = db.users.find(query, {"passwordHash": 0})
            users = list(cursor)
            users = convert_objectids(users)
            total_registrations = len(users)
            return jsonify({
                "total_registrations": total_registrations,
            }), 200

        # Date Range Case.
        if start_date_str and end_date_str:
            start = parse_date(start_date_str)
            end = parse_date(end_date_str)
            if not start or not end:
                return jsonify({"error": "Invalid date format for range. Use YYYY-MM-DD."}), 400
            if start > end:
                return jsonify({"error": "start_date must be less than or equal to end_date."}), 400
            if start.date() > today or end.date() > today:
                return jsonify({"error": "Dates cannot be in the future."}), 400
            # Include the full end day.
            end = end + datetime.timedelta(days=1)
            query = {"createdAt": {"$gte": start, "$lt": end}}
            cursor = db.users.find(query, {"passwordHash": 0})
            users = list(cursor)
            users = convert_objectids(users)
            total_registrations = len(users)
            if (end - start).days >= 7:
                graph_data = aggregate_weekly(users, amount_key=None)
            else:
                graph_data = aggregate_daily(users, amount_key=None)
            return jsonify({
                "total_registrations": total_registrations,
                "graph": graph_data
            }), 200

        return jsonify({"error": "Invalid parameters."}), 400

    except Exception as e:
        return jsonify({"error": "Server error", "message": str(e)}), 500

# =================== Task Completion Endpoint ===================

@dashboard_bp.route("/completion", methods=["POST"])
def get_task_completion():
    """
    POST /dash/completion

    JSON body parameters (one of the following is required):

      1. Single Date Case:
         { "date": "YYYY-MM-DD" }
         - Returns details and total number of tasks completed on that day.
         - The provided date must not be in the future.

      2. Date Range Case:
         { "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }
         - Returns total number of tasks completed in that range and graph data.
         - Enforces:
             • start_date ≤ end_date
             • Neither start_date nor end_date can be in the future.
         - Graph data is aggregated weekly if range spans 7+ days; otherwise, daily.
    """
    try:
        data = request.get_json() or {}
        date_str = data.get("date")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        today = datetime.datetime.utcnow().date()

        def parse_date_local(date_str):
            try:
                return datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                return None

        def convert_objectids_local(data):
            if isinstance(data, list):
                return [convert_objectids_local(item) for item in data]
            elif isinstance(data, dict):
                new_data = {}
                for key, value in data.items():
                    if isinstance(value, ObjectId):
                        new_data[key] = str(value)
                    elif isinstance(value, (list, dict)):
                        new_data[key] = convert_objectids_local(value)
                    else:
                        new_data[key] = value
                return new_data
            else:
                return data

        def aggregate_weekly_custom(data, date_field="verifiedAt"):
            weekly = {}
            for record in data:
                record_date = record.get(date_field)
                if not record_date:
                    continue
                day = record_date.day
                week = ((day - 1) // 7) + 1
                weekly[week] = weekly.get(week, 0) + 1
            return [{"week": week, "total": weekly[week]} for week in sorted(weekly)]

        def aggregate_daily_custom(data, date_field="verifiedAt"):
            daily = {}
            for record in data:
                record_date = record.get(date_field)
                if not record_date:
                    continue
                day_str = record_date.strftime("%Y-%m-%d")
                daily[day_str] = daily.get(day_str, 0) + 1
            return [{"date": day, "total": daily[day]} for day in sorted(daily)]

        # At least one parameter set must be provided.
        if not date_str and not (start_date_str and end_date_str):
            return jsonify({"error": "Please provide either a single 'date' or both 'start_date' and 'end_date'."}), 400

        # Single Date Case.
        if date_str and not (start_date_str or end_date_str):
            dt = parse_date_local(date_str)
            if not dt:
                return jsonify({"error": "Invalid date format for 'date'. Use YYYY-MM-DD."}), 400
            if dt.date() > today:
                return jsonify({"error": "The provided date cannot be in the future."}), 400
            start = dt
            end = dt + datetime.timedelta(days=1)
            query = {"verifiedAt": {"$gte": start, "$lt": end}}
            cursor = db.task_history.find(query)
            tasks = list(cursor)
            tasks = convert_objectids_local(tasks)
            total_completed = len(tasks)
            return jsonify({
                "total_completed": total_completed
            }), 200

        # Date Range Case
        if start_date_str and end_date_str:
            start = parse_date_local(start_date_str)
            end = parse_date_local(end_date_str)
            if not start or not end:
                return jsonify({"error": "Invalid date format for range. Use YYYY-MM-DD."}), 400
            if start > end:
                return jsonify({"error": "start_date must be less than or equal to end_date."}), 400
            if start.date() > today or end.date() > today:
                return jsonify({"error": "Dates cannot be in the future."}), 400
            # Include the entire end day
            end = end + datetime.timedelta(days=1)
            query = {"verifiedAt": {"$gte": start, "$lt": end}}
            cursor = db.task_history.find(query)
            tasks = list(cursor)
            tasks = convert_objectids_local(tasks)
            total_completed = len(tasks)

            if (end - start).days >= 7:
                graph_data = aggregate_weekly_custom(tasks, date_field="verifiedAt")
            else:
                graph_data = aggregate_daily_custom(tasks, date_field="verifiedAt")
            return jsonify({
                "total_completed": total_completed,
                "graph": graph_data
            }), 200

        return jsonify({"error": "Invalid parameters."}), 400

    except Exception as e:
        return jsonify({"error": "Server error", "message": str(e)}), 500


@dashboard_bp.route("/overview", methods=["GET"])
def get_simple_overview():
    """
    GET /dash/overview

    Returns a basic overview of:
    - total_users: total users in DB
    - total_tasks: total tasks in DB
    - total_expense: total amount from payouts collection
    """
    try:
        total_users = db.users.count_documents({})
        total_tasks = db.tasks.count_documents({})

        payouts = db.payouts.find({}, {"amount": 1})
        total_expense = sum(payout.get("amount", 0) for payout in payouts)

        return jsonify({
            "total_users": total_users,
            "total_tasks": total_tasks,
            "total_expense": total_expense
        }), 200

    except Exception as e:
        return jsonify({
            "error": "Server error",
            "message": str(e)
        }), 500
