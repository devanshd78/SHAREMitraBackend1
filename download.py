# download.py

from flask import Blueprint, send_file
from pymongo import MongoClient
import pandas as pd
import os

client = MongoClient("mongodb://localhost:27017")
db = client["enoylity"]

download_bp = Blueprint('download', __name__, url_prefix='/download')

def export_users():
    users_cursor = db.users.find({}, {
        '_id': 0, 'userId': 1, 'name': 1, 'email': 1, 'phone': 1, 'state': 1,
        'city': 1, 'dob': 1, 'referralCode': 1, 'referredBy': 1, 'referralCount': 1
    })
    filename = 'users_data.xlsx'
    pd.DataFrame(list(users_cursor)).to_excel(filename, index=False)
    return filename


def export_tasks():
    tasks_cursor = db.tasks.find({}, {
        '_id': 0, 'taskId': 1, 'title': 1, 'description': 1, 'message': 1, 'task_price': 1
    })
    filename = 'tasks_data.xlsx'
    pd.DataFrame(list(tasks_cursor)).to_excel(filename, index=False)
    return filename


def export_payouts():
    payouts_cursor = db.payouts.find({}, {
        '_id': 0, 'userId': 1, 'payout_id': 1, 'amount': 1, 'status_detail': 1, 'fund_account_type': 1
    })
    payouts_list = list(payouts_cursor)

    for payout in payouts_list:
        user = db.users.find_one({'userId': payout['userId']}, {'_id': 0, 'name': 1})
        payout['userName'] = user['name'] if user else 'Unknown'

    df_payouts = pd.DataFrame(payouts_list)
    df_payouts.rename(columns={'payout_id': 'payoutId', 'status_detail': 'status'}, inplace=True)
    filename = 'payouts_data.xlsx'
    df_payouts.to_excel(filename, index=False)
    return filename


@download_bp.route('/users', methods=['GET'])
def download_users():
    filename = export_users()
    response = send_file(filename, as_attachment=True)
    os.remove(filename)
    return response


@download_bp.route('/tasks', methods=['GET'])
def download_tasks():
    filename = export_tasks()
    response = send_file(filename, as_attachment=True)
    os.remove(filename)
    return response


@download_bp.route('/payouts', methods=['GET'])
def download_payouts():
    filename = export_payouts()
    response = send_file(filename, as_attachment=True)
    os.remove(filename)
    return response