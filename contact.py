from flask import Blueprint, request, jsonify
import datetime
from db import db  # Ensure this imports your configured PyMongo instance
from bson import ObjectId

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
    JSON Body:
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
    Stores the provided contact details in the contacts collection.
    """
    try:
        data = request.get_json() or {}
        
        # Required fields
        fullname    = data.get("fullname", "").strip()
        email       = data.get("email", "").strip()
        phonemumber = data.get("phonemumber", "").strip()
        subject     = data.get("subject", "").strip()
        
        # Optional fields
        companyname = data.get("companyname", "").strip()
        address     = data.get("address", "").strip()
        message     = data.get("message", "").strip()
        state       = data.get("state", "").strip()
        city        = data.get("city", "").strip()
        
        if not fullname:
            return jsonify({"error": "fullname is required."}), 400
        if not email:
            return jsonify({"error": "email is required."}), 400
        if not phonemumber:
            return jsonify({"error": "phonemumber is required."}), 400
        if not subject:
            return jsonify({"error": "subject is required."}), 400

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
        
        return jsonify({
            "message": "Contact details stored successfully.",
            "contactId": str(result.inserted_id)
        }), 201

    except Exception as e:
        return jsonify({"error": "Server error", "message": str(e)}), 500


@contact_bp.route("/india_states", methods=["GET"])
def get_india_states():
    """
    GET /contact/india_states?state=Maharashtra
    - If a query parameter 'state' is provided, returns that state's name and its list of cities.
    - If no state parameter is provided, returns a list of all Indian states with their cities.
    """
    try:
        state_query = request.args.get("state")
        
        if state_query:
            # Search for a specific state by 'name' (case-insensitive)
            state_doc = db.india_states.find_one({
                "name": {"$regex": f"^{state_query}$", "$options": "i"}
            })
            if not state_doc:
                return jsonify({"error": "State not found."}), 404

            state_doc = convert_objectids(state_doc)
            # Return the matching state's name and cities
            return jsonify({
                "state": state_doc.get("name"),
                "cities": state_doc.get("cities", [])
            }), 200
        else:
            # Return all states and their cities
            cursor = db.india_states.find()
            states_list = list(cursor)
            states_list = convert_objectids(states_list)
            
            # Each document has "name" and "cities"
            # Return them in a consistent format
            return jsonify({
                "states": [
                    {
                        "name": doc.get("name"),
                        "cities": doc.get("cities", [])
                    }
                    for doc in states_list
                ]
            }), 200

    except Exception as e:
        return jsonify({"error": "Server error", "message": str(e)}), 500
