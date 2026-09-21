# Inventory App – Complete cURL Documentation

**Base URL**: `http://localhost:8001/api/v2/inventory/`  
**Authentication**: JWT Token (Bearer) or Session  
**Permissions**:
- **Read** (GET): `IsAuthenticated` (any logged-in user)
- **Write** (POST, PUT, PATCH, DELETE): `IsAdminOrInventoryUser` (users in `admin` or `inventory_user` groups)
- **Purge Actions** (product purge): `IsMainAdministrator` (superuser only)
- **Reports**: `IsAdminOrFinanceUser` (users in `admin` or `finance_user` groups)

---

## 1. Product Categories

### 1.1 List Categories
**GET** `/categories/`

**Query Params**: `is_active`, `parent`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/categories/?is_active=true" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "دارو",
      "full_path": "دارو",
      "parent": null,
      "is_active": true
    },
    {
      "id": 2,
      "name": "تجهیزات",
      "full_path": "تجهیزات",
      "parent": null,
      "is_active": true
    }
  ]
}
```

### 1.2 Retrieve Category with Children
**GET** `/categories/{id}/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/categories/1/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "id": 1,
  "name": "دارو",
  "full_path": "دارو",
  "parent": null,
  "is_active": true,
  "children": [
    {
      "id": 3,
      "name": "آنتی‌بیوتیک",
      "full_path": "دارو / آنتی‌بیوتیک",
      "parent": 1,
      "is_active": true
    }
  ]
}
```

### 1.3 Category Tree
**GET** `/categories/tree/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/categories/tree/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
[
  {
    "id": 1,
    "name": "دارو",
    "description": "",
    "is_active": true,
    "depth": 0,
    "children": [
      {
        "id": 3,
        "name": "آنتی‌بیوتیک",
        "description": "",
        "is_active": true,
        "depth": 1,
        "children": []
      }
    ]
  }
]
```

---

## 2. Products

### 2.1 List Products
**GET** `/products/`

**Query Params**: `product_type`, `category`, `category_tree`, `is_active`, `low_stock`, `out_of_stock`, `price_min`, `price_max`, `has_barcode`, `vendor`, `stock_min`, `stock_max`, `search`, `ordering`, `page`, `page_size`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/?is_active=true&product_type=medicine&search=آسپیرین" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "page_size": 150,
  "total_pages": 1,
  "results": [
    {
      "id": 10,
      "name": "آسپیرین 500mg",
      "internal_code": "MED-001",
      "product_type": "medicine",
      "product_type_display": "دارو",
      "category": 3,
      "category_name": "آنتی‌بیوتیک",
      "unit": "عدد",
      "purchase_price": "15000.00",
      "sale_price": "0.00",
      "current_stock": "100.000",
      "minimum_stock": "20.000",
      "barcode": "1234567890",
      "is_low_stock": false,
      "is_out_of_stock": false,
      "stock_status": "موجود",
      "is_active": true
    }
  ]
}
```

### 2.2 Retrieve Product
**GET** `/products/{id}/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/10/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "id": 10,
  "name": "آسپیرین 500mg",
  "internal_code": "MED-001",
  "product_type": "medicine",
  "product_type_display": "دارو",
  "category": 3,
  "category_detail": {
    "id": 3,
    "name": "آنتی‌بیوتیک",
    "full_path": "دارو / آنتی‌بیوتیک",
    "parent": 1,
    "is_active": true
  },
  "unit": "عدد",
  "purchase_price": "15000.00",
  "sale_price": "0.00",
  "barcode": "1234567890",
  "current_stock": "100.000",
  "minimum_stock": "20.000",
  "internal_notes": "",
  "is_active": true,
  "is_low_stock": false,
  "is_out_of_stock": false,
  "stock_status": "موجود",
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-01-15T10:30:00Z"
}
```

### 2.3 Create Product (Write – Admin/Inventory User)
**POST** `/products/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/products/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "پاراستامول 500mg",
    "internal_code": "MED-002",
    "product_type": "medicine",
    "category": 3,
    "unit": "عدد",
    "purchase_price": "5000.00",
    "minimum_stock": "10.000",
    "is_active": true
  }'
```

