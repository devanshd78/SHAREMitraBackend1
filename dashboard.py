from flask import Blueprint, jsonify
from pymongo import MongoClient
from datetime import datetime
from collections import defaultdict


dashboard_bp = Blueprint("dashboard", __name__)

client = MongoClient("mongodb://localhost:27017")
db = client['enoylity']


@dashboard_bp.route("/dashboard-stats", methods=["GET"])
def get_dashboard_stats():
    try:
        user_count = db.users.count_documents({})
        task_count = db.task.count_documents({})
        total_revenue = 12345  # Replace with actual logic if needed

        return jsonify({
            "status": 1,
            "users": user_count,
            "tasks": task_count,
            "revenue": total_revenue
        }), 200
    except Exception as e:
        return jsonify({"status": 0, "msg": str(e)}), 500


@dashboard_bp.route("/dashboard-chart", methods=["GET"])
def get_dashboard_chart():
    try:
        user_aggregation = db.users.aggregate([
            {"$group": {
                "_id": {"month": {"$month": "$created_at"}},
                "count": {"$sum": 1}
            }}
        ])

        user_counts = defaultdict(int)
        for doc in user_aggregation:
            user_counts[doc["_id"]["month"]] = doc["count"]

        task_aggregation = db.task.aggregate([
            {"$group": {
                "_id": {"month": {"$month": "$created_at"}},
                "count": {"$sum": 1}
            }}
        ])

        task_counts = defaultdict(int)
        for doc in task_aggregation:
            task_counts[doc["_id"]["month"]] = doc["count"]

        chart_data = []
        for month in range(1, 13):
            chart_data.append({
                "name": datetime(2000, month, 1).strftime("%b"),
                "users": user_counts[month],
                "tasks": task_counts[month]
            })

        return jsonify({"status": 1, "chartData": chart_data}), 200

    except Exception as e:
        return jsonify({"status": 0, "msg": str(e)}), 500
