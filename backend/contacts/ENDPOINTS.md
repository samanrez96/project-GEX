### 📘 API Documentation – Contacts App

**Base URL**: `http://localhost:8001/api/v2/contacts/`  
**Authentication**: Token or Session (JWT)  
**Permissions**:
- `GET /doctors/` & `/doctors/{id}/` – authenticated users only  
- `POST /doctors/`, `PUT /doctors/{id}/`, `PATCH /doctors/{id}/`, `DELETE /doctors/{id}/` – users in `admin` or `employee_manager` groups  
- `GET /employees/` & `/employees/{id}/` – authenticated users only

---

#### 1. Doctor List & Search

- **Method**: GET  
- **URL**: `/doctors/`  
- **Query Params**: `is_active`, `cooperation_status`, `specialty`, `search`, `ordering`, `page`, `page_size`
- **cURL**:
```bash
curl -X GET "http://localhost:8001/api/v2/contacts/doctors/?is_active=true&search=احمد" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Sample Response** (200 OK):
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "full_name": "دکتر احمد رضایی",
      "specialty": 3,
      "specialty_name": "جراح عمومی",
      "phone_number": "09123456789",
      "email": "ahmad@clinic.com",
      "national_id": "0012345678",
      "medical_system_number": "12345",
      "clinic_phone": "021-12345678",
      "collaboration_start_date": "2025-01-01",
      "license_last_renewal_date": "2026-01-01",
      "medical_certificate_image": "http://localhost:8001/admin/contacts/doctor/1/documents/medical-certificate/",
      "national_card_image": "http://localhost:8001/admin/contacts/doctor/1/documents/national-card/",
      "center_commission_percent": "10.00",
      "rate_per_surgery": "500000.00",
      "cooperation_status": "active",
      "cooperation_status_display": "فعال",
      "is_active": true
    }
  ]
}
```

---

#### 2. Retrieve Doctor

- **Method**: GET  
- **URL**: `/doctors/{id}/`  
- **cURL**:
```bash
curl -X GET "http://localhost:8001/api/v2/contacts/doctors/1/" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Response** similar to above, but with more fields (address, notes, created_at, updated_at).

---

#### 3. Create Doctor (Admin/EmployeeManager only)

- **Method**: POST  
- **URL**: `/doctors/`  
- **Body** (JSON):
```json
{
  "full_name": "دکتر علی محمدی",
  "specialty": 3,
  "phone_number": "09123456789",
  "email": "ali@clinic.com",
  "national_id": "1234567890",
  "medical_system_number": "67890",
  "clinic_phone": "021-12345678",
  "collaboration_start_date": "2026-08-01",
  "center_commission_percent": 15.00,
  "rate_per_surgery": "600000.00",
  "cooperation_status": "active",
  "is_active": true
}
```
- **cURL**:
```bash
curl -X POST "http://localhost:8001/api/v2/contacts/doctors/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name":"دکتر علی محمدی","specialty":3,"phone_number":"09123456789","email":"ali@clinic.com","national_id":"1234567890","medical_system_number":"67890","clinic_phone":"021-12345678","collaboration_start_date":"2026-08-01","center_commission_percent":15,"rate_per_surgery":"600000.00","cooperation_status":"active","is_active":true}'
```
- **Response** (201 Created) – returns the created doctor object.

---

#### 4. Update Doctor (PUT / PATCH)

- **Method**: PUT (full) or PATCH (partial)  
- **URL**: `/doctors/{id}/`  
- **cURL for PATCH**:
```bash
curl -X PATCH "http://localhost:8001/api/v2/contacts/doctors/1/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```
- **Response** (200 OK) – updated doctor.

---

#### 5. Delete Doctor

- **Method**: DELETE  
- **URL**: `/doctors/{id}/`  
- **cURL**:
```bash
curl -X DELETE "http://localhost:8001/api/v2/contacts/doctors/1/" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Response**: 204 No Content.

---

#### 6. Employee Contact List (Read‑only)

- **Method**: GET  
- **URL**: `/employees/`  
- **Query Params**: `is_active`, `job_position`, `search`, `ordering`
- **cURL**:
```bash
curl -X GET "http://localhost:8001/api/v2/contacts/employees/?search=کارمند" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Sample Response** (200 OK):
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 5,
      "full_name": "مهناز کریمی",
      "job_position": 2,
      "job_position_name": "منشی",
      "personal_phone": "09123456788",
      "email": "mahnaz@clinic.com",
      "emergency_contact_phone": "021-12345600",
      "is_active": true
    }
  ]
}
```

---

#### 7. Retrieve Employee

- **Method**: GET  
- **URL**: `/employees/{id}/`  
- **cURL**:
```bash
curl -X GET "http://localhost:8001/api/v2/contacts/employees/5/" \
  -H "Authorization: Token YOUR_TOKEN"
```
- **Response** same as above.

---

#### 8. Excel Export (Doctors)

- **Method**: GET  
- **URL**: `/doctors/?export=excel`  
- **cURL**:
```bash
curl -X GET "http://localhost:8001/api/v2/contacts/doctors/?export=excel" \
  -H "Authorization: Token YOUR_TOKEN" \
  --output doctor_list.xlsx
```
- **Response**: Excel file download.

---

### ✅ Error Handling

- **403 Forbidden** – when attempting write operation without proper role.
- **400 Bad Request** – validation errors (e.g., invalid specialty, negative commission).
- **404 Not Found** – resource does not exist.

---

### 🔄 Coordination with Other Apps

- Uses `accounts.permissions.IsAdminOrEmployeeManager` – consistent with permission system.
- No hardcoded names – all lookups use primary keys.
- Document URLs rely on admin endpoints defined in `admin.py`, now safely chained.
