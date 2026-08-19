### 📘 API Documentation – Employees App

**Base URL**: `http://localhost:8000/api/v2/employees/`  
**Authentication**: JWT Token (Bearer) or Session  
**Permissions**:
- **Read** (GET): `IsAuthenticated` (any logged-in user).
- **Write** (POST, PUT, PATCH, DELETE): `IsAdminOrEmployeeManager` (users in `admin` or `employee_manager` groups).

---

#### 1. Job Positions (`/positions/`)

**1.1 List Job Positions**
- **GET** `/positions/`  
- Query: `search`, `ordering`, `is_active`
- **cURL**:
```bash
curl -X GET "http://localhost:8000/api/v2/employees/positions/?is_active=true" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Sample Response**:
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {"id": 1, "name": "مدیر", "is_active": true},
    {"id": 2, "name": "کارشناس", "is_active": true}
  ]
}
```

**1.2 Create Job Position** (write)
- **POST** `/positions/`  
- Body: `{"name":"تکنسین", "description":"", "is_active":true}`
- **cURL**:
```bash
curl -X POST "http://localhost:8000/api/v2/employees/positions/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"تکنسین","is_active":true}'
```
- **Response**: 201 with full object.

**1.3 Retrieve, Update, Delete** – `/positions/{id}/`  
- PUT, PATCH, DELETE allowed only for admin/employee_manager.

---

#### 2. Employees (`/`)

**2.1 List Employees**
- **GET** `/`  
- Filters: `is_active`, `gender`, `job_position`, `start_date_from`, `start_date_to`, `search`, `ordering`
- **cURL**:
```bash
curl -X GET "http://localhost:8000/api/v2/employees/?is_active=true&search=علی" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Sample Response** (lightweight list):
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 3,
      "full_name": "علی حسینی",
      "national_id": "0012345678",
      "job_position": 2,
      "job_position_name": "کارشناس",
      "gender": "male",
      "gender_display": "مرد",
      "personal_phone": "09123456789",
      "email": "ali@clinic.com",
      "is_active": true,
      "start_date": "2025-01-01"
    }
  ]
}
```

**2.2 Retrieve Employee**
- **GET** `/{id}/`  
- **cURL**:
```bash
curl -X GET "http://localhost:8000/api/v2/employees/3/" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Sample Response** (detail, includes wage info):
```json
{
  "id": 3,
  "full_name": "علی حسینی",
  "national_id": "0012345678",
  "gender": "male",
  "gender_display": "مرد",
  "job_position": 2,
  "job_position_name": "کارشناس",
  "start_date": "2025-01-01",
  "is_active": true,
  "email": "ali@clinic.com",
  "personal_phone": "09123456789",
  "emergency_contact_phone": "021-12345678",
  "address": "تهران",
  "description": "",
  "legacy_hourly_rate": null,
  "current_hourly_rate": null,
  "current_hourly_rate_start_date": null,
  "current_hourly_rate_end_date": null,
  "future_hourly_rate": null,
  "future_hourly_rate_start_date": null,
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:00:00Z"
}
```

**2.3 Create Employee** (write)
- **POST** `/`  
- Body (example):
```json
{
  "full_name": "مریم کریمی",
  "national_id": "0012345679",
  "gender": "female",
  "job_position": 2,
  "start_date": "2026-08-01",
  "is_active": true,
  "email": "maryam@clinic.com",
  "personal_phone": "09123456780",
  "emergency_contact_phone": "021-12345679",
  "address": "اصفهان"
}
```
- **cURL**:
```bash
curl -X POST "http://localhost:8000/api/v2/employees/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name":"مریم کریمی","national_id":"0012345679","gender":"female","job_position":2,"start_date":"2026-08-01","is_active":true,"email":"maryam@clinic.com","personal_phone":"09123456780","emergency_contact_phone":"021-12345679","address":"اصفهان"}'
```
- **Response**: 201 Created.

**2.4 Update/Delete** – `/{id}/` – PUT, PATCH, DELETE require admin/employee_manager role.

---

#### 3. Employee Purchase Commissions (`/purchase-commissions/`)

**3.1 List**
- **GET** `/purchase-commissions/?employee=3`
- **cURL**:
```bash
curl -X GET "http://localhost:8000/api/v2/employees/purchase-commissions/?employee=3" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Sample Response**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "employee": 3,
      "employee_name": "علی حسینی",
      "purchase": 12,
      "purchase_pk": 12,
      "purchase_ref": "PO-2026-001",
      "purchase_date": "2026-08-15",
      "purchase_amount": "2500000",
      "items_summary": "مانیتور + ۲ قلم دیگر",
      "vendor_name": "تجهیزات طب",
      "amount": "50000.00",
      "commission_date": "2026-08-16",
      "description": "کمیسیون خرید",
      "created_at": "2026-08-16T10:00:00Z",
      "updated_at": "2026-08-16T10:00:00Z"
    }
  ]
}
```

**3.2 Create Commission** (write)
- **POST** `/purchase-commissions/`  
- Body: `{"employee":3, "amount":"50000", "commission_date":"2026-08-16", "description":"کمیسیون خرید"}`
- **cURL**:
```bash
curl -X POST "http://localhost:8000/api/v2/employees/purchase-commissions/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee":3,"amount":"50000","commission_date":"2026-08-16","description":"کمیسیون خرید"}'
```
- **Response**: 201 Created.

**3.3 Retrieve/Update/Delete** – `/{id}/` – write ops restricted.

---

#### 4. Excel Export (Employees List)

- **GET** `/?export=excel`  
- **cURL**:
```bash
curl -X GET "http://localhost:8000/api/v2/employees/?export=excel" \
  -H "Authorization: Token YOUR_TOKEN" \
  --output employees.xlsx
```
- **Response**: Excel file download.

---

### ✅ Error Handling

- **403 Forbidden** – when trying to create, update, or delete without proper role.
- **400 Bad Request** – validation errors (e.g., duplicate national_id, deactivating position with active employees).
- **404 Not Found** – resource does not exist.

---

### 🔄 Coordination with Other Apps

- Uses `accounts.permissions.IsAdminOrEmployeeManager` – consistent with role system.
- Admin extensions (`get_urls`) are instance-level, not global monkey-patching.
- No hardcoded strings or magic numbers.
