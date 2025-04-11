from flask import Blueprint, request
from bson import ObjectId
from datetime import datetime
import re

from db import db  # Adjust this import to match your actual db.py
from utils import format_response  # Centralized response formatter

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
    try:
        data = request.json or {}
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        message = data.get("message", "").strip()
        task_price = data.get("task_price")
        hidden = data.get("hidden", False)

        if not title:
            return format_response(False, "title is required", None, 400)
        if not message:
            return format_response(False, "message (link) is required", None, 400)
        if not is_valid_url(message):
            return format_response(False, "message must be a valid link (URL)", None, 400)
        if task_price is None:
            return format_response(False, "task_price is required", None, 400)
        try:
            task_price = float(task_price)
            if task_price <= 0:
                raise ValueError()
        except ValueError:
            return format_response(False, "task_price must be a positive number", None, 400)

        task_id_str = str(ObjectId())
        task_doc = {
            "taskId": task_id_str,
            "title": title,
            "description": description,
            "message": message,
            "task_price": task_price,
            "hidden": hidden,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }

        db.tasks.insert_one(task_doc)
        return format_response(True, "Task created successfully", {"taskId": task_id_str}, 201)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@task_bp.route("/update", methods=["POST"])
def update_task():
    try:
        data = request.json or {}
        task_id = data.get("taskId", "").strip()
        if not task_id:
            return format_response(False, "taskId is required", None, 400)

        update_fields = {}

        if "title" in data:
            title = data["title"].strip()
            if title:
                update_fields["title"] = title
            else:
                return format_response(False, "title cannot be empty", None, 400)

        if "description" in data:
            update_fields["description"] = data["description"].strip()

        if "message" in data:
            new_message = data["message"].strip()
            if not new_message:
                return format_response(False, "message (link) cannot be empty", None, 400)
            if not is_valid_url(new_message):
                return format_response(False, "message must be a valid link (URL)", None, 400)
            update_fields["message"] = new_message

        if "task_price" in data:
            task_price = data["task_price"]
            try:
                task_price = float(task_price)
                if task_price <= 0:
                    raise ValueError()
                update_fields["task_price"] = task_price
            except ValueError:
                return format_response(False, "task_price must be a positive number", None, 400)

        if not update_fields:
            return format_response(False, "No valid fields to update", None, 400)

        update_fields["updatedAt"] = datetime.utcnow()
        result = db.tasks.update_one({"taskId": task_id}, {"$set": update_fields})
        if result.matched_count == 0:
            return format_response(False, "Task not found", None, 404)
        return format_response(True, "Task updated successfully", None, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@task_bp.route("/delete", methods=["POST"])
def delete_task():
    try:
        data = request.json or {}
        task_id = data.get("taskId", "").strip()
        if not task_id:
            return format_response(False, "taskId is required", None, 400)
        result = db.tasks.delete_one({"taskId": task_id})
        if result.deleted_count == 0:
            return format_response(False, "Task not found", None, 404)
        return format_response(True, "Task deleted successfully", None, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@task_bp.route("/getall", methods=["POST"])
def get_all_tasks():
    try:
        data = request.get_json() or {}
        keyword = data.get("keyword", "").strip()
        try:
            page = int(data.get("page", 0))
        except ValueError:
            return format_response(False, "page must be an integer", None, 400)
        try:
            per_page = int(data.get("per_page", 50))
        except ValueError:
            return format_response(False, "per_page must be an integer", None, 400)

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
        return format_response(True, "Tasks retrieved successfully", {
            "total": total_items,
            "page": page,
            "per_page": per_page,
            "tasks": tasks_list
        }, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@task_bp.route("/getbyid", methods=["GET"])
def get_task_by_id():
    try:
        task_id = request.args.get("taskId", "").strip()
        if not task_id:
            return format_response(False, "taskId query parameter is required", None, 400)
        task_doc = db.tasks.find_one({"taskId": task_id}, {"_id": 0})
        if not task_doc:
            return format_response(False, "Task not found", None, 404)
        return format_response(True, "Task retrieved successfully", {"task": task_doc}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

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
    - If no task is available, returns "Task will upload soon..."
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("userId", "").strip()
        if not user_id:
            return format_response(False, "userId is required", None, 400)

        tasks_cursor = db.tasks.find({}, {"_id": 0}).sort("createdAt", -1)
        candidate_task = None
        for task in tasks_cursor:
            if user_id:
                history_entry = db.task_history.find_one({
                    "userId": user_id,
                    "taskId": task["taskId"],
                    "verified": True
                })
                if history_entry:
                    continue
            candidate_task = task
            break

        if not candidate_task:
            return format_response(True, "Task will upload soon...", None, 200)

        if candidate_task.get("hidden", False):
            return format_response(True, "Task hidden", {"taskId": candidate_task.get("taskId", "")}, 200)

        return format_response(True, "Task retrieved successfully", {"task": candidate_task}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

@task_bp.route("/history", methods=["POST"])
def get_task_history():
    try:
        data = request.get_json() or {}
        user_id = data.get("userId", "").strip()
        if not user_id:
            return format_response(False, "userId is required", None, 400)

        tasks_cursor = db.task_history.find({"userId": user_id}, {"_id": 0}).sort("verifiedAt", -1)
        tasks_list = list(tasks_cursor)
        
        # Remove the _id field from embedded task_details, if present.
        for task in tasks_list:
            if "task_details" in task and isinstance(task["task_details"], dict):
                task["task_details"].pop("_id", None)
        
        return format_response(True, "Task history retrieved successfully", {"task_history": tasks_list}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)


@task_bp.route("/togglehide", methods=["POST"])
def toggle_hide_task():
    try:
        data = request.json or {}
        task_id = data.get("taskId", "").strip()
        isHide = data.get("isHide")
        if not task_id:
            return format_response(False, "taskId is required", None, 400)
        if isHide is None:
            return format_response(False, "action is required. Use 1 for hide, 0 for unhide.", None, 400)
        try:
            isHide = int(isHide)
        except ValueError:
            return format_response(False, "action must be an integer: 1 for hide, 0 for unhide.", None, 400)
        if isHide not in [0, 1]:
            return format_response(False, "Invalid action. Use 1 for hide, 0 for unhide.", None, 400)
        hidden = True if isHide == 1 else False
        result = db.tasks.update_one({"taskId": task_id}, {"$set": {"hidden": hidden, "updatedAt": datetime.utcnow()}})
        if result.matched_count == 0:
            return format_response(False, "Task not found", None, 404)
        if hidden:
            return format_response(True, "Task will upload soon...", {"taskId": task_id}, 200)
        else:
            task = db.tasks.find_one({"taskId": task_id}, {"_id": 0})
            return format_response(True, "Task unhidden successfully", {"task": task}, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500)

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
                "status": "unlocked"  # or "completed" or "locked"
             },
             ...
         ]
      }
      
    Logic:
      - Tasks are ordered by newest first.
      - If the task is already completed (verified) by the user, its status is "completed".
      - The first non-completed task is marked as "unlocked".
      - All subsequent non-completed tasks are marked as "locked".
      - Tasks with hidden = true are not returned.
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("userId", "").strip()
        if not user_id:
            return format_response(False, "userId is required", None, 400)

        tasks_cursor = db.tasks.find({"hidden": {"$ne": True}}, {"_id": 0}).sort("createdAt", -1).limit(4)
        tasks_list = list(tasks_cursor)

        unlocked_found = False
        for task in tasks_list:
            history_entry = db.task_history.find_one({
                "userId": user_id,
                "taskId": task.get("taskId"),
                "verified": True
            })
            if history_entry:
                task["status"] = "completed"
            else:
                if not unlocked_found:
                    task["status"] = "unlocked"
                    unlocked_found = True
                else:
                    task["status"] = "locked"

        return format_response(True, "Latest tasks retrieved successfully", {
            "userId": user_id,
            "tasks": tasks_list
        }, 200)
    except Exception as e:
        return format_response(False, f"Server error: {str(e)}", None, 500) 