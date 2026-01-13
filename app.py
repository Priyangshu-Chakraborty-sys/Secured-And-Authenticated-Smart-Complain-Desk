from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import pandas as pd
import pickle
import os
import random
import string
import csv
from datetime import datetime
from sentence_transformers import SentenceTransformer
from functools import wraps
from blockchain_manager import BlockchainManager
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Load ML models with error handling
try:
    with open("complaint_model.pkl", "rb") as f:
        model = pickle.load(f)
    print("✅ ML model loaded successfully")
except FileNotFoundError:
    print("❌ complaint_model.pkl not found. Please run train_model.py first")
    model = None

try:
    embedding_model = SentenceTransformer("embedding_model")
    print("✅ Embedding model loaded successfully")
except:
    print("❌ Embedding model loading failed. Using fallback")
    embedding_model = None

try:
    dept_contacts = pd.read_csv("department_contacts.csv")
    print("✅ Department contacts loaded successfully")
except FileNotFoundError:
    print("❌ department_contacts.csv not found. Creating default")
    dept_contacts = pd.DataFrame({
        'Department': ['Water Supply', 'Electricity', 'Roads', 'Sanitation'],
        'Phone': ['+1234567890', '+1234567891', '+1234567892', '+1234567893'],
        'Email': ['water@city.gov', 'power@city.gov', 'roads@city.gov', 'sanitation@city.gov']
    })
    dept_contacts.to_csv("department_contacts.csv", index=False)

try:
    with open("classes.pkl", "rb") as f:
        all_departments = pickle.load(f)
    print("✅ Department classes loaded successfully")
except FileNotFoundError:
    print("❌ classes.pkl not found. Using default departments")
    all_departments = dept_contacts['Department'].tolist()

# Initialize blockchain manager
blockchain_manager = BlockchainManager()

