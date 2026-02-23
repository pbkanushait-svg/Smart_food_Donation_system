from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret"
app.config['UPLOAD_FOLDER'] = 'static/uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# In-memory "database"
users = {}  # username -> {password, role, address}
donations = []  # {'id', 'donor_username', 'filename', 'freshness', 'address', 'timestamp', 'receivers', 'accepted_by'}
donation_counter = 1
chats = []  # {'sender', 'receiver', 'message', 'timestamp'}

# --- Mock freshness check ---
def predict_freshness(filepath):
    return "Fresh" if os.path.getsize(filepath) % 2 == 0 else "Spoiled"

# --- Mock nearby check ---
def is_nearby(addr1, addr2):
    return True  # Simplified

# --- Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        address = request.form.get('address')
        if not username or not password or not role or not address:
            return "All fields are required!"
        if username in users:
            return "Username already exists!"
        users[username] = {'password': password, 'role': role, 'address': address}
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users and users[username]['password']==password:
            session['username'] = username
            session['role'] = users[username]['role']
            if users[username]['role'] == 'donor':
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('receiver_dashboard'))
        else:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/dashboard', methods=['GET','POST'])
def dashboard():
    if 'username' not in session or session.get('role') != 'donor':
        return redirect(url_for('login'))

    global donation_counter
    current_user = session['username']
    freshness = None
    filename = None
    message = None

    # --- Upload food ---
    if request.method == 'POST' and 'file' in request.files:
        file = request.files.get('file')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            freshness = predict_freshness(filepath)
            donor_address = users[current_user]['address']

            notified = [u for u, info in users.items() if info['role']=='receiver' and is_nearby(donor_address, info['address'])]

            donations.append({
                'id': donation_counter,
                'donor_username': current_user,
                'filename': filename,
                'freshness': freshness,
                'address': donor_address,
                'timestamp': datetime.now(),
                'receivers': notified,
                'accepted_by': None
            })
            donation_counter += 1

            if freshness=="Fresh":
                if notified:
                    message = f"Food is Fresh! Notified receivers: {', '.join(notified)}"
                else:
                    message = "Food is Fresh! No receivers nearby."
            else:
                message = "Food is Spoiled! Cannot notify receivers."

    # --- Chat submission ---
    if request.method=='POST' and 'chat_message' in request.form:
        chat_msg = request.form['chat_message']
        chat_receiver = request.form['chat_receiver']
        chats.append({
            'sender': current_user,
            'receiver': chat_receiver,
            'message': chat_msg,
            'timestamp': datetime.now()
        })

    user_chats = [c for c in chats if c['sender']==current_user or c['receiver']==current_user]

    return render_template(
        'dashboard.html',
        freshness=freshness,
        filename=filename,
        message=message,
        donations=donations,
        users=[u for u in users if u!=current_user],
        chats=user_chats,
        current_user=current_user,
        role='donor'
    )

@app.route('/receiver_dashboard', methods=['GET','POST'])
def receiver_dashboard():
    if 'username' not in session or session.get('role') != 'receiver':
        return redirect(url_for('login'))

    current_user = session['username']
    nearby_donations = []
    message = None

    # --- Filter nearby fresh donations ---
    receiver_address = users[current_user]['address']
    for d in donations:
        if d['freshness']=='Fresh' and is_nearby(d['address'], receiver_address):
            nearby_donations.append(d)

    # --- Accept donation ---
    if request.method=='POST' and 'accept_donation_id' in request.form:
        did = int(request.form['accept_donation_id'])
        for d in donations:
            if d['id']==did:
                d['accepted_by'] = current_user
                message = f"You accepted donation from {d['donor_username']}!"
                break

    user_chats = [c for c in chats if c['sender']==current_user or c['receiver']==current_user]

    return render_template(
        'receiver_dashboard.html',
        donations=nearby_donations,
        users=[u for u in users if u!=current_user],
        chats=user_chats,
        current_user=current_user,
        role='receiver',
        message=message
    )

@app.route('/chat/<other_user>', methods=['GET','POST'])
def chat(other_user):
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = session['username']
    role = session.get('role')
    image = None

    # --- Find latest food image between donor and receiver ---
    for d in reversed(donations):
        if (role=='donor' and other_user in d['receivers']) or \
           (role=='receiver' and d['donor_username']==other_user and d['freshness']=='Fresh'):
            image = d['filename']
            break

    # --- Send chat ---
    if request.method=='POST' and 'chat_message' in request.form:
        chat_msg = request.form['chat_message']
        chats.append({
            'sender': current_user,
            'receiver': other_user,
            'message': chat_msg,
            'timestamp': datetime.now()
        })

    # --- Filter all chats between current_user and other_user ---
    user_chats = [c for c in chats if 
                  (c['sender']==current_user and c['receiver']==other_user) or
                  (c['sender']==other_user and c['receiver']==current_user)]

    # --- Pass donations that belong to this chat for accept/accepted display ---
    related_donations = []
    for d in donations:
        if (role=='donor' and d['donor_username']==current_user and other_user in d['receivers']) or \
           (role=='receiver' and d['donor_username']==other_user):
            related_donations.append(d)

    return render_template(
        'chat.html',
        receiver=other_user,
        chats=user_chats,
        image=image,
        current_user=current_user,
        role=role,
        donations=related_donations
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__=='__main__':
    app.run(debug=True)
