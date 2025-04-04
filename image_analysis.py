
import os
import base64
import re
import json
import requests
import hmac
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Blueprint
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from dotenv import load_dotenv
from wallet import update_wallet_after_task
from PIL import Image
import imagehash

# Load environment variables
load_dotenv()

# Configuration from .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL")

# Blueprints for image analysis and task management
image_analysis_bp = Blueprint('image_analysis', __name__, url_prefix="/image")
task_bp = Blueprint('task', __name__, url_prefix="/task")

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# MongoDB connection
client = MongoClient("mongodb://localhost:27017")
db = client['enoylity']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_recent_task_links(days=3):
    try:
        threshold_date = datetime.utcnow() - timedelta(days=days)
        recent_tasks = db.task.find({"created_at": {"$gte": threshold_date}}).sort("created_at", -1)
        links = [task["link"] for task in recent_tasks if "link" in task]
        return links
    except Exception as e:
        print(f"Error fetching recent task links: {str(e)}")
        return []

def analyze_image_with_openai(image_path, expected_link):
    try:
        base64_image = encode_image_to_base64(image_path)
        print(f"Encoded Image Length: {len(base64_image)}") 
        prompt = f"""
        Analyze this image and determine if it's a screenshot of a WhatsApp broadcast message.

        Specifically check for:
        1. Is this clearly a WhatsApp interface?
        2. Is it a broadcast list (not a group)?
        3. Does the screenshot contain this exact link or URL: '{expected_link}'?
        4. What is the timestamp or time of the message (if visible)?

        Format your response as JSON with these fields:
        - is_whatsapp_screenshot (boolean)
        - is_broadcast_list (boolean)
        - contains_expected_link (boolean)
        - timestamp (string, format as shown in image)
        - confidence_score (1-10)
        - reason (brief explanation)
        """

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
        print("OpenAI Raw Response:", response.text)
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
                content.get("is_whatsapp_screenshot", False)
                and content.get("is_broadcast_list", False)
                and content.get("contains_expected_link", False)
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
        return {
            "verified": False,
            "message": f"Error processing image: {str(e)}"
        }

def check_group_participants(image_path):
    try:
        base64_image = encode_image_to_base64(image_path)

        prompt = """
        This image is a screenshot of a WhatsApp broadcast list information page. 
        Determine the number of recipients and the name of the list.

        Return JSON with:
        - participant_count (integer)
        - is_valid_group (boolean, true if participants >= 1)
        - group_name (string)
        - reason (brief explanation)
        """

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
        return {
            "participant_count": 0,
            "is_valid_group": False,
            "reason": str(e)
        }

# ------------------------------------------------------------------------------
# pHash Computation and Duplicate Check
# ------------------------------------------------------------------------------
def compute_phash(image_path):
    try:
        img = Image.open(image_path)
        # Return the hash as a hex string
        return str(imagehash.phash(img))
    except Exception as e:
        print(f"Error computing pHash: {str(e)}")
        return None

def is_duplicate_phash(new_phash, task_id, user_id, threshold=5):
    # Find all verified screenshots for this task
    history = list(db.task_history.find({"taskId": task_id, "verified": True}))
    for record in history:
        existing_phash = record.get("image_phash")
        if existing_phash:
            diff = imagehash.hex_to_hash(new_phash) - imagehash.hex_to_hash(existing_phash)
            if diff <= threshold and record.get("userId") != user_id:
                return True
    return False