**Sample Response** (201 Created):
```json
{
  "id": 11,
  "name": "پاراستامول 500mg",
  "internal_code": "MED-002",
  "product_type": "medicine",
  "product_type_display": "دارو",
  "category": 3,
  "category_detail": {
    "id": 3,
    "name": "آنتی‌بیوتیک",
    "full_path": "دارو / آنتی‌بیوتیک",
    "parent": 1,
    "is_active": true
  },
  "unit": "عدد",
  "purchase_price": "5000.00",
  "sale_price": "0.00",
  "barcode": null,
  "current_stock": "0.000",
  "minimum_stock": "10.000",
  "internal_notes": "",
  "is_active": true,
  "is_low_stock": true,
  "is_out_of_stock": true,
  "stock_status": "ناموجود",
  "created_at": "2026-08-19T14:15:00Z",
  "updated_at": "2026-08-19T14:15:00Z"
}
```

### 2.4 Update Product (PUT / PATCH)
**PATCH** `/products/{id}/`

```bash
curl -X PATCH "http://localhost:8001/api/v2/inventory/products/10/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"minimum_stock": "30.000"}'
```

**Response**: 200 OK with updated product object.

### 2.5 Delete Product (Blocked)
**DELETE** `/products/{id}/` – always blocked with error message.

```bash
curl -X DELETE "http://localhost:8001/api/v2/inventory/products/10/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response** (400 Bad Request):
```json
{
  "detail": "حذف مستقیم محصول از این مسیر امکان‌پذیر نیست. برای غیرفعال‌سازی، فیلد is_active را خاموش کنید؛ برای حذف کامل و دائمی از عملیات purge (مخصوص مدیر اصلی) استفاده کنید."
}
```

### 2.6 Low Stock Products
**GET** `/products/low_stock/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/low_stock/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Response**: List of products with `current_stock <= minimum_stock`.

### 2.7 Export Product IDs
**GET** `/products/export_ids/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/export_ids/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 5,
  "ids": [1, 2, 3, 4, 5]
}
```

### 2.8 Product Purge Preview (Superuser Only)
**GET** `/products/{id}/purge-preview/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/10/purge-preview/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "product": {
    "id": 10,
    "internal_code": "MED-001",
    "name": "آسپیرین 500mg",
    "product_type": "دارو",
    "current_stock": "100.000"
  },
  "stock_movements_count": 3,
  "surgery_used_items_count": 0,
  "affected_surgery_history_count": 0,
  "surgery_consumption_items_count": 0,
  "affected_legacy_surgery_count": 0,
  "purchase_items_count": 2,
  "affected_purchases": [
    {
      "id": 5,
      "reference_number": "PO-2026-001",
      "status": "CONFIRMED",
      "current_total": "150000.00",
      "new_total": "135000.00",
      "will_be_emptied": false
    }
  ],
  "product_vendor_count": 1
}
```

### 2.9 Product Purge (Superuser Only)
**POST** `/products/{id}/purge/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/products/10/purge/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirmation_code": "MED-001"}'
```

**Sample Response** (200 OK):
```json
{
  "id": 10,
  "internal_code": "MED-001",
  "name": "آسپیرین 500mg",
  "surgery_used_items_deleted": 0,
  "affected_surgery_history_ids": [],
  "surgery_consumption_items_deleted": 0,
  "affected_legacy_surgery_ids": [],
  "stock_movements_deleted": 3,
  "purchase_items_deleted": 2,
  "product_vendors_deleted": 1,
  "purchases_cancelled": [],
  "purchases_recalculated": [5]
}
```

### 2.10 Vendor Price History (for a Product)
**GET** `/products/{id}/vendor-price-history/`

