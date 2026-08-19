### 📘 API Documentation – Surgeries App

**Base URL**: `http://localhost:8000/api/v1/surgeries/`  
**Authentication**: JWT Token (Bearer) or Session  
**Permissions**:
- **Read** (GET): `IsAuthenticated` (any logged-in user)
- **Write** (POST, PUT, PATCH, DELETE, and custom actions like `complete`): `IsAdminOrFinanceUser` (users in `admin` or `finance_user` groups)
- **Reports** (`/reports/profit/`): `IsAdminOrFinanceUser`

---

#### 1. Patients

**GET** `/patients/` – list patients (visible to user)  
**POST** `/patients/` – create patient (admin/finance)  
**GET/PUT/PATCH/DELETE** `/patients/{id}/` – retrieve/update/delete (write restricted)

```bash
curl -X GET "http://localhost:8000/api/v1/surgeries/patients/?search=احمد" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response (list)**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 5,
      "full_name": "احمد رضایی",
      "national_id": "0012345678",
      "case_code": "C-001",
      "internal_code": null,
      "phone_number": "09123456789",
      "age": 45,
      "gender": "MALE",
      "gender_display": "مرد",
      "is_hidden": false,
      "created_at": "2026-01-15T10:30:00Z"
    }
  ]
}
```

---

#### 2. Surgeries (legacy)

**GET** `/surgeries/` – list surgeries  
**POST** `/surgeries/` – create (admin/finance)  
**GET/PUT/PATCH/DELETE** `/surgeries/{id}/` – retrieve/update/delete (write restricted)  
**POST** `/surgeries/{id}/complete/` – complete and consume stock (admin/finance)

```bash
curl -X POST "http://localhost:8000/api/v1/surgeries/1/complete/" \
  -H "Authorization: Token YOUR_TOKEN"
```

---

#### 3. Surgery Types

**GET** `/types/` – list (filter by ?is_active=true/false)  
**POST** `/types/` – create (admin/finance)  
**GET/PUT/PATCH/DELETE** `/types/{id}/` – retrieve/update/delete (write restricted)

```bash
curl -X GET "http://localhost:8000/api/v1/surgeries/types/?is_active=true&search=appendectomy" \
  -H "Authorization: Token YOUR_TOKEN"
```

---

#### 4. Surgery Consumption Items

**GET** `/consumption-items/` – list (filters: surgery, product)  
**POST** `/consumption-items/` – create (admin/finance)  
**GET/PUT/PATCH/DELETE** `/consumption-items/{id}/` – standard CRUD (write restricted)

```bash
curl -X POST "http://localhost:8000/api/v1/surgeries/consumption-items/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"surgery":1,"product":10,"quantity":2}'
```

---

#### 5. Surgery History (new)

**GET** `/history/` – list history records (filters: patient, surgery_type, status, payment_status, clinical_doctor, doctor_or_therapist, date range, amount range)  
**POST** `/history/` – create (admin/finance)  
**GET/PUT/PATCH/DELETE** `/history/{id}/` – standard CRUD (write restricted)  
**Excel Export** – add `?export=excel` to list endpoint.

```bash
curl -X GET "http://localhost:8000/api/v1/surgeries/history/?status=COMPLETED&surgery_date_from=1404-01-01" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response (list)**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 10,
      "patient_name": "احمد رضایی",
      "patient_national_id": "0012345678",
      "patient_age": 45,
      "patient_gender": "MALE",
      "patient_gender_display": "مرد",
      "case_code": "C-001",
      "medical_record_code": "MR-001",
      "phone_number": "09123456789",
      "surgery_type_name": "آپاندکتومی",
      "doctor_name": "دکتر علی کریمی",
      "surgery_date": "2026-01-20T08:00:00Z",
      "amount": "5000000.00",
      "university_share": "2250000.00",
      "doctor_share": "2750000.00",
      "payment_status": "PAID",
      "payment_status_display": "پرداخت شده",
      "status": "COMPLETED",
      "status_display": "انجام شده",
      "center_commission_income_amount": "2500000.00",
      "description": "",
      "created_at": "2026-01-20T08:05:00Z"
    }
  ]
}
```

**POST create example**:
```bash
curl -X POST "http://localhost:8000/api/v1/surgeries/history/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "patient": 5,
    "surgery_type": 3,
    "clinical_doctor": 2,
    "surgery_date": "2026-08-20T09:00:00Z",
    "amount": "6000000.00",
    "payment_status": "PENDING",
    "status": "PLANNED"
  }'
```

---

#### 6. Surgery Used Items

**GET** `/used-items/` – list (filters: surgery, product)  
**POST** `/used-items/` – create (admin/finance) – automatically deducts stock  
**GET/PUT/PATCH/DELETE** `/used-items/{id}/` – standard CRUD (write restricted) – updates/deletes also adjust stock via compensating movements.

```bash
curl -X POST "http://localhost:8000/api/v1/surgeries/used-items/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"surgery":10,"product":20,"quantity":1.5,"description":"مصرف برای عمل"}'
```

---

#### 7. Surgery Profit Report

**GET** `/reports/profit/` – admin/finance only.

Query parameters: `start_date`, `end_date`, `surgery_type_id`, `doctor_id`, `patient_id`, `status`, `payment_status`, `group_by` (surgery|surgery_type|doctor), `min_profit`, `max_profit`, `page`, `page_size`, `export=excel`.

```bash
curl -X GET "http://localhost:8000/api/v1/surgeries/reports/profit/?start_date=2026-01-01&end_date=2026-08-19&group_by=doctor" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "metadata": {
    "start_date": "2026-01-01",
    "end_date": "2026-08-19",
    "group_by": "doctor",
    "surgery_type_id": null,
    "doctor_id": null,
    "patient_id": null,
    "status": null,
    "payment_status": null,
    "total_surgeries": 10,
    "total_center_income": "25000000.00",
    "total_consumed_items_cost": "8000000.00",
    "total_employee_commission_cost": "3000000.00",
    "total_approximate_profit": "14000000.00",
    "average_profit_per_surgery": "1400000.00",
    "profitable_surgeries_count": 8,
    "loss_surgeries_count": 2,
    "missing_cost_items_count": 0
  },
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "doctor_id": 2,
      "doctor_name": "دکتر علی کریمی",
      "surgeries_count": 4,
      "total_center_income": "12000000.00",
      "total_consumed_items_cost": "3000000.00",
      "total_employee_commission_cost": "1000000.00",
      "total_approximate_profit": "8000000.00",
      "average_profit_per_surgery": "2000000.00",
      "average_profit_margin_percent": "66.67"
    }
  ]
}
```
