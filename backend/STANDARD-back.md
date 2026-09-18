# Prompt for Standardizing Django Apps

**Role**: Senior Django Backend Engineer & System Architect.

**Context**:  
We have a Django codebase with multiple apps (e.g., `finance`, `payroll`, `inventory`, `surgeries`, etc.). Each app has its own models, views, services, signals, and admin configurations. However, the code is not fully standardized – there are security gaps (improper permissions), logical inconsistencies (duplicate data sources, hardcoded values, incorrect balance calculations), performance bottlenecks (N+1 queries, lack of aggregation), and maintainability issues (monkey patching, name‑based lookups, scattered constants).

**Goal**:  
You will receive one app at a time. For each app, you must perform a **complete refactoring and standardization** following the best practices established in the `finance` app (which has already been successfully standardized). After each app, you must produce:
1. **Full updated code files** (models, views, services, signals, admin, filters, serializers, etc.) – even if unchanged, provide the entire file.
2. **Comprehensive API documentation** in English with **cURL examples** and **sample responses** for all endpoints.
3. A **summary of changes** (what was fixed and why).

**Your analysis must cover**:

### 🔐 Security
- Ensure every ViewSet/APIView has **proper permission classes**:
  - `IsAuthenticated` for read‑only (list/retrieve) if public.
  - `IsAdminOrFinanceUser` (or similar role‑based) for write operations (create/update/delete).
- Remove any **monkey patching** (e.g., overriding `get_urls` on `admin.site`); use a custom `AdminSite` instead.
- Validate all user inputs rigorously; return clear error messages for malformed parameters.

### 🧠 Logical Integrity
- **Data Sources**: Centralize all financial/payroll/surgery calculations into a **single source of truth** (e.g., `Transaction` model) rather than mixing multiple models (e.g., directly querying `MonthlyWage` and `CommissionTransaction`).  
- **Cumulative Balance**: Compute balance as **accumulated from the beginning of time up to the end of the filtered period**, not just the period’s net difference.  
- **Hardcoded Values**: Replace any hardcoded category names, percentage rates, or business rules with:
  - A `slug` field on key models (like `FinanceCategory`) – use `slug` instead of name in all system logic.
  - Settings variables (e.g., `UNIVERSITY_COMMISSION_PERCENT`) for configurable percentages.
- **Date Handling**: When filtering by `year` and `month`, ensure `month` cannot be used without `year` – return `400 Bad Request` if so. Convert `year`/`month` to a proper date range for consistent querying.
- **Cumulative Trend**: In trend endpoints, include `cumulative_balance` for each period to show the running total.

### ⚡ Performance & Efficiency
- Replace per‑category sum queries (multiple hits) with a **single `GROUP BY` aggregation** using `values('category__slug').annotate(total=Sum('amount'))`.
- Avoid **N+1 queries** by using `select_related` and `prefetch_related` where appropriate.
- Use **window functions** or simple Python accumulation for cumulative calculations instead of querying the entire table multiple times.
- Remove **unused code**, dead classes, and unnecessary imports.

### 🧹 Maintainability & Consistency
- **Constants**: Define all system‑critical category slugs, statuses, and permissions in a single, shared module (e.g., `finance/services.py` or `common/constants.py`) and reference them across apps to avoid duplication.
- **Naming**: Use clear, consistent field names (e.g., `_period` suffix for period‑only aggregates, `_cumulative` for running totals).
- **Error Handling**: Use Django’s `ValidationError` or DRF’s `raise_exception` with meaningful messages.
- **Admin**: Use a custom `AdminSite` subclass for each app if needed, but avoid patching `admin.site` globally.
- **Signals**: Keep signal handlers lightweight; delegate heavy logic to service classes.

---

### Expected Output for Each App

You will receive the **full codebase** of one app (all `.py` files). Your response must include:

1. **Refactored Code Files** (complete, copy‑paste ready) – clearly labeled with filenames (e.g., `models.py`, `views.py`, etc.).
2. **API Documentation** (in English) – containing:
   - Base URL and authentication method.
   - Endpoints with `GET`, `POST`, `PUT`, `PATCH`, `DELETE`.
   - Query parameters and expected request body (with examples).
   - Sample responses (JSON) for success and error cases.
   - **cURL commands** for every endpoint.
3. **Change Log** – bullet points explaining what was fixed and why (e.g., “Replaced hardcoded category name with slug”, “Added cumulative balance calculation”).

### Coordination Between Apps

- If you introduce a new `slug` for a model that is used across apps (e.g., `FinanceCategory`), ensure the slug is documented and imported from a shared constants file (e.g., `common/constants.py`).  
- Use the **same permission classes** across all apps (e.g., `IsAdminOrFinanceUser` from `accounts.permissions`).  
- If an endpoint is similar to one in the `finance` app (e.g., balance report), mimic the response structure (e.g., `_period` and `_cumulative` fields).  
- Ensure **no duplicate logic** – if a service is generic (e.g., Excel export, date parsing), use the common utilities in `common/` instead of rewriting.

---

### Final Remarks

Treat each app as an independent unit, but keep the overall ecosystem in mind. After finishing all apps, the entire system should be:
- **Secure** (proper permissions, input validation).
- **Accurate** (logical calculations, single source of truth).
- **Fast** (optimized queries, minimal DB hits).
- **Clean** (no hacks, no hardcoded values, easy to extend).

Start with the app I will provide now. If you need any clarification about existing app dependencies, ask before proceeding.

---

**Example of your response format** (for reference):

```
### App: <app_name>

#### Changes Summary
- ...
- ...

#### Updated Files

##### models.py
```python
# full code
```

##### views.py
```python
# full code
```

... (all files)

#### API Documentation

**Base URL**: `http://localhost:8000/api/v2/<app_name>`
**Authentication**: Token / Session

##### 1. Endpoint Name
- **Method**: GET
- **URL**: `/path/`
- **cURL**: `curl ...`
- **Sample Response**: `{ ... }`

... (all endpoints)

---

**Now, apply this process to the following app.** I will provide its code files one by one. Proceed with the analysis and refactoring.