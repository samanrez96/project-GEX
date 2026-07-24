# Surgery Clinic Management System

A RESTful API backend for managing the day-to-day operations of a surgical clinic — covering personnel, finances, medical inventory, and surgery records.

Built with **Django 5** and **Django REST Framework**, localized for Iran (Persian / Asia/Tehran).

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Overview](#api-overview)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Development Server](#running-the-development-server)
- [Configuration](#configuration)
- [Contributing](#contributing)

---

## Features

| Module | Description |
|---|---|
| **Employees** | Staff directory, anesthesiologist records, job positions, personal information |
| **Finance** | Payroll, wages, payments, daily accounting, income & expense tracking |
| **Inventory** | Medicines, medical equipment, stock levels, suppliers, purchase history |
| **Surgeries** | Surgery records and operation-related data |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.x |
| Framework | Django 5.2 |
| REST API | Django REST Framework 3.17 |
| Database | PostgreSQL (SQLite fallback for development) |
| CORS | django-cors-headers |
| Config | django-environ |

---

## Project Structure

```
surgery-clinic/
├── config/                  # Django project configuration
│   ├── settings/
│   │   ├── base.py          # Shared settings
│   │   ├── development.py   # Development overrides
│   │   └── production.py    # Production hardening
│   ├── urls.py              # Root URL router (/api/v1/)
│   ├── wsgi.py
│   └── asgi.py
├── employees/               # Staff & personnel management
├── finance/                 # Financial operations & accounting
├── inventory/               # Medical supply chain
├── surgeries/               # Clinical operations & surgery records
├── manage.py
├── requirements.txt
├── .env.example
└── db.sqlite3               # Development database
```

---

## API Overview

All endpoints are versioned under `/api/v1/`.

| Prefix | App |
|---|---|
| `/api/v1/employees/` | Employees |
| `/api/v1/finance/` | Finance |
| `/api/v1/inventory/` | Inventory |
| `/api/v1/surgeries/` | Surgeries |

The Django admin panel is available at `/admin/`.

**Pagination:** All list endpoints return paginated results with a default page size of 20.

---

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL (optional for development; SQLite is used by default)
- `pip` and `venv`

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/surgery-clinic.git
cd surgery-clinic

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Copy the example file and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description | Example |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key (keep private) | `change-me-in-production` |
| `DJANGO_DEBUG` | Enable debug mode | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `DATABASE_URL` | Database connection string | `postgres://user:pass@localhost/surgery_clinic` |

Leave `DATABASE_URL` empty to use the SQLite fallback (`db.sqlite3`).

### Running the Development Server

```bash
# Apply migrations
python manage.py migrate

# Create a superuser (for the admin panel)
python manage.py createsuperuser

# Start the server
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.

---

## Configuration

The project uses split settings:

| Module | Usage |
|---|---|
| `config.settings.development` | Local development (default) |
| `config.settings.production` | Production deployments |

To switch to production settings, set the environment variable:

```bash
# Windows (PowerShell)
$env:DJANGO_SETTINGS_MODULE = "config.settings.production"

# macOS / Linux
export DJANGO_SETTINGS_MODULE=config.settings.production
```

**Production settings include:**
- `DEBUG = False`
- Strict CORS origin allowlist
- Secure cookies (HTTPS-only, HttpOnly, SameSite)
- Security headers (X-Frame-Options, XSS protection, Content-Type nosniff)

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m "Add your feature"`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

> Localized for Iran — language: `fa-ir`, timezone: `Asia/Tehran`
