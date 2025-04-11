from flask import Flask, jsonify
from flask_cors import CORS
from task_list import task_bp   
from image_analysis import image_analysis_bp  
from payment_details import payment_details_bp
from user import user_bp
from admin import admin_bp
from dashboard import dashboard_bp
from payout import payout_bp
from contact import contact_bp
from download import download_bp
from wallet import wallet_bp
from utils import utils_bp
app = Flask(__name__)

# Configure Cross-Origin Resource Sharing (CORS)
CORS(app, resources={r"/*": {"origins": "*"}})



# Register blueprints for your endpoints.
app.register_blueprint(task_bp)
app.register_blueprint(image_analysis_bp, url_prefix="/image")
app.register_blueprint(payment_details_bp)
app.register_blueprint(user_bp)
app.register_blueprint(payout_bp)
app.register_blueprint(contact_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(download_bp)
app.register_blueprint(wallet_bp)
app.register_blueprint(utils_bp)

# Global Error Handler: Resource Not Found


if __name__ == '__main__':
    app.run(debug=True)