# ------------------------------------------------------------------------------
# Updated Verification Endpoint
# ------------------------------------------------------------------------------
@image_analysis_bp.route('/api/verify', methods=['POST'])
def verify_image():
    # Retrieve taskId, userId from form data (assuming multipart/form-data)
    task_id = request.form.get("taskId", "").strip()
    user_id = request.form.get("userId", "").strip()
    
    if not task_id:
        return jsonify({"error": "taskId is required"}), 400
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    # Check if the user has already completed this task
    existing_entry = db.task_history.find_one({"taskId": task_id, "userId": user_id})
    if existing_entry:
        return jsonify({
            "error": "Already done task",
            "message": "This user has already completed the task.",
            "status": "already_done"
        }), 200

    # Fetch the task document from the database
    task_doc = db.tasks.find_one({"taskId": task_id})
    if not task_doc:
        return jsonify({"error": "Task not found"}), 404

    # Mark the task as pending when it is visited
    db.tasks.update_one(
        {"taskId": task_id},
        {"$set": {"status": "pending", "updatedAt": datetime.utcnow()}}
    )

    # Check for both image and group_image files
    if 'image' not in request.files or 'group_image' not in request.files:
        return jsonify({"error": "Both 'image' and 'group_image' are required"}), 400

    image_file = request.files['image']
    group_image_file = request.files['group_image']

    if image_file.filename == '' or group_image_file.filename == '':
        return jsonify({"error": "Image files must be selected"}), 400

    if not allowed_file(image_file.filename) or not allowed_file(group_image_file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    image_filename = secure_filename(image_file.filename)
    group_image_filename = secure_filename(group_image_file.filename)

    image_path = os.path.join(UPLOAD_FOLDER, image_filename)
    group_image_path = os.path.join(UPLOAD_FOLDER, group_image_filename)

    image_file.save(image_path)
    group_image_file.save(group_image_path)

    # Compute pHash for the uploaded screenshot
    uploaded_phash = compute_phash(image_path)
    print(f"Uploaded pHash: {uploaded_phash}")
    if not uploaded_phash:
        return jsonify({"error": "Unable to compute image pHash"}), 400

    # Check if the same screenshot (or a very similar one) has already been used by another user for this task
    if is_duplicate_phash(uploaded_phash, task_id, user_id):
        return jsonify({"error": "Screenshot already used by another user"}), 400

    # Check if the broadcast list is valid (minimum recipient count)
    group_check = check_group_participants(group_image_path)
    print(f"Group Check Response: {group_check}")
    if not group_check.get("is_valid_group"):
        db.tasks.update_one(
            {"taskId": task_id},
            {"$set": {"status": "rejected", "updatedAt": datetime.utcnow()}}
        )
        return jsonify({
            "verified": False,
            "message": "Broadcast list must contain at least 2 recipients.",
            "participant_check": group_check,
            "status": "rejected"
        }), 200

    # Use the task's message (link) as the expected link for verification
    expected_link = task_doc.get("message", "")
    result = analyze_image_with_openai(image_path, expected_link)

    if result.get("verified"):
        # Update task status to accepted if verification succeeds
        db.tasks.update_one(
            {"taskId": task_id},
            {"$set": {
                "status": "accepted",
                "updatedAt": datetime.utcnow(),
                "verification_details": result.get("details", {})
            }}
        )

        # Save the verified task to task_history along with the userId, task_price, and image pHash
        history_doc = {
            "taskId": task_id,
            "userId": user_id,
            "matched_link": expected_link,
            "group_name": group_check.get("group_name"),
            "participant_count": group_check.get("participant_count"),
            "verification_details": result.get("details", {}),
            "verified": True,
            "verifiedAt": datetime.utcnow(),
            "task_price": int(task_doc.get("task_price", 0)),
            "image_phash": uploaded_phash
        }
        db.task_history.insert_one(history_doc)
        wallet_update = update_wallet_after_task(user_id, task_id, int(task_doc.get("task_price", 0)))
        if "error" in wallet_update:
            return jsonify(wallet_update), 400

        return jsonify({
            "verified": True,
            "matched_link": expected_link,
            "group_name": group_check.get("group_name"),
            "participant_count": group_check.get("participant_count"),
            "verification_details": result.get("details", {}),
            "status": "accepted"
        }), 200
    else:
        # Update task status to rejected if verification fails
        db.tasks.update_one(
            {"taskId": task_id},
            {"$set": {
                "status": "rejected",
                "updatedAt": datetime.utcnow(),
                "verification_details": result.get("details", {})
            }}
        )
        return jsonify({
            "verified": False,
            "message": "No matching link found in the broadcast message screenshot",
            "participant_check": group_check,
            "verification_details": result.get("details", {}),
            "status": "rejected"
        }), 200
