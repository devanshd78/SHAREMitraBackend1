from flask import Blueprint, request, jsonify
from bson import ObjectId
import datetime
import re

from db import db  # Adjust this import to match your actual db.py

task_bp = Blueprint("task", __name__, url_prefix="/task")

def is_valid_url(url: str) -> bool:
    """
    Basic URL validation: checks if the string starts with http://, https:// or ftp://
    and has at least one character after.
    This is a simple pattern – you can make it more or less strict as needed.
    """
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
    
    - 'title' (required, non-empty)
    - 'message' must be a valid URL
    - 'description' optional
    - 'task_price' required, positive number
    """
    data = request.json or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    message = data.get("message", "").strip()
    task_price = data.get("task_price")
    hidden = data.get("hidden")

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

    # Generate unique taskId
    task_id_str = str(ObjectId())

    task_doc = {
        "taskId": task_id_str,
        "title": title,
        "description": description,
        "message": message,
        "task_price": task_price,  # New field added
        "hidden": hidden,           # Default value added
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }

    db.tasks.insert_one(task_doc)

    return jsonify({
        "message": "Task created successfully",
        "taskId": task_id_str
    }), 201

@task_bp.route("/update", methods=["POST"])
def update_task():
    """
    POST /task/update
    JSON Body:
    {
      "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx",
      "title": "New Title",
      "description": "New Description",
      "message": "https://example.com/new-valid-link",
      "task_price": 120.50  # Optional numeric input
    }
    
    - 'taskId' is required to find the existing task.
    - If 'message' is provided, it must be a valid URL.
    - If 'task_price' is provided, it must be a positive number.
    """
    data = request.json or {}
    task_id = data.get("taskId", "").strip()
    if not task_id:
        return jsonify({"error": "taskId is required"}), 400

    update_fields = {}

    # Title
    if "title" in data:
        title = data["title"].strip()
        if title:
            update_fields["title"] = title
        else:
            return jsonify({"error": "title cannot be empty"}), 400

    # Description
    if "description" in data:
        update_fields["description"] = data["description"].strip()

    # Message (Link)
    if "message" in data:
        new_message = data["message"].strip()
        if not new_message:
            return jsonify({"error": "message (link) cannot be empty"}), 400
        if not is_valid_url(new_message):
            return jsonify({"error": "message must be a valid link (URL)"}), 400
        update_fields["message"] = new_message

    # Task Price
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

    update_fields["updatedAt"] = datetime.datetime.utcnow()

    result = db.tasks.update_one(
        {"taskId": task_id},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Task not found"}), 404

    return jsonify({"message": "Task updated successfully"}), 200

@task_bp.route("/delete", methods=["POST"])
def delete_task():
    """
    POST /task/delete
    JSON Body:
    {
      "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx"
    }
    
    - 'taskId' is required
    """
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
    """
    POST /task/getall
    Request JSON Body:
      {
        "keyword": "optional search keyword",
        "page": 0,             # optional, default=0
        "per_page": 50         # optional, default=50
      }
    Returns:
      {
        "total": <total_matching_tasks>,
        "page": <current_page>,
        "per_page": <items_per_page>,
        "tasks": [
            {
              "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx",
              "title": "Some Title",
              "description": "Task description",
              "message": "https://example.com/valid-link",
              "status": "pending/accepted",  # defaults to pending if not updated
              "createdAt": "...",
              "updatedAt": "..."
            },
            ...
        ]
      }
    """
    data = request.get_json() or {}
    
    # Retrieve optional keyword and pagination parameters
    keyword = data.get("keyword", "").strip()
    try:
        page = int(data.get("page", 0))
    except ValueError:
        return jsonify({"error": "page must be an integer"}), 400

    try:
        per_page = int(data.get("per_page", 50))
    except ValueError:
        return jsonify({"error": "per_page must be an integer"}), 400

    # Build query. No userId filtering is applied.
    query = {}
    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"description": {"$regex": keyword, "$options": "i"}},
            {"message": {"$regex": keyword, "$options": "i"}},
            {"status": {"$regex": keyword, "$options": "i"}}
        ]

    total_items = db.tasks.count_documents(query)
    tasks_cursor = db.tasks.find(query, {"_id": 0}).sort("createdAt", -1)\
        .skip(page * per_page).limit(per_page)
    tasks_list = list(tasks_cursor)

    # Ensure each task shows a status, defaulting to "pending" if not set.
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
    """
    GET /task/getbyid?taskId=<someId>
    Example: /task/getbyid?taskId=xxxxxxxxxxxxxxxxxxxxxxxx
    """
    task_id = request.args.get("taskId", "").strip()
    if not task_id:
        return jsonify({"error": "taskId query parameter is required"}), 400

    task_doc = db.tasks.find_one({"taskId": task_id}, {"_id": 0})
    if not task_doc:
        return jsonify({"error": "Task not found"}), 404

    return jsonify({"task": task_doc}), 200


@task_bp.route("/newtask", methods=["GET"])
def get_new_task():
    """
    GET /task/newtask
    Returns the most recently created task (top task).
    """
    latest_task = db.tasks.find({}, {"_id": 0}).sort("createdAt", -1).limit(1)
    latest_task_list = list(latest_task)
    
    if not latest_task_list:
        return jsonify({"error": "No tasks found"}), 404

    return jsonify({"task": latest_task_list[0]}), 200

@task_bp.route("/prevtasks", methods=["GET"])
def get_previous_tasks():
    """
    GET /task/prevtasks
    Returns all tasks except the most recent one.
    """
    latest_task = db.tasks.find({}, {"taskId": 1}).sort("createdAt", -1).limit(1)
    latest_task_list = list(latest_task)
    
    if not latest_task_list:
        return jsonify({"tasks": []}), 200  # No tasks yet

    latest_task_id = latest_task_list[0]["taskId"]

    previous_tasks_cursor = db.tasks.find(
        {"taskId": {"$ne": latest_task_id}}, {"_id": 0}
    ).sort("createdAt", -1)

    previous_tasks = list(previous_tasks_cursor)
    return jsonify({"tasks": previous_tasks}), 200

@task_bp.route('/history', methods=['POST'])
def get_task_history():
    """
    POST /image/api/history
    Request JSON Body:
      {
        "userId": "user123"
      }
    Returns:
      {
         "userId": "user123",
         "task_history": [
             {
                "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx",
                "userId": "user123",
                "matched_link": "https://example.com/valid-link",
                "group_name": "Group Name",
                "participant_count": 2,
                "details": { ... },
                "verified": true,
                "verifiedAt": "2025-04-02T15:00:00"
             },
             ...
         ]
      }
    """
    data = request.get_json() or {}
    user_id = data.get("userId", "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    # Query the task_history collection for documents matching the given userId.
    tasks_cursor = db.task_history.find({"userId": user_id}, {"_id": 0}).sort("verifiedAt", -1)
    tasks_list = list(tasks_cursor)

    return jsonify({
        "userId": user_id,
        "task_history": tasks_list
    }), 200
    
@task_bp.route("/togglehide", methods=["POST"])
def toggle_hide_task():
    """
    POST /task/togglehide
    JSON Body:
    {
      "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx",
      "action": 0    # 0 to hide, 1 to unhide
    }
    
    If action is 0, the task will be hidden and a message "Task will upload soon..." is returned.
    If action is 1, the task will be unhidden and the full task details are returned.
    """
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

    # Set hidden field based on action
    hidden = True if isHide == 1 else False

    result = db.tasks.update_one(
        {"taskId": task_id},
        {"$set": {"hidden": hidden, "updatedAt": datetime.datetime.utcnow()}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Task not found"}), 404

    if hidden:
        return jsonify({
            "message": "Task will upload soon...",
            "taskId": task_id
        }), 200
    else:
        task = db.tasks.find_one({"taskId": task_id}, {"_id": 0})
        return jsonify({
            "message": "Task unhidden successfully",
            "task": task
        }), 200
