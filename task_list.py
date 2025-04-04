from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
import re
import secrets

from db import db  # Adjust this import to match your actual db.py

task_bp = Blueprint("task", __name__, url_prefix="/task")

def is_valid_url(url: str) -> bool:
    pattern = r'^(https?|ftp)://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))

@task_bp.route("/create", methods=["POST"])
def create_task():
    """
    POST /task/create
    JSON Body:
    {
      "title": "Some Title",
      "description": "Task description",
      "message": "https://example.com/valid-link",
      "task_price": 100  # New numeric input
    }
    """
    data = request.json or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    message = data.get("message", "").strip()
    task_price = data.get("task_price")
    hidden = data.get("hidden", False)

    # Validation
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not message:
        return jsonify({"error": "message (link) is required"}), 400
    if not is_valid_url(message):
        return jsonify({"error": "message must be a valid link (URL)"}), 400
    if task_price is None:
        return jsonify({"error": "task_price is required"}), 400
    try:
        task_price = float(task_price)
        if task_price <= 0:
            raise ValueError()
    except ValueError:
        return jsonify({"error": "task_price must be a positive number"}), 400

    # Generate unique taskId and tokenized URL for per-user verification.
    task_id_str = str(ObjectId())
    # token = secrets.token_urlsafe(16)
    # unique_link = f"{message}?token={token}"

    task_doc = {
        "taskId": task_id_str,
        "title": title,
        "description": description,
        "message": message,  # Original link (could be a landing page)
        # "unique_link": unique_link,  # Unique tokenized URL
        # "token": token,
        "task_price": task_price,
        "hidden": hidden,
        "status": "pending",  # default status
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }

    db.tasks.insert_one(task_doc)
    return jsonify({
        "message": "Task created successfully",
        "taskId": task_id_str,
        # "unique_link": unique_link
    }), 201

@task_bp.route("/update", methods=["POST"])
def update_task():
    data = request.json or {}
    task_id = data.get("taskId", "").strip()
    if not task_id:
        return jsonify({"error": "taskId is required"}), 400

    update_fields = {}

    if "title" in data:
        title = data["title"].strip()
        if title:
            update_fields["title"] = title
        else:
            return jsonify({"error": "title cannot be empty"}), 400

    if "description" in data:
        update_fields["description"] = data["description"].strip()

    if "message" in data:
        new_message = data["message"].strip()
        if not new_message:
            return jsonify({"error": "message (link) cannot be empty"}), 400
        if not is_valid_url(new_message):
            return jsonify({"error": "message must be a valid link (URL)"}), 400
        update_fields["message"] = new_message

    if "task_price" in data:
        task_price = data["task_price"]
        try:
            task_price = float(task_price)
            if task_price <= 0:
                raise ValueError()
            update_fields["task_price"] = task_price
        except ValueError:
            return jsonify({"error": "task_price must be a positive number"}), 400

    if not update_fields:
        return jsonify({"error": "No valid fields to update"}), 400

    update_fields["updatedAt"] = datetime.utcnow()
    result = db.tasks.update_one({"taskId": task_id}, {"$set": update_fields})
    if result.matched_count == 0:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"message": "Task updated successfully"}), 200

@task_bp.route("/delete", methods=["POST"])
def delete_task():
    data = request.json or {}
    task_id = data.get("taskId", "").strip()
    if not task_id:
        return jsonify({"error": "taskId is required"}), 400
    result = db.tasks.delete_one({"taskId": task_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"message": "Task deleted successfully"}), 200

@task_bp.route("/getall", methods=["POST"])
def get_all_tasks():
    data = request.get_json() or {}
    keyword = data.get("keyword", "").strip()
    try:
        page = int(data.get("page", 0))
    except ValueError:
        return jsonify({"error": "page must be an integer"}), 400
    try:
        per_page = int(data.get("per_page", 50))
    except ValueError:
        return jsonify({"error": "per_page must be an integer"}), 400

    query = {}
    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"description": {"$regex": keyword, "$options": "i"}},
            {"message": {"$regex": keyword, "$options": "i"}},
            {"status": {"$regex": keyword, "$options": "i"}}
        ]
    total_items = db.tasks.count_documents(query)
    tasks_cursor = db.tasks.find(query, {"_id": 0}).sort("createdAt", -1).skip(page * per_page).limit(per_page)
    tasks_list = list(tasks_cursor)
    for task in tasks_list:
        task["status"] = task.get("status", "pending")
    return jsonify({
        "total": total_items,
        "page": page,
        "per_page": per_page,
        "tasks": tasks_list
    }), 200

@task_bp.route("/getbyid", methods=["GET"])
def get_task_by_id():
    task_id = request.args.get("taskId", "").strip()
    if not task_id:
        return jsonify({"error": "taskId query parameter is required"}), 400
    task_doc = db.tasks.find_one({"taskId": task_id}, {"_id": 0})
    if not task_doc:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"task": task_doc}), 200

@task_bp.route("/newtask", methods=["GET"])
def get_new_task():
    latest_task = db.tasks.find({}, {"_id": 0}).sort("createdAt", -1).limit(1)
    latest_task_list = list(latest_task)
    if not latest_task_list:
        return jsonify({"error": "No tasks found"}), 404
    return jsonify({"task": latest_task_list[0]}), 200

@task_bp.route("/prevtasks", methods=["GET"])
def get_previous_tasks():
    latest_task = db.tasks.find({}, {"taskId": 1}).sort("createdAt", -1).limit(1)
    latest_task_list = list(latest_task)
    if not latest_task_list:
        return jsonify({"tasks": []}), 200
    latest_task_id = latest_task_list[0]["taskId"]
    previous_tasks_cursor = db.tasks.find({"taskId": {"$ne": latest_task_id}}, {"_id": 0}).sort("createdAt", -1)
    previous_tasks = list(previous_tasks_cursor)
    return jsonify({"tasks": previous_tasks}), 200

@task_bp.route('/history', methods=['POST'])
def get_task_history():
    data = request.get_json() or {}
    user_id = data.get("userId", "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    tasks_cursor = db.task_history.find({"userId": user_id}, {"_id": 0}).sort("verifiedAt", -1)
    tasks_list = list(tasks_cursor)
    return jsonify({
        "userId": user_id,
        "task_history": tasks_list
    }), 200

@task_bp.route("/togglehide", methods=["POST"])
def toggle_hide_task():
    data = request.json or {}
    task_id = data.get("taskId", "").strip()
    isHide = data.get("isHide")
    if not task_id:
        return jsonify({"error": "taskId is required"}), 400
    if isHide is None:
        return jsonify({"error": "action is required. Use 1 for hide, 0 for unhide."}), 400
    try:
        isHide = int(isHide)
    except ValueError:
        return jsonify({"error": "action must be an integer: 1 for hide, 0 for unhide."}), 400
    if isHide not in [0, 1]:
        return jsonify({"error": "Invalid action. Use 1 for hide, 0 for unhide."}), 400
    hidden = True if isHide == 1 else False
    result = db.tasks.update_one({"taskId": task_id}, {"$set": {"hidden": hidden, "updatedAt": datetime.utcnow()}})
    if result.matched_count == 0:
        return jsonify({"error": "Task not found"}), 404
    if hidden:
        return jsonify({"message": "Task will upload soon...", "taskId": task_id}), 200
    else:
        task = db.tasks.find_one({"taskId": task_id}, {"_id": 0})
        return jsonify({"message": "Task unhidden successfully", "task": task}), 200