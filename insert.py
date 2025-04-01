from flask import Flask, jsonify
from flask_pymongo import PyMongo

app = Flask(__name__)

# Configure MongoDB URI
app.config["MONGO_URI"] = "mongodb://localhost:27017/enoylity"  # Replace with your MongoDB URI
mongo = PyMongo(app)

# State and city data (the same data you provided)
data = [
    {
  "states": [
    {
      "name": "Andhra Pradesh",
      "cities": [
        "Visakhapatnam",
        "Vijayawada",
        "Guntur",
        "Kakinada",
        "Tirupati",
        "Nellore",
        "Rajahmundry",
        "Anantapur",
        "Chittoor",
        "Kadapa"
      ]
    },
    {
      "name": "Arunachal Pradesh",
      "cities": [
        "Itanagar",
        "Tawang",
        "Naharlagun",
        "Ziro",
        "Bomdila",
        "Tezu",
        "Pasighat"
      ]
    },
    {
      "name": "Assam",
      "cities": [
        "Guwahati",
        "Silchar",
        "Dibrugarh",
        "Jorhat",
        "Nagaon",
        "Tinsukia",
        "Duliajan",
        "Bongaigaon"
      ]
    },
    {
      "name": "Bihar",
      "cities": [
        "Patna",
        "Gaya",
        "Bhagalpur",
        "Muzaffarpur",
        "Munger",
        "Purnia",
        "Darbhanga",
        "Bihar Sharif"
      ]
    },
    {
      "name": "Chhattisgarh",
      "cities": [
        "Raipur",
        "Bhilai",
        "Korba",
        "Bilaspur",
        "Durg",
        "Raigarh",
        "Jagdalpur",
        "Ambikapur"
      ]
    },
    {
      "name": "Goa",
      "cities": [
        "Panaji",
        "Margao",
        "Vasco da Gama",
        "Mapusa",
        "Ponda",
        "Bicholim"
      ]
    },
    {
      "name": "Gujarat",
      "cities": [
        "Ahmedabad",
        "Surat",
        "Vadodara",
        "Rajkot",
        "Bhavnagar",
        "Anand",
        "Gandhinagar",
        "Jamnagar",
        "Junagadh"
      ]
    },
    {
      "name": "Haryana",
      "cities": [
        "Chandigarh",
        "Gurgaon",
        "Faridabad",
        "Karnal",
        "Ambala",
        "Hisar",
        "Panipat",
        "Sirsa",
        "Rewari"
      ]
    },
    {
      "name": "Himachal Pradesh",
      "cities": [
        "Shimla",
        "Manali",
        "Kullu",
        "Solan",
        "Mandi",
        "Dharamshala",
        "Kasauli"
      ]
    },
    {
      "name": "Jharkhand",
      "cities": [
        "Ranchi",
        "Jamshedpur",
        "Dhanbad",
        "Bokaro",
        "Hazaribagh",
        "Deoghar",
        "Giridih",
        "Dumka"
      ]
    },
    {
      "name": "Karnataka",
      "cities": [
        "Bengaluru",
        "Mysuru",
        "Mangaluru",
        "Hubballi",
        "Belagavi",
        "Davangere",
        "Kalaburagi",
        "Udupi"
      ]
    },
    {
      "name": "Kerala",
      "cities": [
        "Thiruvananthapuram",
        "Kochi",
        "Kozhikode",
        "Kollam",
        "Thrissur",
        "Alappuzha",
        "Kannur",
        "Kottayam",
        "Palakkad"
      ]
    },
    {
      "name": "Madhya Pradesh",
      "cities": [
        "Bhopal",
        "Indore",
        "Gwalior",
        "Jabalpur",
        "Ujjain",
        "Sagar",
        "Ratlam",
        "Khandwa"
      ]
    },
    {
      "name": "Maharashtra",
      "cities": [
        "Mumbai",
        "Pune",
        "Nagpur",
        "Nashik",
        "Aurangabad",
        "Thane",
        "Solapur",
        "Nanded",
        "Kolhapur",
        "Jalgaon"
      ]
    },
    {
      "name": "Manipur",
      "cities": [
        "Imphal",
        "Thoubal",
        "Churachandpur",
        "Bishnupur",
        "Moirang"
      ]
    },
    {
      "name": "Meghalaya",
      "cities": [
        "Shillong",
        "Tura",
        "Jowai",
        "Nongpoh"
      ]
    },
    {
      "name": "Mizoram",
      "cities": [
        "Aizawl",
        "Lunglei",
        "Champhai",
        "Kolasib"
      ]
    },
    {
      "name": "Nagaland",
      "cities": [
        "Kohima",
        "Dimapur",
        "Mokokchung",
        "Wokha",
        "Zunheboto"
      ]
    },
    {
      "name": "Odisha",
      "cities": [
        "Bhubaneswar",
        "Cuttack",
        "Rourkela",
        "Berhampur",
        "Sambalpur",
        "Puri"
      ]
    },
    {
      "name": "Punjab",
      "cities": [
        "Chandigarh",
        "Amritsar",
        "Ludhiana",
        "Jalandhar",
        "Patiala",
        "Bathinda",
        "Mohali",
        "Hoshiarpur"
      ]
    },
    {
      "name": "Rajasthan",
      "cities": [
        "Jaipur",
        "Udaipur",
        "Jodhpur",
        "Kota",
        "Ajmer",
        "Bikaner",
        "Jaisalmer",
        "Alwar",
        "Bharatpur"
      ]
    },
    {
      "name": "Sikkim",
      "cities": [
        "Gangtok",
        "Namchi",
        "Jorethang"
      ]
    },
    {
      "name": "Tamil Nadu",
      "cities": [
        "Chennai",
        "Coimbatore",
        "Madurai",
        "Tiruchirappalli",
        "Salem",
        "Erode",
        "Tirunelveli",
        "Vellore"
      ]
    },
    {
      "name": "Telangana",
      "cities": [
        "Hyderabad",
        "Warangal",
        "Karimnagar",
        "Khammam",
        "Nizamabad",
        "Mahbubnagar"
      ]
    },
    {
      "name": "Tripura",
      "cities": [
        "Agartala",
        "Udaipur",
        "Kailashahar"
      ]
    },
    {
      "name": "Uttar Pradesh",
      "cities": [
        "Lucknow",
        "Kanpur",
        "Agra",
        "Varanasi",
        "Meerut",
        "Prayagraj",
        "Ghaziabad",
        "Noida"
      ]
    },
    {
      "name": "Uttarakhand",
      "cities": [
        "Dehradun",
        "Haridwar",
        "Nainital",
        "Rishikesh",
        "Roorkee"
      ]
    },
    {
      "name": "West Bengal",
      "cities": [
        "Kolkata",
        "Howrah",
        "Siliguri",
        "Durgapur",
        "Asansol",
        "Kalyani",
        "Berhampore",
        "Malda"
      ]
    },
    {
      "name": "Andaman and Nicobar Islands",
      "cities": [
        "Port Blair",
        "Car Nicobar",
        "Havelock"
      ]
    },
    {
      "name": "Chandigarh",
      "cities": [
        "Chandigarh"
      ]
    },
    {
      "name": "Dadra and Nagar Haveli and Daman and Diu",
      "cities": [
        "Daman",
        "Diu"
      ]
    },
    {
      "name": "Lakshadweep",
      "cities": [
        "Kavaratti"
      ]
    },
    {
      "name": "Delhi",
      "cities": [
        "New Delhi",
        "Dwarka",
        "Rohini",
        "Janakpuri",
        "Vasant Vihar"
      ]
    },
    {
      "name": "Puducherry",
      "cities": [
        "Puducherry",
        "Karaikal",
        "Mahe",
        "Yanam"
      ]
    },
    {
      "name": "Ladakh",
      "cities": [
        "Leh",
        "Kargil"
      ]
    },

  ]
}
]

@app.route('/insert_state_city', methods=['POST'])
def insert_state_city():
    try:
        # Insert the data into MongoDB collection (you can name the collection "states")
        mongo.db.states.insert_many(data)
        return jsonify({"message": "Data inserted successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
