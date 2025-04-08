from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime, timedelta
import re
import secrets

from db import db  # Adjust this import to match your actual db.py

task_bp = Blueprint("task", __name__, url_prefix="/task")

def is_valid_url(url: str) -> bool:
    pattern = r'^(https?|ftp)://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))

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
      "task_price": 100,  # numeric
      "hidden": false     # optional boolean
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

    # Generate unique taskId
    task_id_str = str(ObjectId())

    task_doc = {
        "taskId": task_id_str,
        "title": title,
        "description": description,
        "message": message,   # Original link
        "task_price": task_price,
        "hidden": hidden,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }

    db.tasks.insert_one(task_doc)

    return jsonify({
        "message": "Task created successfully",
        "taskId": task_id_str,
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

@task_bp.route("/newtask", methods=["POST"])
def new_task():
    """
    POST /task/newtask
    JSON Body:
    {
      "userId": "user123"  
    }

    Returns the most recent task that has not already been verified by the user.
    - If a task is found and its 'hidden' status is set, a message "Task hidden" is returned.
    - If no task is available (e.g. all tasks are already verified), returns "Task will upload soon..."
    """
    data = request.get_json() or {}
    user_id = data.get("userId", "").strip()

    # Retrieve candidate tasks sorted by creation time (newest first)
    tasks_cursor = db.tasks.find({}, {"_id": 0}).sort("createdAt", -1)
    candidate_task = None

    for task in tasks_cursor:
        # If a userId is provided, check if this task has already been verified for that user.
        if user_id:
            history_entry = db.task_history.find_one({
                "userId": user_id,
                "taskId": task["taskId"],
                "verified": True
            })
            if history_entry:
                # Skip this task if it has been verified by the user.
                continue

        # Use this task as the candidate.
        candidate_task = task
        break

    if not candidate_task:
        return jsonify({"message": "Task will upload soon..."}), 200

    # If the candidate task is marked as hidden, return a message instead of the task details.
    if candidate_task.get("hidden", False):
        return jsonify({
            "message": "Task hidden",
            "taskId": candidate_task.get("taskId", "")
        }), 200

    return jsonify({"task": candidate_task}), 200

@task_bp.route('/history', methods=['POST'])
def get_task_history():
    data = request.get_json() or {}
    user_id = data.get("userId", "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    # Retrieve task history for the user.
    tasks_cursor = db.task_history.find({"userId": user_id}, {"_id": 0}).sort("verifiedAt", -1)
    tasks_list = list(tasks_cursor)
    
    # Iterate over each history document and remove the ObjectId in the embedded task_details
    for task in tasks_list:
        if "task_details" in task and isinstance(task["task_details"], dict):
            task["task_details"].pop("_id", None)  # Remove _id if present

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

@task_bp.route("/latestTask", methods=["POST"])
def getLatestTask():
    """
    POST /task/latestTask
    JSON Body:
    {
      "userId": "user123"
    }
    
    Returns:
      {
         "userId": "user123",
         "tasks": [
             {
                "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx",
                "title": "Some Title",
                "description": "Task description",
                "message": "https://example.com/valid-link",
                "task_price": 100,
                "hidden": false,
                "createdAt": "2025-04-07T12:34:56.789Z",
                "updatedAt": "2025-04-07T12:34:56.789Z",
                "status": "unlocked"  # or "done" or "locked"
             },
             ...
         ]
      }
      
    Logic:
      - Tasks are ordered by newest first.
      - If the task is already completed (verified) by the user, its status is "done".
      - The first non-completed task is marked as "unlocked".
      - All subsequent non-completed tasks are marked as "locked".
      - Tasks with hidden = true are not returned.
    """
    data = request.get_json() or {}
    user_id = data.get("userId", "").strip()
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    # Retrieve the top 4 tasks sorted by createdAt descending (newest first) excluding hidden tasks
    tasks_cursor = db.tasks.find({"hidden": {"$ne": True}}, {"_id": 0}).sort("createdAt", -1).limit(4)
    tasks_list = list(tasks_cursor)

    # Sequential unlocking: mark completed tasks as done, first non-completed as unlocked,
    # and remaining non-completed as locked.
    unlocked_found = False
    for task in tasks_list:
        # Check if the user has already completed this task
        history_entry = db.task_history.find_one({
            "userId": user_id,
            "taskId": task.get("taskId"),
            "verified": True
        })
        if history_entry:
            task["status"] = "done"
        else:
            if not unlocked_found:
                task["status"] = "unlocked"
                unlocked_found = True
            else:
                task["status"] = "locked"

    return jsonify({
        "userId": user_id,
        "tasks": tasks_list
    }), 200
