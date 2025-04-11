from flask import Blueprint, request
import datetime
from db import db  # Ensure this imports your configured PyMongo instance
from bson import ObjectId
from utils import format_response

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
    This helps in serializing MongoDB documents.
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

def aggregate_weekly(data, amount_key="amount", date_field="created_at"):
    """Aggregate data by week based on a given date field."""
    weekly = {}
    for record in data:
        record_date = record.get(date_field)
        if not record_date:
            continue
        # Compute week number for the day in the month.
        day = record_date.day
        week = ((day - 1) // 7) + 1
        if amount_key is not None:
            weekly[week] = weekly.get(week, 0) + record.get(amount_key, 0)
        else:
            weekly[week] = weekly.get(week, 0) + 1
    return [{"week": week, "total": weekly[week]} for week in sorted(weekly)]

def aggregate_daily(data, amount_key="amount", date_field="created_at"):
    """Aggregate data by day based on a given date field."""
    daily = {}
    for record in data:
        record_date = record.get(date_field)
        if not record_date:
            continue
        day_str = record_date.strftime("%Y-%m-%d")
        if amount_key is not None:
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
             • Dates cannot be in the future.
         - Graph data is aggregated weekly if range spans 7+ days; otherwise, daily.
    """
    try:
        data = request.get_json() or {}
        date_str = data.get("date")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        today = datetime.datetime.utcnow().date()

        # Validate parameters.
        if not date_str and not (start_date_str and end_date_str):
            return format_response(False, "Please provide either a single 'date' or both 'start_date' and 'end_date'.", None, 400)

        # Single Date Case.
        if date_str and not (start_date_str or end_date_str):
            dt = parse_date(date_str)
            if not dt:
                return format_response(False, "Invalid date format for 'date'. Use YYYY-MM-DD.", None, 400)
            if dt.date() > today:
                return format_response(False, "The provided date cannot be in the future.", None, 400)
            start = dt
            end = dt + datetime.timedelta(days=1)
            query = {"created_at": {"$gte": start, "$lt": end}}
            payouts = list(db.payouts.find(query))
            payouts = convert_objectids(payouts)
            total_expense = sum(item.get("amount", 0) for item in payouts)
            return format_response(True, "Expense data retrieved successfully.", {"total_expense": total_expense, "details": payouts}, 200)

        # Date Range Case.
        if start_date_str and end_date_str:
            start = parse_date(start_date_str)
            end = parse_date(end_date_str)
            if not start or not end:
                return format_response(False, "Invalid date format for range. Use YYYY-MM-DD.", None, 400)
            if start > end:
                return format_response(False, "start_date must be less than or equal to end_date.", None, 400)
            if start.date() > today or end.date() > today:
                return format_response(False, "Dates cannot be in the future.", None, 400)
            # Include the full end day.
            end = end + datetime.timedelta(days=1)
            query = {"created_at": {"$gte": start, "$lt": end}}
            payouts = list(db.payouts.find(query))
            payouts = convert_objectids(payouts)
            total_expense = sum(item.get("amount", 0) for item in payouts)
            # Use weekly aggregation for ranges spanning 7+ days.
            if (end - start).days >= 7:
                graph_data = aggregate_weekly(payouts, amount_key="amount", date_field="created_at")
            else:
                graph_data = aggregate_daily(payouts, amount_key="amount", date_field="created_at")
            return format_response(True, "Expense range data retrieved successfully.", {"total_expense": total_expense, "graph": graph_data}, 200)

        return format_response(False, "Invalid parameters.", None, 400)

    except Exception as e:
        return format_response(False, "Server error", {"message": str(e)}, 500)

# =================== User Registration Endpoint ===================

@dashboard_bp.route("/user", methods=["POST"])
def get_user_registrations():
    """
    POST /dash/user

    JSON body parameters (one of the following is required):

      1. Single Date Case:
         { "date": "YYYY-MM-DD" }
         - Returns the total number of users registered on that day.
         - The provided date must not be in the future.

      2. Date Range Case:
         { "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }
         - Returns total registrations for the range and graph data.
         - Enforces valid date order and dates not in the future.
         - Graph data is aggregated weekly for ranges spanning 7+ days; otherwise, daily.

      3. Default Case (no parameters):
         - Uses the current month's registration data.
         - Returns full user details (with sensitive fields excluded) and a weekly aggregated graph.
    """
    try:
        data = request.get_json() or {}
        date_str = data.get("date")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        today = datetime.datetime.utcnow().date()

        # Default Case: current month's data.
        if not date_str and not (start_date_str and end_date_str):
            start = datetime.datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = datetime.datetime.utcnow()
            query = {"createdAt": {"$gte": start, "$lt": end}}
            users = list(db.users.find(query, {"passwordHash": 0}))
            users = convert_objectids(users)
            total_registrations = len(users)
            graph_data = aggregate_weekly(users, amount_key=None, date_field="createdAt")
            return format_response(True, "Current month's user data retrieved.", {"total_registrations": total_registrations, "graph": graph_data}, 200)

        # Single Date Case.
        if date_str and not (start_date_str or end_date_str):
            dt = parse_date(date_str)
            if not dt:
                return format_response(False, "Invalid date format for 'date'. Use YYYY-MM-DD.", None, 400)
            if dt.date() > today:
                return format_response(False, "The provided date cannot be in the future.", None, 400)
            start = dt
            end = dt + datetime.timedelta(days=1)
            query = {"createdAt": {"$gte": start, "$lt": end}}
            users = list(db.users.find(query, {"passwordHash": 0}))
            users = convert_objectids(users)
            total_registrations = len(users)
            return format_response(True, "User registration data retrieved.", {"total_registrations": total_registrations}, 200)

        # Date Range Case.
        if start_date_str and end_date_str:
            start = parse_date(start_date_str)
            end = parse_date(end_date_str)
            if not start or not end:
                return format_response(False, "Invalid date format for range. Use YYYY-MM-DD.", None, 400)
            if start > end:
                return format_response(False, "start_date must be less than or equal to end_date.", None, 400)
            if start.date() > today or end.date() > today:
                return format_response(False, "Dates cannot be in the future.", None, 400)
            end = end + datetime.timedelta(days=1)
            query = {"createdAt": {"$gte": start, "$lt": end}}
            users = list(db.users.find(query, {"passwordHash": 0}))
            users = convert_objectids(users)
            total_registrations = len(users)
            if (end - start).days >= 7:
                graph_data = aggregate_weekly(users, amount_key=None, date_field="createdAt")
            else:
                graph_data = aggregate_daily(users, amount_key=None, date_field="createdAt")
            return format_response(True, "User registration range data retrieved.", {"total_registrations": total_registrations, "graph": graph_data}, 200)

        return format_response(False, "Invalid parameters.", None, 400)

    except Exception as e:
        return format_response(False, "Server error", {"message": str(e)}, 500)

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
         - Returns total completed tasks in that range and graph data.
         - Enforces valid date order and dates not in the future.
         - Graph data is aggregated weekly for ranges spanning 7+ days; otherwise, daily.
    """
    try:
        data = request.get_json() or {}
        date_str = data.get("date")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        today = datetime.datetime.utcnow().date()

        # Reuse the global parse_date function.
        if not date_str and not (start_date_str and end_date_str):
            return format_response(False, "Please provide either a single 'date' or both 'start_date' and 'end_date'.", None, 400)

        # Single Date Case.
        if date_str and not (start_date_str or end_date_str):
            dt = parse_date(date_str)
            if not dt:
                return format_response(False, "Invalid date format for 'date'. Use YYYY-MM-DD.", None, 400)
            if dt.date() > today:
                return format_response(False, "The provided date cannot be in the future.", None, 400)
            start = dt
            end = dt + datetime.timedelta(days=1)
            query = {"verifiedAt": {"$gte": start, "$lt": end}}
            tasks = list(db.task_history.find(query))
            tasks = convert_objectids(tasks)
            total_completed = len(tasks)
            return format_response(True, "Task completion data retrieved.", {"total_completed": total_completed}, 200)

        # Date Range Case.
        if start_date_str and end_date_str:
            start = parse_date(start_date_str)
            end = parse_date(end_date_str)
            if not start or not end:
                return format_response(False, "Invalid date format for range. Use YYYY-MM-DD.", None, 400)
            if start > end:
                return format_response(False, "start_date must be less than or equal to end_date.", None, 400)
            if start.date() > today or end.date() > today:
                return format_response(False, "Dates cannot be in the future.", None, 400)
            end = end + datetime.timedelta(days=1)
            query = {"verifiedAt": {"$gte": start, "$lt": end}}
            tasks = list(db.task_history.find(query))
            tasks = convert_objectids(tasks)
            total_completed = len(tasks)
            if (end - start).days >= 7:
                graph_data = aggregate_weekly(tasks, amount_key=None, date_field="verifiedAt")
            else:
                graph_data = aggregate_daily(tasks, amount_key=None, date_field="verifiedAt")
            return format_response(True, "Task completion range data retrieved.", {"total_completed": total_completed, "graph": graph_data}, 200)

        return format_response(False, "Invalid parameters.", None, 400)

    except Exception as e:
        return format_response(False, "Server error", {"message": str(e)}, 500)

# =================== Overview Endpoint ===================

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
        overview = {
            "total_users": total_users,
            "total_tasks": total_tasks,
            "total_expense": total_expense
        }
        return format_response(True, "Overview data retrieved successfully.", overview, 200)
    except Exception as e:
        return format_response(False, "Server error", {"message": str(e)}, 500)