import os
import base64
import re
import json
import requests
import hmac
import hashlib
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, request, jsonify, Blueprint
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from dotenv import load_dotenv
from PIL import Image
import imagehash
import logging

from wallet import update_wallet_after_task
from utils import format_response  # Centralized response formatter

# Load environment variables
load_dotenv()

# Configuration from .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL")

# Blueprints for image analysis and task management
image_analysis_bp = Blueprint('image_analysis', __name__, url_prefix="/image")
task_bp = Blueprint('task', __name__, url_prefix="/task")

# MongoDB connection
client = MongoClient("mongodb://localhost:27017")
db = client['enoylity']

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

def encode_image_to_base64_from_bytes(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

def get_recent_task_links(days=3):
    """Fetch recent task links from the database within the specified number of days."""
    try:
        threshold_date = datetime.utcnow() - timedelta(days=days)
        recent_tasks = db.task.find({"created_at": {"$gte": threshold_date}}).sort("created_at", -1)
        links = [task["link"] for task in recent_tasks if "link" in task]
        return links
    except Exception as e:
        logger.exception("Error fetching recent task links: %s", e)
        return []

def analyze_image_with_openai_from_bytes(image_bytes, expected_link):
    """
    Send the image to the OpenAI API for analysis, checking if it's a valid WhatsApp broadcast screenshot.
    """
    try:
        base64_image = encode_image_to_base64_from_bytes(image_bytes)
        logger.info("Encoded Image Length: %s", len(base64_image))
        prompt = (
            "Analyze this image and determine if it's a screenshot of a WhatsApp broadcast message.\n\n"
            "Specifically check for:\n"
            "1. Is this clearly a WhatsApp interface?\n"
            "2. Is it a broadcast list (not a group & not sending message to a particular user)?\n"
            "3. Does the screenshot contain this exact link or URL: '{}'? \n"
            "4. What is the timestamp or time of the message (if visible)?\n\n"
            "Format your response as JSON with these fields:\n"
            "- is_whatsapp_screenshot (boolean)\n"
            "- is_broadcast_list (boolean)\n"
            "- contains_expected_link (boolean)\n"
            "- timestamp (string, format as shown in image)\n"
            "- confidence_score (1-10)\n"
            "- reason (brief explanation)"
        ).format(expected_link)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            "max_tokens": 500
        }
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        logger.info("OpenAI Raw Response: %s", response.text)
        if response.status_code == 200:
            result = response.json()
            assistant_content = result["choices"][0]["message"]["content"]
            assistant_content_clean = re.sub(r"```(?:json)?", "", assistant_content).replace("```", "").strip()
            try:
                content = json.loads(assistant_content_clean)
            except json.JSONDecodeError:
                return {
                    "verified": False,
                    "message": "OpenAI response is not valid JSON",
                    "details": assistant_content
                }
            verified = (
                content.get("is_whatsapp_screenshot", False) and
                content.get("is_broadcast_list", False) and
                content.get("contains_expected_link", False)
            )
            return {
                "verified": verified,
                "message": "Image analyzed successfully",
                "details": content
            }
        else:
            return {
                "verified": False,
                "message": f"API Error: {response.status_code}",
                "details": response.text
            }
    except Exception as e:
        logger.exception("Error processing image:")
        return {
            "verified": False,
            "message": f"Error processing image: {str(e)}"
        }

def check_group_participants_from_bytes(image_bytes):
    """
    Analyze the group image to determine participant count and broadcast list validity.
    """
    try:
        base64_image = encode_image_to_base64_from_bytes(image_bytes)
        prompt = (
            "This image is a screenshot of a WhatsApp broadcast list information page. \n"
            "Determine the number of recipients and the name of the list.\n\n"
            "Return JSON with:\n"
            "- participant_count (integer)\n"
            "- is_valid_group (boolean, true if participants >= 1)\n"
            "- group_name (string)\n"
            "- reason (brief explanation)"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            "max_tokens": 300
        }
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            result = response.json()
            assistant_content = result["choices"][0]["message"]["content"]
            assistant_content_clean = re.sub(r"```(?:json)?", "", assistant_content).replace("```", "").strip()
            try:
                content = json.loads(assistant_content_clean)
                return content
            except json.JSONDecodeError:
                return {
                    "participant_count": 0,
                    "is_valid_group": False,
                    "reason": "OpenAI response is not valid JSON",
                    "raw_response": assistant_content
                }
        return {
            "participant_count": 0,
            "is_valid_group": False,
            "reason": f"API error: {response.status_code}",
            "raw_response": response.text
        }
    except Exception as e:
        logger.exception("Error processing group image:")
        return {
            "participant_count": 0,
            "is_valid_group": False,
            "reason": str(e)
        }

def compute_phash_from_bytes(image_bytes):
    """Compute the perceptual hash for an image given its byte content."""
    try:
        image_stream = BytesIO(image_bytes)
        img = Image.open(image_stream)
        return str(imagehash.phash(img))
    except Exception as e:
        logger.exception("Error computing pHash:")
        return None

