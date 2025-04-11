import re
import datetime
from flask import Blueprint, request
from bson import ObjectId
from db import db  # Ensure this imports your configured PyMongo instance
from utils import format_response

contact_bp = Blueprint("contact", __name__, url_prefix="/contact")

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

@contact_bp.route("/store", methods=["POST"])
def store_contact():
    """
    POST /contact/store
    Stores the provided contact details in the contacts collection.
    Expected JSON Body:
    {
        "fullname": "John Doe",
        "email": "john@example.com",
        "phonemumber": "1234567890",
        "companyname": "Example Inc.",
        "address": "123 Main St",
        "message": "I have a question",
        "subject": "Inquiry",
        "state": "California",
        "city": "Los Angeles"
    }
    """
    try:
        data = request.get_json() or {}

        # Extract and strip required fields
        fullname    = data.get("fullname", "").strip()
        email       = data.get("email", "").strip()
        phonemumber = data.get("phonemumber", "").strip()
        subject     = data.get("subject", "").strip()
        state       = data.get("state", "").strip()
        city        = data.get("city", "").strip()
        address     = data.get("address", "").strip()


        # Optional fields
        companyname = data.get("companyname", "").strip()
        message     = data.get("message", "").strip()
        

        # Validate required fields
        if not fullname:
            return format_response(False, "fullname is required.", None, 400)
        if not email:
            return format_response(False, "email is required.", None, 400)
        if not phonemumber:
            return format_response(False, "phonemumber is required.", None, 400)
        if not subject:
            return format_response(False, "subject is required.", None, 400)
        if not state:
            return format_response(False, "state is required.", None, 400)
        if not city:
            return format_response(False, "city is required.", None, 400)
        if not address:
            return format_response(False, "address is required.", None, 400)



        # Prepare the contact document
        contact_doc = {
            "fullname": fullname,
            "email": email,
            "phonemumber": phonemumber,
            "companyname": companyname,
            "address": address,
            "message": message,
            "subject": subject,
            "state": state,
            "city": city,
            "createdAt": datetime.datetime.utcnow()
        }

        result = db.contacts.insert_one(contact_doc)
        return format_response(True, "Contact details stored successfully.", {"contactId": str(result.inserted_id)}, 201)

    except Exception as e:
        return format_response(False, "Server error", {"message": str(e)}, 500)

@contact_bp.route("/india_states", methods=["GET"])
def get_india_states():
    """
    GET /contact/india_states?state=Maharashtra
    - If a query parameter 'state' is provided, returns that state's stateId, name and its list of cities.
    - If no state parameter is provided, returns a list of all Indian states with their stateIds, names, and cities.
    """
    try:
        state_query = request.args.get("state")

        if state_query:
            # Search for a specific state by 'name' (case-insensitive)
            state_doc = db.india_states.find_one({
                "name": {"$regex": f"^{re.escape(state_query)}$", "$options": "i"}
            })
            if not state_doc:
                return format_response(False, "State not found.", None, 404)

            state_doc = convert_objectids(state_doc)
            response_data = {
                "stateId": state_doc.get("stateId"),
                "state": state_doc.get("name"),
                "cities": state_doc.get("cities", [])
            }
            return format_response(True, "State found successfully.", response_data, 200)
        else:
            # Return all states and their cities
            cursor = db.india_states.find()
            states_list = list(cursor)
            states_list = convert_objectids(states_list)

            response_data = {
                "states": [
                    {
                        "stateId": doc.get("stateId"),
                        "state": doc.get("name"),
                        "cities": doc.get("cities", [])
                    }
                    for doc in states_list
                ]
            }
            return format_response(True, "States retrieved successfully.", response_data, 200)

    except Exception as e:
        return format_response(False, "Server error", {"message": str(e)}, 500)