**Query Params**: `vendor_id`, `date_from`, `date_to`, `currency`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/10/vendor-price-history/?vendor_id=2" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
[
  {
    "id": 15,
    "product_id": 10,
    "product_name": "آسپیرین 500mg",
    "vendor_id": 2,
    "vendor_name": "داروسازی تهران",
    "purchase_id": 5,
    "reference_id": "PO-2026-001",
    "purchase_date": "2026-01-15T10:00:00Z",
    "unit_price": "15000.00",
    "quantity": "10.000",
    "total_amount": "150000.00",
    "currency": "IRR"
  }
]
```

### 2.11 Product Excel Export
**GET** `/products/?export=excel`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/products/?export=excel" \
  -H "Authorization: Token YOUR_TOKEN" \
  --output products.xlsx
```

---

## 3. Vendors

### 3.1 List Vendors
**GET** `/vendors/`

**Query Params**: `is_active`, `search`, `ordering`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/vendors/?is_active=true&search=تهران" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "داروسازی تهران",
      "phone_number": "021-12345678",
      "email": "info@tehrandaru.com",
      "address": "تهران، خیابان انقلاب",
      "notes": "",
      "phones": ["021-12345678", "021-87654321"]
    }
  ]
}
```

### 3.2 Retrieve Vendor
**GET** `/vendors/{id}/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/vendors/1/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "id": 1,
  "name": "داروسازی تهران",
  "phone_number": "021-12345678",
  "email": "info@tehrandaru.com",
  "address": "تهران، خیابان انقلاب",
  "notes": "",
  "is_active": true,
  "opening_balance": "0.00",
  "current_balance": "0.00",
  "tax_id": "1234567890",
  "bank_account": "IR123456789012345678901234",
  "created_at": "2026-01-01T08:00:00Z",
  "updated_at": "2026-01-01T08:00:00Z",
  "phones": ["021-12345678", "021-87654321"],
  "additional_phones": [
    {"id": 1, "phone": "021-87654321", "order": 1}
  ]
}
```

### 3.3 Create Vendor (Write – Admin/Inventory User)
**POST** `/vendors/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/vendors/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "تجهیزات پزشکی پارس",
    "phone_number": "021-98765432",
    "email": "info@parsmedical.com",
    "address": "تهران، خیابان آزادی",
    "is_active": true
  }'
```

**Response**: 201 Created with full vendor object.

### 3.4 Update Vendor (PUT / PATCH)
**PATCH** `/vendors/{id}/`

```bash
curl -X PATCH "http://localhost:8001/api/v2/inventory/vendors/1/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### 3.5 Delete Vendor
**DELETE** `/vendors/{id}/` – only if no related purchases exist.

```bash
curl -X DELETE "http://localhost:8001/api/v2/inventory/vendors/1/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Response**: 204 No Content.

### 3.6 Vendor Purchased Products
**GET** `/vendors/{id}/purchased-products/`

**Query Params**: `search`, `page`, `page_size`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/vendors/1/purchased-products/?search=آسپیرین" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 10,
      "internal_code": "MED-001",
      "name": "آسپیرین 500mg",
      "product_type": "medicine",
      "product_type_display": "دارو",
      "unit": "عدد",
      "current_stock": "100.000",
      "is_active": true,
      "purchase_count": 3,
      "total_quantity": "50.000",
      "last_purchase_date": "2026-08-15T10:00:00Z",
      "last_unit_price": "15000.00",
      "product_detail_url": "/admin/inventory/product/10/detail/"
    }
  ]
}
```

---

## 4. Product-Vendor Links

### 4.1 List Product-Vendor Links
**GET** `/product-vendors/`

**Query Params**: `product`, `vendor`, `is_active`, `is_primary`, `search`, `ordering`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/product-vendors/?product=10" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "product": 10,
      "product_name": "آسپیرین 500mg",
      "product_code": "MED-001",
      "vendor": 1,
      "vendor_name": "داروسازی تهران",
      "vendor_url": "/admin/inventory/vendor/1/change/",
      "vendor_detail_url": "/admin/inventory/vendor/1/detail/",
      "supplier_product_code": "ASP-500",
      "unit_price": "15000.00",
      "currency": "IRR",
      "is_primary": true,
      "is_active": true,
      "total_purchased_quantity": "50.000",
      "latest_purchase_date": "2026-08-15"
    }
  ]
}
```

### 4.2 Create Product-Vendor Link (Write)
**POST** `/product-vendors/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/product-vendors/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 10,
    "vendor": 2,
    "unit_price": "16000.00",
    "currency": "IRR",
    "is_active": true
  }'
