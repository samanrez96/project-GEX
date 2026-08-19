## 📘 API Documentation – Accounts App

**Base URL**: `http://localhost:8000/api/v1/auth/`  
**Authentication**: JWT (Bearer Token) – except for `login/` which accepts credentials.  
**Endpoints**: 4 endpoints for full authentication flow.

---

### 1. Login (Obtain Token Pair)

- **Method**: POST  
- **URL**: `/login/`  
- **Body** (JSON):
  ```json
  {
    "username": "admin",
    "password": "secret123"
  }
  ```
- **cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/auth/login/" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"secret123"}'
  ```
- **Sample Response** (200 OK):
  ```json
  {
    "access": "eyJhbGciOiJIUzI1NiIs...",
    "refresh": "eyJhbGciOiJIUzI1NiIs..."
  }
  ```
- **Error** (401):
  ```json
  { "detail": "No active account found with the given credentials" }
  ```

---

### 2. Refresh Access Token

- **Method**: POST  
- **URL**: `/refresh/`  
- **Body** (JSON):
  ```json
  { "refresh": "<refresh_token>" }
  ```
- **cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/auth/refresh/" \
    -H "Content-Type: application/json" \
    -d '{"refresh":"eyJhbGciOiJIUzI1NiIs..."}'
  ```
- **Sample Response** (200 OK):
  ```json
  { "access": "eyJhbGciOiJIUzI1NiIs..." }
  ```

---

### 3. Logout

- **Method**: POST  
- **URL**: `/logout/`  
- **Headers**: `Authorization: Bearer <access_token>`  
- **Body** (JSON):
  ```json
  { "refresh": "<refresh_token>" }
  ```
- **cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/auth/logout/" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
    -H "Content-Type: application/json" \
    -d '{"refresh":"eyJhbGciOiJIUzI1NiIs..."}'
  ```
- **Sample Response** (200 OK):
  ```json
  { "detail": "Successfully logged out." }
  ```
- **Error** (400 – missing token):
  ```json
  { "detail": "Refresh token is required." }
  ```
- **Error** (400 – invalid/expired token):
  ```json
  { "detail": "Token is invalid or expired" }
  ```

---

### 4. Get Current User Profile

- **Method**: GET  
- **URL**: `/me/`  
- **Headers**: `Authorization: Bearer <access_token>`  
- **cURL**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/auth/me/" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
  ```
- **Sample Response** (200 OK):
  ```json
  {
    "id": 1,
    "username": "admin",
    "email": "admin@clinic.com",
    "first_name": "مدیر",
    "last_name": "سیستم",
    "is_staff": true,
    "is_superuser": true,
    "roles": ["admin", "finance_user"]
  }
  ```

---

### ✅ Error Codes Summary

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Invalid request (malformed data, missing fields) |
| 401 | Unauthorised (invalid credentials or expired token) |
| 403 | Forbidden (insufficient permissions – from permission classes) |

---

### 🔗 Integration with Other Apps

- Import permission classes via `from accounts.permissions import IsAdminOrFinanceUser` in any other app.
- Use `UserSerializer` for consistent user representation across APIs.
