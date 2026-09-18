
# Finance API – Complete cURL Documentation

**Base URL**: `http://localhost:8000/api/v2/finance`  
**Authentication**: Token (`Authorization: Token YOUR_TOKEN`) or Session Cookie  
**Permissions**: 
- `GET` (list/retrieve): `IsAuthenticated` for categories & transactions  
- `POST/PUT/PATCH/DELETE`: `IsAdminOrFinanceUser` only  
- `BalanceReport`: `IsAdminOrFinanceUser`  

---

## 1. Finance Categories (`/categories/`)

### 1.1 List Categories
**GET** `/categories/?category_type=expense&is_active=true&search=salary`

```bash
curl -X GET "http://localhost:8000/api/v2/finance/categories/?category_type=expense&is_active=true" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response** (200 OK):
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "هزینه دارو",
      "slug": "medicine-cost",
      "category_type": "expense",
      "description": "",
      "is_active": true,
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-01-15T10:30:00Z"
    },
    {
      "id": 3,
      "name": "حقوق ثابت کارمندان",
      "slug": "employee-salary-cost",
      "category_type": "expense",
      "description": "حقوق پایه کارمندان",
      "is_active": true,
      "created_at": "2026-02-01T08:20:00Z",
      "updated_at": "2026-02-01T08:20:00Z"
    }
  ]
}
```

### 1.2 Create Category
**POST** `/categories/` – `slug` is now **required** and unique.

```bash
curl -X POST "http://localhost:8000/api/v2/finance/categories/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "هزینه تبلیغات",
    "slug": "advertising-cost",
    "category_type": "expense",
    "description": "هزینه‌های بازاریابی",
    "is_active": true
  }'
```

**Sample Response** (201 Created):
```json
{
  "id": 10,
  "name": "هزینه تبلیغات",
  "slug": "advertising-cost",
  "category_type": "expense",
  "description": "هزینه‌های بازاریابی",
  "is_active": true,
  "created_at": "2026-08-19T14:15:00Z",
  "updated_at": "2026-08-19T14:15:00Z"
}
```

### 1.3 Retrieve/Update/Delete
- **GET** `/categories/{slug}/`  
- **PUT** `/categories/{slug}/` (all fields required)  
- **PATCH** `/categories/{slug}/` (partial update)  
- **DELETE** `/categories/{slug}/`  

---

## 2. Transactions (`/transactions/`)

### 2.1 List Transactions
**GET** `/transactions/?transaction_type=expense&payment_status=pending&transaction_date__gte=1404-01-01`

```bash
curl -X GET "http://localhost:8000/api/v2/finance/transactions/?transaction_type=expense&payment_status=pending" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response** (200 OK):
```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 15,
      "transaction_type": "expense",
      "category": {
        "id": 3,
        "name": "هزینه دارو",
        "slug": "medicine-cost",
        "category_type": "expense"
      },
      "amount": "1250000.00",
      "transaction_date": "1404-02-10T10:00:00Z",
      "description": "خرید دارو از شرکت داروسازی",
      "payment_status": "pending",
      "content_type": 8,
      "object_id": 42,
      "created_at": "1404-02-10T10:05:00Z",
      "updated_at": "1404-02-10T10:05:00Z"
    }
  ]
}
```

### 2.2 Create Transaction
**POST** `/transactions/` – requires `IsAdminOrFinanceUser`.

```bash
curl -X POST "http://localhost:8000/api/v2/finance/transactions/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_type": "expense",
    "category": 3,
    "amount": "2500000.00",
    "transaction_date": "1404-07-01T12:00:00Z",
    "description": "تعمیرات تجهیزات",
    "payment_status": "pending"
  }'
