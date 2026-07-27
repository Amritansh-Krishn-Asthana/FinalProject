import os
import time
import cv2
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, Response, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import database

app = Flask(__name__)
app.secret_key = "literary_oasis_secret_key"

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database & load cleaned Books.csv
database.init_db()

# Optimized OpenCV Camera Setup
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.03)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in as an official first.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- AUTH ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        if database.create_user(username, email, hashed_pw):
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))
        else:
            flash("Username or email already exists.", "danger")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = database.get_user_by_username(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['login_time'] = datetime.now().strftime("%I:%M %p (%d %b %Y)")
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials.", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))

# --- MAIN APP ROUTES ---

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    raw_records = database.get_all_records()
    metrics = database.get_dashboard_metrics()
    
    processed_records = []
    now = datetime.now()
    overdue_count = 0

    for rec in raw_records:
        try:
            issued_date = datetime.strptime(str(rec['issued_at']), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            issued_date = datetime.now()

        due_date = issued_date + timedelta(days=7)
        is_overdue = now > due_date
        if is_overdue:
            overdue_count += 1

        processed_records.append({
            'id': rec['id'],
            'college_id': rec['college_id'],
            'student_name': rec['student_name'],
            'book_title': rec['book_title'],
            'image_path': rec['image_path'],
            'issued_at': issued_date.strftime("%b %d, %Y"),
            'due_date': due_date.strftime("%b %d, %Y"),
            'is_overdue': is_overdue
        })

    return render_template('dashboard.html', 
                           records=processed_records[:5], 
                           metrics=metrics, 
                           overdue_count=overdue_count)

@app.route('/catalog')
@login_required
def catalog():
    books = database.get_all_books()
    return render_template('catalog.html', books=books)

@app.route('/issue-page')
@login_required
def issue_page():
    available_books = database.get_available_books()
    return render_template('issue.html', books=available_books)

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/issue', methods=['POST'])
@login_required
def issue_book():
    college_id = request.form.get('college_id', '').strip()
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    branch = request.form.get('branch', '').strip()
    semester = request.form.get('semester', '').strip()
    book_title = request.form.get('book_title', '').strip()

    if not all([college_id, name, phone, branch, semester, book_title]):
        flash("All form fields are required!", "danger")
        return redirect(url_for('issue_page'))

    # Capture frame from webcam
    success, frame = camera.read()
    if not success or frame is None:
        flash("Webcam error. Could not capture photo.", "danger")
        return redirect(url_for('issue_page'))

    filename = f"{college_id}_{int(time.time())}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    cv2.imwrite(filepath, frame)

    relative_img_path = f"uploads/{filename}"
    database.add_issue_record(college_id, name, phone, branch, semester, book_title, relative_img_path, session['username'])
    
    # Deduct 1 count from database & update Books.csv
    database.deduct_book_quantity(book_title)

    flash(f"Book '{book_title}' issued to {name}! Quantity updated.", "success")
    return redirect(url_for('records'))

@app.route('/records')
@login_required
def records():
    raw_records = database.get_all_records()
    processed_records = []
    now = datetime.now()

    for rec in raw_records:
        try:
            issued_date = datetime.strptime(str(rec['issued_at']), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            issued_date = datetime.now()

        due_date = issued_date + timedelta(days=7)
        is_overdue = now > due_date

        processed_records.append({
            'id': rec['id'],
            'college_id': rec['college_id'],
            'student_name': rec['student_name'],
            'phone': rec['phone_number'],
            'branch': rec['branch'],
            'semester': rec['semester'],
            'book_title': rec['book_title'],
            'image_path': rec['image_path'],
            'issued_by': rec['issued_by'],
            'issued_at': issued_date.strftime("%b %d, %Y"),
            'due_date': due_date.strftime("%b %d, %Y"),
            'is_overdue': is_overdue
        })

    return render_template('records.html', records=processed_records)

@app.route('/return/<int:record_id>', methods=['POST'])
@login_required
def return_book(record_id):
    record = database.get_record_by_id(record_id)
    if record:
        # 1. Increment quantity back in DB and update Books.csv
        database.restore_book_quantity(record['book_title'])

        # 2. Delete captured photo file
        full_img_path = os.path.join('static', record['image_path'])
        if os.path.exists(full_img_path):
            try:
                os.remove(full_img_path)
            except OSError:
                pass

        # 3. Delete database record
        database.delete_record(record_id)
        flash(f"Book '{record['book_title']}' returned! Quantity restored to file.", "success")

    return redirect(url_for('records'))

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)