from flask import Flask
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



app = Flask(__name__)

cors = CORS(app, resources={r"/*": {"origins": "*"}})

app.register_blueprint(task_bp)
app.register_blueprint(image_analysis_bp, url_prefix="/image")
app.register_blueprint(payment_details_bp)
app.register_blueprint(user_bp)
app.register_blueprint(payout_bp)
app.register_blueprint(contact_bp)
app.register_blueprint(admin_bp,url_prefix = "/admin")
app.register_blueprint(dashboard_bp)
app.register_blueprint(download_bp)
app.register_blueprint(wallet_bp)


if __name__ == '__main__':
    app.run(debug=True)