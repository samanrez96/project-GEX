### 📘 API Documentation

**Base URL**: `http://localhost:8000/api/v1/payroll/`  
**Authentication**: JWT Token (Bearer) or Session  
**Permissions**:
- **Read** (GET): `IsAuthenticated` (any logged-in user)
- **Write** (POST, PUT, PATCH, DELETE, and custom actions like `close`, `calculate`): `IsAdminOrFinanceUser` (users in `admin` or `finance_user` groups)
- **Reports** (`/report/`, `/reports/employee-cost/`): `IsAdminOrFinanceUser`

---

#### 1. Payroll Periods

**GET** `/periods/` – list periods  
**POST** `/periods/` – create (admin/finance)  
**GET/PATCH** `/periods/{id}/` – retrieve/update (write restricted)  
**POST** `/periods/{id}/close/` – close a period (admin/finance)  

```bash
curl -X GET "http://localhost:8000/api/v1/payroll/periods/?status=OPEN" \
  -H "Authorization: Token YOUR_TOKEN"
```

#### 2. Payroll Type Configs

**GET** `/configs/` – list configs  
**PATCH** `/configs/{id}/` – update (admin/finance)  
**GET** `/configs/by_employee/?employee={id}` – retrieve by employee  

```bash
curl -X GET "http://localhost:8000/api/v1/payroll/configs/by_employee/?employee=5" \
  -H "Authorization: Token YOUR_TOKEN"
```

#### 3. Monthly Wages

**GET** `/wages/` – list (filters: employee, is_active)  
**POST** `/wages/` – create (admin/finance)  
**GET/PATCH** `/wages/{id}/` – retrieve/update (write restricted)  
**GET** `/wages/period_summary/?year=&month=` – summary for a Jalali month  

```bash
curl -X POST "http://localhost:8000/api/v1/payroll/wages/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee":5,"amount":"5000000","start_date":"2026-08-01","is_active":true}'
```

#### 4. Hourly Rates

**GET** `/hourly-rates/` – list  
**POST** `/hourly-rates/` – create (admin/finance)  
**GET/PATCH** `/hourly-rates/{id}/` – retrieve/update (write restricted)  

```bash
curl -X POST "http://localhost:8000/api/v1/payroll/hourly-rates/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee":5,"rate":"150000","start_date":"2026-08-01","is_active":true}'
```

#### 5. Hourly Work Entries

**GET** `/hourly-work-entries/` – list (filters: employee, work_date__gte, work_date__lte, payroll_period)  
**POST** `/hourly-work-entries/` – create (admin/finance)  
**GET/PATCH** `/hourly-work-entries/{id}/` – retrieve/update (write restricted)  
**DELETE** `/hourly-work-entries/{id}/` – blocked if processed  
**POST** `/hourly-work-entries/calculate/` – preview calculation (admin/finance)  

```bash
curl -X POST "http://localhost:8000/api/v1/payroll/hourly-work-entries/calculate/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"employee":5,"year":1404,"month":6}'
```

#### 6. Commission Rules

**GET** `/commission-rules/` – list (filters: job_position, surgery_type, is_active)  
**POST** `/commission-rules/` – create (admin/finance)  
**GET/PATCH** `/commission-rules/{id}/` – retrieve/update (write restricted)  
**DELETE** → 405 (use deactivation)  
**GET** `/commission-rules/matrix/` – matrix view  
**GET** `/commission-rules/by_position/?job_position={id}` – rules for a position  

```bash
curl -X GET "http://localhost:8000/api/v1/payroll/commission-rules/matrix/" \
  -H "Authorization: Token YOUR_TOKEN"
```

#### 7. Commission Transactions (read-only)

**GET** `/commission-transactions/` – list (filters: employee, surgery, commission_rule)  
**GET** `/commission-transactions/{id}/` – retrieve  

```bash
curl -X GET "http://localhost:8000/api/v1/payroll/commission-transactions/?employee=5" \
  -H "Authorization: Token YOUR_TOKEN"
```

#### 8. Payroll Report

**GET** `/report/` – aggregated payroll report (admin/finance)  

Query: `start_date`, `end_date`, `employee`, `position`, `month`, `year`, `wage_type`  

```bash
curl -X GET "http://localhost:8000/api/v1/payroll/report/?year=1404&month=6&wage_type=both" \
  -H "Authorization: Token YOUR_TOKEN"
```

#### 9. Employee Cost Report

**GET** `/reports/employee-cost/` – per-employee cost report (admin/finance)  

Query: `start_date`, `end_date`, `employee_id`, `position_id`, `wage_type`, `page`, `page_size`, `export=excel`  

```bash
curl -X GET "http://localhost:8000/api/v1/payroll/reports/employee-cost/?start_date=2026-08-01&end_date=2026-08-31" \
  -H "Authorization: Token YOUR_TOKEN"
```