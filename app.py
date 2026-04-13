from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import base64
import numpy as np
import cv2
import os
import json
import uuid
from datetime import datetime
import face_recognition
import io
from PIL import Image

app = Flask(__name__, static_folder='static')
CORS(app)

DB_PATH = 'users.db'
FACE_DATA_DIR = 'face_data'
os.makedirs(FACE_DATA_DIR, exist_ok=True)

# ─── DATABASE SETUP ───────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            mobile TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            face_encoding TEXT NOT NULL,
            face_image_path TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── HELPERS ──────────────────────────────────────────────────────
def base64_to_image(b64_string):
    """Convert base64 image string to numpy array."""
    if ',' in b64_string:
        b64_string = b64_string.split(',')[1]
    img_bytes = base64.b64decode(b64_string)
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img

def get_face_encoding(b64_image):
    """Extract face encoding from a base64 image. Returns encoding or None."""
    img = base64_to_image(b64_image)
    if img is None:
        return None, "Could not decode image"
    
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Detect faces
    face_locations = face_recognition.face_locations(rgb_img, model='hog')
    
    if len(face_locations) == 0:
        return None, "No face detected. Please ensure your face is clearly visible."
    
    if len(face_locations) > 1:
        return None, "Multiple faces detected. Please ensure only one person is in frame."
    
    encodings = face_recognition.face_encodings(rgb_img, face_locations)
    if not encodings:
        return None, "Could not extract face features. Please try again."
    
    return encodings[0], None

def liveness_check_basic(b64_image):
    """
    Basic liveness/anti-spoofing check using image quality analysis.
    Checks for: blur, brightness uniformity, edge patterns typical of screens.
    Returns (is_live, reason)
    """
    img = base64_to_image(b64_image)
    if img is None:
        return False, "Invalid image"
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Laplacian variance - blurry images (printed photos) score low
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if lap_var < 30:
        return False, "Image too blurry. Please ensure good lighting."
    
    # 2. Check histogram spread - flat histograms suggest screens/photos
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_normalized = hist.flatten() / hist.sum()
    non_zero_bins = np.count_nonzero(hist_normalized > 0.001)
    if non_zero_bins < 30:
        return False, "Unusual image pattern detected. Please use a live camera."
    
    # 3. Face region skin tone check
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb, model='hog')
    if face_locations:
        top, right, bottom, left = face_locations[0]
        face_region = img[top:bottom, left:right]
        if face_region.size > 0:
            hsv_face = cv2.cvtColor(face_region, cv2.COLOR_BGR2HSV)
            # Skin tone hue range
            lower_skin = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin = np.array([30, 255, 255], dtype=np.uint8)
            skin_mask = cv2.inRange(hsv_face, lower_skin, upper_skin)
            skin_ratio = np.sum(skin_mask > 0) / (face_region.shape[0] * face_region.shape[1])
            if skin_ratio < 0.08:
                return False, "Could not verify live person. Please ensure face is well-lit."
    
    return True, "Liveness check passed"

def compare_faces(stored_encoding_list, new_encoding, tolerance=0.5):
    """Compare a new face encoding against stored encoding."""
    stored = np.array(stored_encoding_list)
    results = face_recognition.compare_faces([stored], new_encoding, tolerance=tolerance)
    distance = face_recognition.face_distance([stored], new_encoding)[0]
    return results[0], float(distance)

# ─── ROUTES ───────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/signup.html')
def signup_page():
    return send_from_directory('static', 'signup.html')

@app.route('/dashboard.html')
def dashboard_page():
    return send_from_directory('static', 'dashboard.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    full_name = data.get('full_name', '').strip()
    mobile = data.get('mobile', '').strip()
    email = data.get('email', '').strip().lower()
    face_image = data.get('face_image', '')

    # Validate fields
    if not all([full_name, mobile, email, face_image]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    if len(mobile) < 10:
        return jsonify({'success': False, 'message': 'Invalid mobile number.'}), 400

    # Check existing user
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE mobile=? OR email=?', (mobile, email))
    existing = c.fetchone()
    if existing:
        conn.close()
        return jsonify({'success': False, 'message': 'Mobile or email already registered.'}), 409

    # Liveness check
    is_live, live_msg = liveness_check_basic(face_image)
    if not is_live:
        conn.close()
        return jsonify({'success': False, 'message': live_msg}), 400

    # Extract face encoding
    encoding, err = get_face_encoding(face_image)
    if encoding is None:
        conn.close()
        return jsonify({'success': False, 'message': err}), 400

    # Check if this face already exists in DB
    c.execute('SELECT id, full_name, face_encoding FROM users')
    all_users = c.fetchall()
    for uid, uname, uenc in all_users:
        stored_enc = json.loads(uenc)
        match, dist = compare_faces(stored_enc, encoding, tolerance=0.45)
        if match:
            conn.close()
            return jsonify({'success': False, 'message': f'This face is already registered to another account.'}), 409

    # Save face image
    user_id = str(uuid.uuid4())
    face_path = os.path.join(FACE_DATA_DIR, f"{user_id}.jpg")
    img = base64_to_image(face_image)
    cv2.imwrite(face_path, img)

    # Store user
    encoding_json = json.dumps(encoding.tolist())
    c.execute('''
        INSERT INTO users (id, full_name, mobile, email, face_encoding, face_image_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, full_name, mobile, email, encoding_json, face_path, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'Account created successfully! Welcome, {full_name}!',
        'user_id': user_id,
        'full_name': full_name
    })


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    face_image = data.get('face_image', '')

    if not face_image:
        return jsonify({'success': False, 'message': 'No face image provided.'}), 400

    # Liveness check
    is_live, live_msg = liveness_check_basic(face_image)
    if not is_live:
        return jsonify({'success': False, 'message': live_msg}), 400

    # Extract face encoding
    encoding, err = get_face_encoding(face_image)
    if encoding is None:
        return jsonify({'success': False, 'message': err}), 400

    # Search database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, full_name, mobile, email, face_encoding FROM users')
    all_users = c.fetchall()
    conn.close()

    if not all_users:
        return jsonify({'success': False, 'message': 'No registered users found. Please sign up first.'}), 404

    best_match = None
    best_distance = 1.0

    for uid, full_name, mobile, email, uenc in all_users:
        stored_enc = json.loads(uenc)
        match, dist = compare_faces(stored_enc, encoding, tolerance=0.50)
        if match and dist < best_distance:
            best_distance = dist
            best_match = {
                'user_id': uid,
                'full_name': full_name,
                'mobile': mobile,
                'email': email,
                'confidence': round((1 - dist) * 100, 1)
            }

    if best_match:
        return jsonify({
            'success': True,
            'message': f"Welcome back, {best_match['full_name']}!",
            **best_match
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Face not recognized. Please sign up or try again with better lighting.'
        }), 401


@app.route('/api/check_face', methods=['POST'])
def check_face():
    """Real-time face detection check (for UI feedback, no DB query)."""
    data = request.json
    face_image = data.get('face_image', '')
    if not face_image:
        return jsonify({'detected': False})
    
    try:
        img = base64_to_image(face_image)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model='hog')
        return jsonify({
            'detected': len(locations) == 1,
            'count': len(locations)
        })
    except:
        return jsonify({'detected': False, 'count': 0})


if __name__ == '__main__':
    print("🚀 Face Auth Server starting on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
