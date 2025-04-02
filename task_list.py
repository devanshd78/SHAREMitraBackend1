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
    POST /task/createtask
    JSON Body:
    {
      "title": "Some Title",
      "description": "Task description",
      "message": "https://example.com/valid-link"
    }
    
    - 'title' (required, non-empty)
    - 'message' must be a valid URL (per is_valid_url).
    - 'description' optional
    """
    data = request.json or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    message = data.get("message", "").strip() 

    # Basic validation
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not message:
        return jsonify({"error": "message (link) is required"}), 400
    if not is_valid_url(message):
        return jsonify({"error": "message must be a valid link (URL)"}), 400

    # Generate a unique taskId from MongoDB ObjectId
    task_id_str = str(ObjectId())

    task_doc = {
        "taskId": task_id_str,
        "title": title,
        "description": description,
        "message": message,  # validated URL
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
    POST /task/updatetask
    JSON Body:
    {
      "taskId": "xxxxxxxxxxxxxxxxxxxxxxxx",
      "title": "New Title",
      "description": "New Description",
      "message": "https://example.com/new-valid-link"
    }
    
    - 'taskId' is required to find the existing task.
    - If 'message' is provided, it must be a valid URL.
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

@task_bp.route("/getall", methods=["GET"])
def get_all_tasks():
    """
    GET /task/getall
    Returns all tasks sorted by newest first (newest task on top).
    Excludes Mongo _id field and wraps in 'task' key.
    """
    tasks_cursor = db.tasks.find({}, {"_id": 0}).sort("createdAt", -1)
    tasks_list = list(tasks_cursor)
    return jsonify({"task": tasks_list}), 200


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