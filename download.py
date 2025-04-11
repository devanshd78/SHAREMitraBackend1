import os
import datetime
import logging
from flask import Blueprint, send_file, jsonify
from pymongo import MongoClient
import pandas as pd
from db import db  # Ensure this imports your configured PyMongo instance
from bson import ObjectId
from utils import format_response  # Centralized response formatter

download_bp = Blueprint('download', __name__, url_prefix='/download')

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def export_users():
    """Export selected user fields to an Excel file."""
    users_cursor = db.users.find({}, {
        '_id': 0, 
        'userId': 1, 
        'name': 1, 
        'email': 1, 
        'phone': 1, 
        'stateName': 1, 
        'cityName': 1, 
        'dob': 1, 
        'referralCode': 1, 
        'referredBy': 1, 
        'referralCount': 1,
        'createdAt': 1,
        'updatedAt': 1
    })
    
    filename = 'users_data.xlsx'
    df = pd.DataFrame(list(users_cursor))
    
    # Format datetime columns if they exist.
    if not df.empty:
        if 'createdAt' in df.columns:
            df['createdAt'] = df['createdAt'].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime.datetime) else x)
        if 'updatedAt' in df.columns:
            df['updatedAt'] = df['updatedAt'].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime.datetime) else x)
    
    df.to_excel(filename, index=False)
    return filename

def export_tasks():
    """Export selected task fields to an Excel file."""
    tasks_cursor = db.tasks.find({}, {
        '_id': 0, 
        'taskId': 1, 
        'title': 1, 
        'description': 1, 
        'message': 1, 
        'task_price': 1
    })
    filename = 'tasks_data.xlsx'
    pd.DataFrame(list(tasks_cursor)).to_excel(filename, index=False)
    return filename

def export_payouts():
    """
    Export payouts with additional details:
      - userId and the associated userName (fetched from db.users)
      - payout_id (renamed to payoutId)
      - amount, status_detail (renamed to status), fund_account_type, fund_account_id
      - created_at formatted as a readable string.
    """
    payouts_cursor = db.payouts.find({}, {
        '_id': 0, 
        'userId': 1, 
        'payout_id': 1, 
        'amount': 1, 
        'status_detail': 1, 
        'fund_account_type': 1,
        'fund_account_id': 1,
        'created_at': 1
    })
    
    payouts_list = list(payouts_cursor)
    for payout in payouts_list:
        user = db.users.find_one({'userId': payout['userId']}, {'_id': 0, 'name': 1})
        payout['userName'] = user.get('name') if user else 'Unknown'
        if 'created_at' in payout and isinstance(payout['created_at'], datetime.datetime):
            payout['created_at'] = payout['created_at'].strftime("%Y-%m-%d %H:%M:%S")
    
    df = pd.DataFrame(payouts_list)
    # Rename fields for clarity.
    df.rename(columns={
        'payout_id': 'payoutId', 
        'status_detail': 'status', 
        'created_at': 'withdraw_time'
    }, inplace=True)
    
    filename = 'payouts_data.xlsx'
    df.to_excel(filename, index=False)
    return filename

@download_bp.route('/users', methods=['GET'])
def download_users():
    """Download the exported users data as an Excel file."""
    try:
        filename = export_users()
        response = send_file(filename, as_attachment=True)
        # Clean up the temporary file.
        os.remove(filename)
        return response
    except Exception as e:
        logger.exception("Error exporting users data: %s", e)
        # Return a JSON formatted error response.
        return format_response(False, "Server error while exporting users data.", {"message": str(e)}, 500)

@download_bp.route('/tasks', methods=['GET'])
def download_tasks():
    """Download the exported tasks data as an Excel file."""
    try:
        filename = export_tasks()
        response = send_file(filename, as_attachment=True)
        os.remove(filename)
        return response
    except Exception as e:
        logger.exception("Error exporting tasks data: %s", e)
        return format_response(False, "Server error while exporting tasks data.", {"message": str(e)}, 500)

@download_bp.route('/payouts', methods=['GET'])
def download_payouts():
    """Download the exported payouts data as an Excel file."""
    try:
        filename = export_payouts()
        response = send_file(filename, as_attachment=True)
        os.remove(filename)
        return response
    except Exception as e:
        logger.exception("Error exporting payouts data: %s", e)
        return format_response(False, "Server error while exporting payouts data.", {"message": str(e)}, 500)