```

**Sample Response** (201 Created):
```json
{
  "id": 20,
  "transaction_type": "expense",
  "category": 3,
  "amount": "2500000.00",
  "transaction_date": "1404-07-01T12:00:00Z",
  "description": "تعمیرات تجهیزات",
  "payment_status": "pending",
  "content_type": null,
  "object_id": null,
  "created_at": "1404-07-01T12:05:00Z",
  "updated_at": "1404-07-01T12:05:00Z"
}
```

### 2.3 Retrieve/Update/Delete
Standard REST endpoints:  
- **GET** `/transactions/{id}/`  
- **PUT** `/transactions/{id}/`  
- **PATCH** `/transactions/{id}/`  
- **DELETE** `/transactions/{id}/`  

---

## 3. Balance Report (`/reports/balance/`)

**GET** `/reports/balance/`  

### Query Parameters (all optional):
- `start_date` – Jalali or Gregorian (e.g., `1404-01-01` or `2025-03-21`)  
- `end_date` – same format  
- `year` – Gregorian year (e.g., `2026`)  
- `month` – Gregorian month (1–12) – **must be accompanied by `year`**  
- `export=excel` – downloads Excel file instead of JSON  

**Default (no filters)**: returns **entire history** from the beginning of time until today.

### 3.1 Full History (no filters)
```bash
curl -X GET "http://localhost:8000/api/v2/finance/reports/balance/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response** (200 OK):
```json
{
  "total_income_period": "125000000.00",
  "total_expense_period": "92000000.00",
  "final_balance_cumulative": "33000000.00",
  "total_employee_cost_period": "42000000.00",
  "total_equipment_cost_period": "12000000.00",
  "total_medicine_cost_period": "18000000.00",
  "center_commission_income_period": "65000000.00",
  "university_commission_period": "15000000.00",
  "anesthesia_cost_period": "8000000.00",
  "daily_supplies_cost_period": "5000000.00"
}
```

**Field definitions:**
- `total_income_period` – total income within the filtered period (or all-time if no filter)  
- `total_expense_period` – total expense within the filtered period  
- `final_balance_cumulative` – **cumulative balance** from the beginning of time **up to the end of the filtered period** (or today)  
- Other `_period` fields – sum of specific categories **within the filtered period**  

### 3.2 Filter by Date Range (Jalali)
```bash
curl -X GET "http://localhost:8000/api/v2/finance/reports/balance/?start_date=1404-01-01&end_date=1404-06-30" \
  -H "Authorization: Token YOUR_TOKEN"
```

### 3.3 Filter by Year and Month (Gregorian)
```bash
curl -X GET "http://localhost:8000/api/v2/finance/reports/balance/?year=2026&month=3" \
  -H "Authorization: Token YOUR_TOKEN"
```
> ⚠️ `month` without `year` returns **400 Bad Request**.

### 3.4 Excel Export
```bash
curl -X GET "http://localhost:8000/api/v2/finance/reports/balance/?start_date=1404-01-01&end_date=1404-06-30&export=excel" \
  -H "Authorization: Token YOUR_TOKEN" \
  --output balance_report.xlsx
```

---

## 4. Finance Trend (`/reports/trend/`)

**GET** `/reports/trend/?year=2026` – optional `year` (Gregorian).

```bash
curl -X GET "http://localhost:8000/api/v2/finance/reports/trend/?year=2026" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response** (200 OK):
```json
[
  {
    "month": "2026-01",
    "income": 45000000.0,
    "expense": 32000000.0,
    "cumulative_balance": 13000000.0
  },
  {
    "month": "2026-02",
    "income": 52000000.0,
    "expense": 38000000.0,
    "cumulative_balance": 27000000.0
  },
  {
    "month": "2026-03",
    "income": 61000000.0,
    "expense": 43000000.0,
    "cumulative_balance": 45000000.0
  }
]
```

- `cumulative_balance` – balance accumulated from the beginning of time **up to the end of that month**.  
- `income` / `expense` – totals for that specific month.

---

## 5. Important Notes

- **Pagination** does **not** affect any aggregated numbers (totals and cumulative balance are computed globally on the server).  
- **Date filters** are inclusive on both ends.  
- **Cancelled transactions** (`payment_status=cancelled`) are **excluded** from all calculations.  
- The `slug` field in `FinanceCategory` is **unique and required** – use it for reliable system calculations instead of human-readable names.  
- If you request `month` without `year`, API returns `400 Bad Request` with an error message.  
- All `POST`, `PUT`, `PATCH`, `DELETE` operations on categories and transactions require `IsAdminOrFinanceUser` permission.