# 🔐 FaceAuth — Biometric Login System

Face recognition-based authentication system with **Python Flask** backend and a polished **HTML/CSS/JS** frontend.

---

## 📁 Project Structure

```
face_auth/
├── app.py                  ← Flask backend (API)
├── requirements.txt        ← Python dependencies
├── users.db                ← SQLite database (auto-created)
├── face_data/              ← Stored face images (auto-created)
└── static/
    ├── index.html          ← Login page (auto face detection)
    ├── signup.html         ← Signup page (collect info + face)
    └── dashboard.html      ← Dashboard after login
```

---

## ⚙️ Setup & Installation

### 1. Install system dependencies (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install -y cmake build-essential python3-dev libopenblas-dev
```

### 2. Install Python packages
```bash
pip install -r requirements.txt
```

> **Note:** `face-recognition` requires `dlib` which compiles from source. This may take 5–10 minutes.

### 3. Run the server
```bash
python app.py
```

The server starts at **http://localhost:5000**

### 4. Open the app
- Login:   http://localhost:5000/
- Signup:  http://localhost:5000/signup.html

---

## 🔑 How It Works

### Signup Flow
1. User enters **Full Name, Mobile Number, Email**
2. Camera activates — face is detected automatically
3. After holding face steady for ~2 seconds, face is captured
4. **Liveness checks** run:
   - Blur/sharpness analysis (catches printed photos)
   - Histogram analysis (catches screen recordings)
   - Skin-tone detection (verifies real face)
5. **Face encoding** (128-dimension vector) is extracted via `face_recognition`
6. Duplicate face check against all existing users
7. Data saved to **SQLite DB** + face image stored in `face_data/`

### Login Flow
1. Camera activates immediately on page load
2. Face detection runs every 300ms (no video — just frame captures)
3. After 5 consecutive successful detections (~1.5 seconds), login is attempted
4. **Same liveness checks** run as signup
5. Face encoding compared against **all users in DB**
6. Best match with `tolerance ≤ 0.50` → auto login
7. Welcome screen shows user's **full name** + confidence score
8. Redirects to dashboard

---

## 🛡️ Security Features

| Feature | Description |
|---------|-------------|
| Face encoding (128-D) | Via `face_recognition` (dlib ResNet) |
| Liveness detection | Blur + histogram + skin-tone analysis |
| Anti-spoofing | Detects photos/screens |
| Duplicate prevention | No same face registered twice |
| Single-face enforcement | Rejects frames with multiple people |
| Auto-login threshold | 5 consecutive detections required |
| Mirror detection | Frames are flipped to match display |

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/signup` | Register new user with face |
| POST | `/api/login` | Login via face recognition |
| POST | `/api/check_face` | Lightweight face detection check |

### POST `/api/signup`
```json
{
  "full_name": "John Doe",
  "mobile": "+91 98765 43210",
  "email": "john@example.com",
  "face_image": "data:image/jpeg;base64,..."
}
```

### POST `/api/login`
```json
{
  "face_image": "data:image/jpeg;base64,..."
}
```

### Response on success
```json
{
  "success": true,
  "full_name": "John Doe",
  "email": "john@example.com",
  "user_id": "uuid-here",
  "confidence": 94.3,
  "message": "Welcome back, John Doe!"
}
```

---

## 🗄️ Database Schema

```sql
CREATE TABLE users (
  id              TEXT PRIMARY KEY,   -- UUID
  full_name       TEXT NOT NULL,
  mobile          TEXT NOT NULL UNIQUE,
  email           TEXT NOT NULL UNIQUE,
  face_encoding   TEXT NOT NULL,      -- JSON array of 128 floats
  face_image_path TEXT,
  created_at      TEXT NOT NULL
);
```

---

## 🚀 Production Notes

- Use **HTTPS** in production (required for camera access)
- Replace SQLite with **PostgreSQL** for multi-user scale
- Store face images in **S3 or cloud storage**
- Add **JWT tokens** for session management
- Consider **GPU-accelerated** face detection for speed
- Set `CORS` to specific origin in production