```

**Response**: 201 Created.

### 4.3 Update/Delete
**PATCH** `/product-vendors/{id}/`  
**DELETE** `/product-vendors/{id}/`

---

## 5. Stock Movements

### 5.1 List Stock Movements
**GET** `/stock-movements/`

**Query Params**: `product`, `movement_type`, `source_type`, `search`, `ordering`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/stock-movements/?product=10" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "page_size": 75,
  "total_pages": 1,
  "results": [
    {
      "id": 5,
      "product": 10,
      "product_name": "آسپیرین 500mg",
      "product_code": "MED-001",
      "quantity": "10.000",
      "unit": "عدد",
      "movement_type": "IN",
      "movement_type_display": "ورود به انبار",
      "source_type": "PURCHASE",
      "source_type_display": "خرید",
      "movement_date": "2026-01-15T10:00:00Z",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

### 5.2 Create Stock Movement (Write – Admin/Inventory User)
**POST** `/stock-movements/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/stock-movements/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product": 10,
    "quantity": "5.000",
    "movement_type": "IN",
    "source_type": "MANUAL_ADJUSTMENT",
    "reference_id": "manual-001",
    "description": "اصلاح موجودی دستی"
  }'
```

**Sample Response** (201 Created):
```json
{
  "id": 6,
  "product": 10,
  "product_name": "آسپیرین 500mg",
  "product_code": "MED-001",
  "quantity": "5.000",
  "unit": "عدد",
  "movement_type": "IN",
  "movement_type_display": "ورود به انبار",
  "source_type": "MANUAL_ADJUSTMENT",
  "source_type_display": "تعدیل دستی",
  "reference_id": "manual-001",
  "movement_date": "2026-08-19T14:20:00Z",
  "description": "اصلاح موجودی دستی",
  "created_at": "2026-08-19T14:20:00Z",
  "updated_at": "2026-08-19T14:20:00Z"
}
```

### 5.3 Retrieve Stock Movement
**GET** `/stock-movements/{id}/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/stock-movements/6/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Note**: PUT / PATCH / DELETE are intentionally disabled.

---

## 6. Purchases

### 6.1 List Purchases
**GET** `/purchases/`

**Query Params**: `vendor`, `status`, `stock_applied`, `date_from`, `date_to`, `search`, `ordering`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/purchases/?vendor=1&status=CONFIRMED" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 5,
      "vendor": 1,
      "vendor_name": "داروسازی تهران",
      "reference_number": "PO-2026-001",
      "purchase_date": "2026-01-15T10:00:00Z",
      "status": "CONFIRMED",
      "status_display": "تأیید شده",
      "stock_applied": true,
      "item_count": 2,
      "average_unit_price": "15000.00",
      "total_amount": "150000.00",
      "product_names_display": "آسپیرین 500mg + 1 قلم دیگر",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

### 6.2 Retrieve Purchase
**GET** `/purchases/{id}/`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/purchases/5/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "id": 5,
  "vendor": 1,
  "vendor_name": "داروسازی تهران",
  "reference_number": "PO-2026-001",
  "purchase_date": "2026-01-15T10:00:00Z",
  "status": "CONFIRMED",
  "status_display": "تأیید شده",
  "notes": "",
  "stock_applied": true,
  "items": [
    {
      "id": 10,
      "purchase": 5,
      "product": 10,
      "product_name": "آسپیرین 500mg",
      "product_code": "MED-001",
      "quantity": "10.000",
      "unit": "عدد",
      "unit_price": "15000.00",
      "notes": "",
      "created_at": "2026-01-15T10:00:00Z",
      "updated_at": "2026-01-15T10:00:00Z"
    }
  ],
  "created_at": "2026-01-15T10:00:00Z",
  "updated_at": "2026-01-15T10:00:00Z"
}
```

### 6.3 Create Purchase (Write – Admin/Inventory User)
**POST** `/purchases/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/purchases/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "vendor": 1,
    "reference_number": "PO-2026-002",
    "purchase_date": "2026-08-19T10:00:00Z",
    "notes": "خرید جدید"
  }'