def is_duplicate_phash(new_phash, task_id, user_id, threshold=5):
    """Check if a similar image (based on pHash) already exists in the task history."""
    try:
        history = list(db.task_history.find({"taskId": task_id, "verified": True}))
        for record in history:
            existing_phash = record.get("image_phash")
            if existing_phash:
                diff = imagehash.hex_to_hash(new_phash) - imagehash.hex_to_hash(existing_phash)
                if diff <= threshold and record.get("userId") != user_id:
                    return True
        return False
    except Exception as e:
        logger.exception("Error checking duplicate pHash:")
        return False

@image_analysis_bp.route('/api/verify', methods=['POST'])
def verify_image():
    """
    Verify an image screenshot submission for a task. 
    Validates the screenshot, checks for duplicates, and verifies broadcast list details.
    """
    try:
        # Retrieve taskId and userId from form data.
        task_id = request.form.get("taskId", "").strip()
        user_id = request.form.get("userId", "").strip()
    
        if not task_id:
            return format_response(False, "taskId is required", None, 400)
        if not user_id:
            return format_response(False, "userId is required", None, 400)
    
        # Check if the user has already completed this task.
        existing_entry = db.task_history.find_one({"taskId": task_id, "userId": user_id})
        if existing_entry:
            return format_response(False, "This user has already completed the task.", {"status": "already_done"}, 200)
    
        # Fetch the task document from the database.
        task_doc = db.tasks.find_one({"taskId": task_id})
        if not task_doc:
            return format_response(False, "Task not found", None, 404)
    
        # Mark the task as pending.
        db.tasks.update_one(
            {"taskId": task_id},
            {"$set": {"status": "pending", "updatedAt": datetime.utcnow()}}
        )
    
        # Validate file uploads.
        if 'image' not in request.files or 'group_image' not in request.files:
            return format_response(False, "Both 'image' and 'group_image' files are required", None, 400)
    
        image_file = request.files['image']
        group_image_file = request.files['group_image']
    
        if image_file.filename == '' or group_image_file.filename == '':
            return format_response(False, "Image files must be selected", None, 400)
    
        if not allowed_file(image_file.filename) or not allowed_file(group_image_file.filename):
            return format_response(False, "File type not allowed", None, 400)
    
        # Read image bytes (without saving to disk).
        image_bytes = image_file.read()
        group_image_bytes = group_image_file.read()
    
        # Compute the perceptual hash for the uploaded image.
        uploaded_phash = compute_phash_from_bytes(image_bytes)
        logger.info("Uploaded pHash: %s", uploaded_phash)
        if not uploaded_phash:
            return format_response(False, "Unable to compute image pHash", None, 400)
    
        # Check for duplicate screenshots.
        if is_duplicate_phash(uploaded_phash, task_id, user_id):
            return format_response(False, "Screenshot already used by another user", None, 400)
    
        # Validate the broadcast list image.
        group_check = check_group_participants_from_bytes(group_image_bytes)
        logger.info("Group Check Response: %s", group_check)
        if not group_check.get("is_valid_group"):
            db.tasks.update_one(
                {"taskId": task_id},
                {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
            )
            return format_response(
                False,
                "Broadcast list must contain at least 2 recipients.",
                {"participant_check": group_check, "status": "rejected"},
                200
            )
    
        # Use the task's message (link) as the expected link.
        expected_link = task_doc.get("message", "")
        result = analyze_image_with_openai_from_bytes(image_bytes, expected_link)
    
        if result.get("verified"):
            # Update task status to accepted.
            db.tasks.update_one(
                {"taskId": task_id},
                {"$set": {
                    "status": "accepted",
                    "updatedAt": datetime.utcnow(),
                    "verification_details": result.get("details", {})
                }}
            )
            history_doc = {
                "taskId": task_id,
                "userId": user_id,
                "matched_link": expected_link,
                "task_name": task_doc.get("title", ""),
                "participant_count": group_check.get("participant_count"),
                "verified": True,
                "verifiedAt": datetime.utcnow(),
                "task_price": int(task_doc.get("task_price", 0)),
                "image_phash": uploaded_phash,
                "task_details": task_doc
            }
            db.task_history.insert_one(history_doc)
            wallet_update = update_wallet_after_task(user_id, task_id, int(task_doc.get("task_price", 0)))
            if "error" in wallet_update:
                return format_response(False, wallet_update.get("error"), wallet_update, 400)
    
            return format_response(
                True,
                "Image verified successfully.",
                {
                    "matched_link": expected_link,
                    "group_name": group_check.get("group_name"),
                    "participant_count": group_check.get("participant_count"),
                    "verification_details": result.get("details", {}),
                    "status": "accepted"
                },
                200
            )
        else:
            # Update task status to rejected.
            db.tasks.update_one(
                {"taskId": task_id},
                {"$set": {
                    "status": "rejected",
                    "updatedAt": datetime.utcnow(),
                    "verification_details": result.get("details", {})
                }}
            )
            return format_response(
                False,
                "No matching link found in the broadcast message screenshot",
                {"participant_check": group_check, "verification_details": result.get("details", {}), "status": "rejected"},
                200
            )
    except Exception as e:
        logger.exception("Error verifying image:")
        return format_response(False, f"Server error: {str(e)}", None, 500)