def login_required(f):
    """Decorator to require blockchain wallet login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'wallet_address' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def home():
    """Home page - redirect to login if not authenticated"""
    if 'wallet_address' not in session:
        return redirect(url_for('login'))
    return render_template("index.html", wallet_address=session['wallet_address'])

@app.route("/login")
def login():
    """Wallet connection page"""
    return render_template("login.html")

@app.route("/api/connect_wallet", methods=["POST"])
def connect_wallet():
    """Handle wallet connection"""
    data = request.get_json()
    wallet_address = data.get('address')
    signature = data.get('signature', '')
    
    # Validate wallet address
    if not blockchain_manager.is_valid_address(wallet_address):
        return jsonify({"success": False, "message": "Invalid wallet address"})
    
    # Store in session
    session['wallet_address'] = wallet_address
    session['authenticated'] = True
    
    return jsonify({
        "success": True, 
        "message": "Wallet connected successfully",
        "address": wallet_address
    })

@app.route("/logout")
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('login'))

@app.route("/preview", methods=["POST"])
@login_required
def preview_complaint():
    """Preview complaint before submission"""
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    zip_code = request.form.get("zip", "").strip()
    complaint = request.form.get("complaint", "").strip()

    # ML prediction with fallback
    if model and embedding_model and complaint:
        try:
            complaint_embedding = embedding_model.encode([complaint])
            predicted_dept = model.predict(complaint_embedding)[0]
        except:
            predicted_dept = "General"
    else:
        predicted_dept = "General"

    # Get department info
    dept_info = dept_contacts[dept_contacts["Department"] == predicted_dept]
    if not dept_info.empty:
        dept_info = dept_info.iloc[0].to_dict()
    else:
        dept_info = {"Department": predicted_dept, "Phone": "N/A", "Email": "N/A"}

    departments_data = dept_contacts.to_dict(orient="records")

    return render_template(
        "preview.html",
        name=name, email=email, phone=phone, address=address,
        city=city, state=state, zip=zip_code, complaint=complaint,
        dept_info=dept_info, departments_data=departments_data,
        wallet_address=session['wallet_address']
    )

@app.route("/confirm", methods=["POST"])
@login_required
def confirm_complaint():
    """Confirm and submit complaint to blockchain"""
    # Get form data
    complaint_data = {
        'name': request.form.get("name", "").strip(),
        'email': request.form.get("email", "").strip(),
        'phone': request.form.get("phone", "").strip(),
        'address': request.form.get("address", "").strip(),
        'city': request.form.get("city", "").strip(),
        'state': request.form.get("state", "").strip(),
        'zip': request.form.get("zip", "").strip(),
        'complaint': request.form.get("complaint", "").strip()
    }
    
    department = (request.form.get("correct_department") or request.form.get("department", "")).strip()
    
    # Generate reference number
    ref_no = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    # Update ML model with feedback if possible
    if model and embedding_model and complaint_data['complaint'] and department:
        try:
            feedback_df = pd.DataFrame([[complaint_data['complaint'], department]], 
                                     columns=["complaint_text", "product"])
            
            # Save to CSV for future training
            if os.path.exists("consumer_complaints.csv"):
                feedback_df.to_csv("consumer_complaints.csv", mode="a", header=False, 
                                 index=False, quoting=csv.QUOTE_MINIMAL)
            else:
                feedback_df.to_csv("consumer_complaints.csv", mode="w", header=True, 
                                 index=False, quoting=csv.QUOTE_MINIMAL)
            
            # Incremental learning
            complaint_embedding = embedding_model.encode([complaint_data['complaint']])
            model.partial_fit(complaint_embedding, [department], classes=all_departments)
            
            # Save updated model
            with open("complaint_model.pkl", "wb") as f:
                pickle.dump(model, f)
        except Exception as e:
            print(f"Error updating ML model: {e}")
    
    # Submit to blockchain
    blockchain_result = blockchain_manager.submit_complaint_to_blockchain(
        ref_no, complaint_data, department, session['wallet_address']  # Pass wallet address
    )
    
    # Save to local CSV as backup with proper wallet address mapping
    file_exists = os.path.exists("complaints.csv")
    df = pd.DataFrame([{
        "Reference No": ref_no,
        "Wallet Address": session['wallet_address'],
        "Name": complaint_data['name'],
        "Email": complaint_data['email'],
        "Phone": complaint_data['phone'],
        "Address": complaint_data['address'],
        "City": complaint_data['city'],
        "State": complaint_data['state'],
        "Zip": complaint_data['zip'],
        "Complaint": complaint_data['complaint'],
        "Department": department,
        "Status": "Submitted",
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Blockchain Status": "Success" if blockchain_result["success"] else "Failed",
        "Transaction Hash": blockchain_result.get("tx_hash", "N/A")
    }])
    
    try:
        df.to_csv("complaints.csv", mode="a", header=not file_exists, 
                  index=False, quoting=csv.QUOTE_MINIMAL)
        print(f"✅ Complaint {ref_no} saved to CSV for wallet {session['wallet_address']}")
    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")
    
    return render_template("confirmation.html", 
                         ref_no=ref_no,
                         blockchain_result=blockchain_result,
                         wallet_address=session['wallet_address'])

@app.route("/track", methods=["GET", "POST"])
@login_required
def track_complaint():
    """Track complaint by reference number"""
    result = None
    blockchain_data = None
    
    if request.method == "POST":
        ref_no = request.form.get("ref_no", "").strip().upper()  # Ensure uppercase
        print(f"🔍 Tracking complaint: {ref_no} for wallet: {session['wallet_address']}")
        
        # Check local CSV first for faster lookup
        local_complaint = None
        if os.path.exists("complaints.csv"):
            try:
                df = pd.read_csv("complaints.csv", quoting=csv.QUOTE_MINIMAL, on_bad_lines="skip")
                # Convert Reference No to string to ensure proper comparison
                df["Reference No"] = df["Reference No"].astype(str)
                
                # Find complaint by reference number and wallet address
                local_complaint = df[
                    (df["Reference No"] == ref_no) & 
                    (df["Wallet Address"].str.lower() == session['wallet_address'].lower())
                ]
                
                if not local_complaint.empty:
                    result = local_complaint.iloc[0].to_dict()
                    print(f"✅ Found complaint in local CSV: {ref_no}")
                else:
                    print(f"❌ Complaint not found in local CSV or wrong owner: {ref_no}")
                    
            except Exception as e:
                print(f"❌ Error reading local complaints: {e}")
        
        # Check blockchain
        blockchain_data = blockchain_manager.get_complaint_from_blockchain(ref_no)
        if blockchain_data:
            print(f"✅ Found complaint on blockchain: {ref_no}")
            # Verify ownership
            is_owner = blockchain_manager.verify_complaint_ownership(ref_no, session['wallet_address'])
            if not is_owner:
                print(f"❌ Wallet {session['wallet_address']} is not owner of complaint {ref_no}")
                result = "not_authorized"
                blockchain_data = None
        else:
            print(f"❌ Complaint not found on blockchain: {ref_no}")
        
        # Determine final result
        if result is None and blockchain_data is None:
            result = "not_found"
        elif result == "not_authorized":
            pass  # Keep as is
        elif blockchain_data and result is None:
            result = "blockchain_only"
    
    return render_template("track.html", 
                         result=result, 
                         blockchain_data=blockchain_data,
                         wallet_address=session['wallet_address'],
                         network_info=blockchain_manager.get_network_info())

@app.route("/history")
@login_required
def view_history():
    """View user's complaint history"""
    user_complaints = []
    wallet_address = session['wallet_address']
    
    print(f"🔍 Loading history for wallet: {wallet_address}")
    
    # Get complaints from local CSV first (faster)
    if os.path.exists("complaints.csv"):
        try:
            df = pd.read_csv("complaints.csv", quoting=csv.QUOTE_MINIMAL, on_bad_lines="skip")
            # Filter by wallet address (case insensitive)
            user_df = df[df["Wallet Address"].str.lower() == wallet_address.lower()]
            
            if not user_df.empty:
                user_complaints = user_df.to_dict(orient="records")
                # Sort by date (newest first)
                user_complaints = sorted(user_complaints, 
                                       key=lambda x: x.get('Date', ''), 
                                       reverse=True)
                print(f"✅ Found {len(user_complaints)} complaints in local CSV")
            else:
                print(f"❌ No complaints found in local CSV for wallet: {wallet_address}")
                
        except Exception as e:
            print(f"❌ Error reading complaints history from CSV: {e}")
    
    # Also try to get from blockchain (as backup/verification)
    try:
        ref_numbers = blockchain_manager.get_user_complaints(wallet_address)
        print(f"📊 Blockchain reports {len(ref_numbers)} complaints for this wallet")
        
        # If we have blockchain data but no local data, create minimal records
        if ref_numbers and not user_complaints:
            for ref_no in ref_numbers:
                blockchain_complaint = blockchain_manager.get_complaint_from_blockchain(ref_no)
                if blockchain_complaint:
                    user_complaints.append({
                        "Reference No": ref_no,
                        "Department": blockchain_complaint.get('department', 'Unknown'),
                        "Status": blockchain_complaint.get('status', 'Unknown'),
                        "Date": blockchain_complaint.get('formatted_date', 'Unknown'),
                        "Name": "Blockchain Record",
                        "Complaint": "Details stored on blockchain",
                        "Blockchain Status": "Success"
                    })
    except Exception as e:
        print(f"❌ Error reading from blockchain: {e}")
    
    print(f"📋 Returning {len(user_complaints)} complaints for history view")
    
    return render_template("history.html", 
                         complaints=user_complaints,
                         wallet_address=wallet_address,
                         network_info=blockchain_manager.get_network_info())

@app.route("/api/blockchain_status")
@login_required
def blockchain_status():
    """API endpoint to check blockchain connection status"""
    return jsonify({
        "connected": blockchain_manager.is_connected(),
        "contract_address": Config.CONTRACT_ADDRESS,
        "user_address": session.get('wallet_address')
    })

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('contracts', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)