```

**Sample Response** (201 Created):
```json
{
  "id": 6,
  "vendor": 1,
  "vendor_name": "داروسازی تهران",
  "reference_number": "PO-2026-002",
  "purchase_date": "2026-08-19T10:00:00Z",
  "status": "PENDING",
  "status_display": "در انتظار تأیید",
  "notes": "خرید جدید",
  "stock_applied": false,
  "items": [],
  "created_at": "2026-08-19T14:25:00Z",
  "updated_at": "2026-08-19T14:25:00Z"
}
```

### 6.4 Update Purchase (PUT / PATCH)
**PATCH** `/purchases/{id}/`

```bash
curl -X PATCH "http://localhost:8001/api/v2/inventory/purchases/6/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "خرید جدید - اصلاح شده"}'
```

### 6.5 Confirm Purchase
**POST** `/purchases/{id}/confirm/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/purchases/6/confirm/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response** (200 OK):
```json
{
  "id": 6,
  "vendor": 1,
  "vendor_name": "داروسازی تهران",
  "reference_number": "PO-2026-002",
  "purchase_date": "2026-08-19T10:00:00Z",
  "status": "CONFIRMED",
  "status_display": "تأیید شده",
  "notes": "خرید جدید - اصلاح شده",
  "stock_applied": true,
  "items": [],
  "created_at": "2026-08-19T14:25:00Z",
  "updated_at": "2026-08-19T14:25:00Z"
}
```

### 6.6 Cancel Purchase
**POST** `/purchases/{id}/cancel/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/purchases/6/cancel/" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Response**: 200 OK with updated status `CANCELLED`.

### 6.7 Purchase Price History
**GET** `/purchases/price_history/?product=10`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/purchases/price_history/?product=10" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
[
  {
    "purchase_date": "2026-01-15T10:00:00Z",
    "vendor": 1,
    "vendor_name": "داروسازی تهران",
    "unit_price": "15000.00",
    "quantity": "10.000"
  },
  {
    "purchase_date": "2026-06-20T14:00:00Z",
    "vendor": 2,
    "vendor_name": "تجهیزات پزشکی پارس",
    "unit_price": "16000.00",
    "quantity": "20.000"
  }
]
```

### 6.8 Purchase Excel Export
**GET** `/purchases/?export=excel`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/purchases/?export=excel" \
  -H "Authorization: Token YOUR_TOKEN" \
  --output purchases.xlsx
```

---

## 7. Purchase Items

### 7.1 List Purchase Items
**GET** `/purchase-items/?purchase=6`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/purchase-items/?purchase=6" \
  -H "Authorization: Token YOUR_TOKEN"
```

### 7.2 Create Purchase Item
**POST** `/purchase-items/`

```bash
curl -X POST "http://localhost:8001/api/v2/inventory/purchase-items/" \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "purchase": 6,
    "product": 10,
    "quantity": "10.000",
    "unit_price": "15000.00",
    "notes": ""
  }'
```

**Sample Response** (201 Created):
```json
{
  "id": 15,
  "purchase": 6,
  "product": 10,
  "product_name": "آسپیرین 500mg",
  "product_code": "MED-001",
  "quantity": "10.000",
  "unit": "عدد",
  "unit_price": "15000.00",
  "notes": "",
  "created_at": "2026-08-19T14:30:00Z",
  "updated_at": "2026-08-19T14:30:00Z"
}
```

### 7.3 Update/Delete Purchase Item
**PATCH** `/purchase-items/{id}/`  
**DELETE** `/purchase-items/{id}/` – only if purchase is `PENDING`.

---

## 8. Reports

### 8.1 Inventory Stock Report
**GET** `/reports/stock/`

**Query Params**: `product_type`, `category`, `low_stock`, `out_of_stock`, `page`, `page_size`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/reports/stock/?product_type=medicine&low_stock=true" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "summary": {
    "total_products": 50,
    "low_stock_count": 5,
    "out_of_stock_count": 3,
    "total_inventory_value": "2500000.00"
  },
  "count": 5,
  "next": null,
  "previous": null,
  "page_size": 75,
  "total_pages": 1,
  "results": [
    {
      "id": 10,
      "name": "آسپیرین 500mg",
      "internal_code": "MED-001",
      "product_type": "medicine",
      "category": 3,
      "category_name": "آنتی‌بیوتیک",
      "unit": "عدد",
      "purchase_price": "15000.00",
      "current_stock": "10.000",
      "minimum_stock": "20.000",
      "is_low_stock": true,
      "is_out_of_stock": false,
      "inventory_value": "150000.00",
      "is_active": true
    }
  ]
}
```

### 8.2 Product Cost Report
**GET** `/reports/cost/`

**Query Params**: `start_date`, `end_date`, `product_type`, `group_by`, `vendor_id`, `page`, `page_size`, `export=excel`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/reports/cost/?start_date=2026-01-01&end_date=2026-08-19&group_by=vendor" \
  -H "Authorization: Token YOUR_TOKEN"
```

**Sample Response**:
```json
{
  "metadata": {
    "start_date": "2026-01-01",
    "end_date": "2026-08-19",
    "product_type": "all",
    "group_by": "vendor",
    "vendor_id": null,
    "total_cost": "1500000.00",
    "total_quantity": "100.000",
    "total_line_items": 10
  },
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "vendor_id": 1,
      "vendor_name": "داروسازی تهران",
      "total_quantity": "50.000",
      "total_cost": "750000.00",
      "avg_unit_price": "15000.00",
      "purchase_count": 5
    }
  ]
}
```

### 8.3 Product Cost Report Excel Export
**GET** `/reports/cost/?export=excel`

```bash
curl -X GET "http://localhost:8001/api/v2/inventory/reports/cost/?start_date=2026-01-01&end_date=2026-08-19&export=excel" \
  -H "Authorization: Token YOUR_TOKEN" \
  --output cost_report.xlsx
```

---

## 9. Error Codes Summary

| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request (validation error, malformed parameters) |
| 401 | Unauthorised (missing/invalid token) |
| 403 | Forbidden (insufficient permissions – read/write role mismatch) |
| 404 | Not Found |
| 405 | Method Not Allowed (e.g., DELETE on stock movement) |

---

## 10. Permission Summary

| Endpoint Type | Method | Required Permission |
|---------------|--------|---------------------|
| Categories | GET | `IsAuthenticated` |
| Products | GET | `IsAuthenticated` |
| Products | POST, PUT, PATCH | `IsAdminOrInventoryUser` |
| Products | DELETE | Blocked (use `purge`) |
| Products | `purge_preview`, `purge` | `IsMainAdministrator` |
| Vendors | GET | `IsAuthenticated` |
| Vendors | POST, PUT, PATCH, DELETE | `IsAdminOrInventoryUser` |
| Product-Vendors | GET | `IsAuthenticated` |
| Product-Vendors | POST, PUT, PATCH, DELETE | `IsAdminOrInventoryUser` |
| Stock Movements | GET | `IsAuthenticated` |
| Stock Movements | POST | `IsAdminOrInventoryUser` |
| Purchases | GET | `IsAuthenticated` |
| Purchases | POST, PUT, PATCH, DELETE | `IsAdminOrInventoryUser` |
| Purchases | `confirm`, `cancel` | `IsAdminOrInventoryUser` |
| Purchase Items | GET | `IsAuthenticated` |
| Purchase Items | POST, PUT, PATCH, DELETE | `IsAdminOrInventoryUser` |
| Reports | GET | `IsAdminOrFinanceUser` |
| Excel Export | GET with `export=excel` | Same as parent endpoint |