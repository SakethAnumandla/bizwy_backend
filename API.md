# Expense Tracker API Reference

**Base URL (local):** `http://localhost:8000`  
**Interactive docs:** [Swagger UI](http://localhost:8000/docs) | [ReDoc](http://localhost:8000/redoc)

**Authentication:** None (dev mode). All routes use auto-created user `devuser` via `get_default_user`.

**Content types:**
- JSON endpoints: `application/json`
- Upload endpoints: `multipart/form-data`

---

## Table of contents

1. [General](#general)
2. [Categories](#categories)
3. [Expenses](#expenses)
4. [OCR](#ocr)
5. [Wallet](#wallet)
6. [Dashboard](#dashboard)
7. [Shared enums](#shared-enums)
8. [Shared response models](#shared-response-models)

---

## General

### `GET /`

**Description:** API root.

**Output:**
```json
{ "message": "Expense Tracker API", "status": "running" }
```

---

### `GET /health`

**Description:** Health check.

**Output:**
```json
{ "status": "healthy" }
```

---

## Categories

### `GET /categories`

**Description:** Main and sub categories for dropdowns.

**Output:**
```json
{
  "main_categories": [{ "value": "travel", "label": "Travel" }, ...],
  "subcategories": {
    "travel": [{ "value": "uber", "label": "Uber" }, ...],
    "food": [...]
  }
}
```

---

### `GET /categories/hierarchy`

**Description:** Category hierarchy with icons/colors for UI.

**Output:**
```json
{
  "main_categories": [
    { "value": "travel", "display_name": "Travel & Transport", "icon": "🚗", "color": "#4CAF50" }
  ],
  "subcategories": { "travel": { "display_name": "...", "subcategories": { ... } } }
}
```

---

## Expenses

Prefix: `/expenses`

### `POST /expenses/manual`

**Description:** Create one expense manually (optional files). Supports draft.

**Content-Type:** `multipart/form-data`

| Input (form) | Type | Required | Notes |
|--------------|------|----------|--------|
| `bill_name` | string | yes | |
| `bill_amount` | float | yes | > 0 |
| `bill_date` | string | yes | `15/05/2026`, `2026-05-15`, ISO |
| `transaction_type` | string | yes | `expense`, `out`, `income`, `in` |
| `main_category` | enum | yes | See [MainCategory](#maincategory) |
| `sub_category` | string | no | e.g. `uber`, `dining` |
| `description` | string | no | Notes |
| `payment_method` | string | no | `cash`, `upi`, `credit_card`, … |
| `vendor_name` | string | no | |
| `bill_number` | string | no | |
| `tax_amount` | float | no | default `0` |
| `discount_amount` | float | no | default `0` |
| `files` | file[] | no | jpg, png, pdf, webp, … |
| `save_as_draft` | bool | no | default `false` → `pending` |

**Query:**

| Param | Type | Default | Notes |
|-------|------|---------|--------|
| `force_duplicate` | bool | `false` | Allow same file hash again |

**Output:** `201` → [ExpenseResponse](#expenseresponse)  
If duplicate file detected → `200` with `is_duplicate: true` and existing expense.

---

### `POST /expenses/upload-drafts`

**Description:** Upload **multiple files** → **one DRAFT per file** (no OCR). Prefill: filename, date, placeholder amount.

**Content-Type:** `multipart/form-data`

| Input | Type | Required |
|-------|------|----------|
| `files` | file[] | yes (min 1) |

**Output:** [MultiBillDraftResponse](#multibilldraftresponse)

---

### `GET /expenses/drafts`

**Description:** List draft expenses.

**Query:**

| Param | Type | Notes |
|-------|------|--------|
| `batch_id` | int | optional — drafts from OCR batch only |

**Output:** `ExpenseResponse[]`

---

### `GET /expenses`

**Description:** List expenses with filters and pagination.

**Query:**

| Param | Type | Notes |
|-------|------|--------|
| `skip` | int | default `0` |
| `limit` | int | default `100`, max `1000` |
| `sort_by` | string | model field name |
| `sort_desc` | bool | default `false` |
| `status` | enum | `draft`, `pending`, `approved`, `rejected` |
| `main_category` | enum | |
| `sub_category` | string | |
| `transaction_type` | enum | `income`, `expense` |
| `start_date` | datetime | |
| `end_date` | datetime | |
| `min_amount` | float | |
| `max_amount` | float | |
| `search` | string | bill name, vendor, description |
| `upload_method` | string | `manual`, `ocr` |

**Output:** `ExpenseResponse[]`

---

### `GET /expenses/{expense_id}`

**Description:** Get single expense.

**Output:** [ExpenseResponse](#expenseresponse)

---

### `GET /expenses/{expense_id}/details`

**Description:** Expense + full OCR extraction (tax, ride, items). Use on **bill details** screen after save.

**Output:** [ExpenseDetailResponse](#expensedetailresponse)

---

### `POST /expenses/{expense_id}/submit`

**Description:** Save/submit a **draft** bill (main fields + optional tax). Moves to `pending` or `approved`.

**Content-Type:** `application/json`

**Body:** [ExpenseSubmit](#expensesubmit)

**Output:** [ExpenseResponse](#expenseresponse)

---

### `PATCH /expenses/{expense_id}`

**Description:** Partial update (not allowed if `approved`).

**Body:** [ExpenseUpdate](#expenseupdate) (all fields optional)

**Output:** [ExpenseResponse](#expenseresponse)

---

### `POST /expenses/{expense_id}/approve`

**Description:** Approve or reject expense. Updates wallet on approve.

**Body:**
```json
{
  "status": "approved",
  "rejection_reason": null
}
```
`status`: `approved` | `rejected` | `pending`

**Output:** [ExpenseResponse](#expenseresponse)

---

### `DELETE /expenses/{expense_id}`

**Description:** Delete expense (not if `approved`).

**Output:** `204` No content

---

### File endpoints

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `POST` | `/expenses/{id}/files` | `files` (multipart) | `ExpenseFileResponse[]` |
| `GET` | `/expenses/{id}/files` | — | `ExpenseFileResponse[]` |
| `GET` | `/expenses/{id}/files/{file_id}` | Query: `download` (bool) | File stream |
| `GET` | `/expenses/{id}/files/{file_id}/thumbnail` | — | JPEG stream |
| `DELETE` | `/expenses/{id}/files/{file_id}` | — | `204` |
| `GET` | `/expenses/{id}/file` | Legacy primary file | File stream |
| `GET` | `/expenses/{id}/thumbnail` | Legacy thumbnail | JPEG stream |

**ExpenseFileResponse:**
```json
{
  "id": 1,
  "file_name": "receipt.pdf",
  "file_size": 288916,
  "mime_type": "application/pdf",
  "is_primary": true,
  "file_url": "/expenses/7/files/4",
  "thumbnail_url": "/expenses/7/files/4/thumbnail",
  "uploaded_at": "2026-05-15T09:32:27.622834Z"
}
```

---

## OCR

Prefix: `/ocr`

### `POST /ocr/scan-drafts` ⭐ Multi-bill (recommended)

**Description:** Scan **multiple** images/PDFs → **one DRAFT per file**. Returns Bill 1, Bill 2, … with **main fields only** prefilled. Drafts persist if user leaves without saving.

**Content-Type:** `multipart/form-data`

| Input | Type | Required |
|-------|------|----------|
| `files` | file[] | yes |

**Query:**

| Param | Type | Default |
|-------|------|---------|
| `force_rescan` | bool | `false` |

**Allowed types:** `jpg`, `jpeg`, `png`, `pdf`, `webp`

**Output:** [MultiBillDraftResponse](#multibilldraftresponse)

**Prefill fields only:** `bill_name`, `bill_amount`, `bill_date`, `transaction_type`, `main_category`, `sub_category`, `description`, `file_name`  
Tax/payment/ride details → stored in DB, exposed via `GET /expenses/{id}/details`.

---

### `GET /ocr/batch/{batch_id}/drafts`

**Description:** Reload all bills in a batch (resume editing later).

**Output:** [MultiBillDraftResponse](#multibilldraftresponse)

---

### `POST /ocr/scan`

**Description:** Single-file OCR → creates **one** expense (`pending` or `approved`).

**Content-Type:** `multipart/form-data`

| Input | Type | Required |
|-------|------|----------|
| `file` | file | yes |

**Query:**

| Param | Type | Default |
|-------|------|---------|
| `auto_approve` | bool | `false` |
| `force_rescan` | bool | `false` |

**Output:** [ExpenseResponse](#expenseresponse) (`is_duplicate: true` if same file hash)

---

### `POST /ocr/scan-batch`

**Description:** Background batch OCR (legacy — creates pending/approved expenses, not draft review flow).

**Input:** `files[]`, Query: `auto_approve`, `force_rescan`

**Output:**
```json
{
  "batch_id": 1,
  "total_files": 3,
  "processed_files": 0,
  "status": "processing",
  "message": "Processing 3 files in background",
  "status_url": "/ocr/batch/1/status"
}
```

---

### `GET /ocr/batch/{batch_id}/status`

**Description:** Poll batch job status.

**Output:** [OCRBatchStatusResponse](#ocrbatchstatusresponse)

---

### `GET /ocr/bills`

**Description:** List all OCR bill records for user.

**Output:** [OCRBillResponse](#ocrbillresponse)[]

---

### `GET /ocr/bills/{bill_id}`

**Description:** Single OCR bill record.

**Output:** [OCRBillResponse](#ocrbillresponse)

---

## Wallet

Prefix: `/wallet`

### `GET /wallet/balance`

**Output:** [WalletResponse](#walletresponse)

---

### `GET /wallet/transactions`

**Query:** `skip` (default 0), `limit` (default 50)

**Output:** [WalletTransactionResponse](#wallettransactionresponse)[]

---

### `GET /wallet/summary`

**Output:**
```json
{
  "current_balance": -3478.72,
  "total_income": 0.0,
  "total_expense": 3478.72,
  "net_savings": -3478.72
}
```

---

## Dashboard

Prefix: `/dashboard`

### `GET /dashboard/stats`

**Query:** `start_date`, `end_date` (optional; default last 30 days)

**Output:**
```json
{
  "total_balance": 0.0,
  "total_income": 0.0,
  "total_expense": 0.0,
  "pending_approvals": 0,
  "draft_expenses": 1
}
```

---

### `GET /dashboard/category-breakdown`

**Query:**

| Param | Values | Default |
|-------|--------|---------|
| `period` | `week`, `month`, `year` | `month` |
| `transaction_type` | `income`, `expense` | `expense` |

**Output:**
```json
[
  {
    "category": "travel",
    "total_amount": 113.01,
    "percentage": 45.5,
    "count": 2
  }
]
```

---

### `GET /dashboard/monthly-trend`

**Query:** `months` (1–24, default `6`)

**Output:**
```json
[
  { "month": "2026-05", "income": 6000.0, "expense": 1500.0, "net": 4500.0 }
]
```

---

### `GET /dashboard/recent-transactions`

**Query:** `limit` (1–50, default `10`)

**Output:** Array of `{ id, bill_name, bill_amount, bill_date, transaction_type, category, vendor_name }`

---

### `GET /dashboard/top-categories`

**Query:** `limit` (1–10, default `5`), `transaction_type` (default `expense`)

**Output:** Array of `{ category, total_amount, transaction_count, average_amount }`

---

### `GET /dashboard/daily-spending`

**Query:** `days` (7–90, default `30`)

**Output:** `[{ "date": "2026-05-15", "amount": 113.01 }]`

---

### `GET /dashboard/pending-approvals-summary`

**Output:**
```json
{
  "total_pending_count": 2,
  "total_pending_amount": 500.0,
  "by_category": { "food": { "count": 1, "total": 300.0 } },
  "oldest_pending": "2026-05-01T00:00:00Z",
  "newest_pending": "2026-05-15T00:00:00Z"
}
```

---

### `GET /dashboard/ocr-statistics`

**Output:**
```json
{
  "total_ocr_scans": 5,
  "approved_ocr_scans": 3,
  "pending_ocr_scans": 1,
  "total_ocr_amount": 832.7,
  "average_confidence_score": 85.0,
  "approval_rate": 60.0
}
```

---

### `GET /dashboard/budget-vs-actual`

**Query:** `month` (`YYYY-MM`, default current month)

**Output:**
```json
{
  "month": "2026-05",
  "categories": [
    { "category": "travel", "actual": 113.01, "budget": null }
  ]
}
```

---

### `GET /dashboard/export-data`

**Query:** `start_date`, `end_date` (required), `format` (`json` | `csv`)

**Output:** JSON array or CSV file download

---

### `GET /dashboard/quick-insights`

**Output:**
```json
{
  "top_spending_category": { "category": "food", "amount": 500.0 },
  "average_daily_spending": 45.2,
  "biggest_expense": {
    "name": "Uber — Trip",
    "amount": 113.01,
    "category": "travel",
    "date": "2025-11-15T00:00:00Z"
  },
  "most_frequent_category": { "category": "food", "count": 5 },
  "total_transactions": 12,
  "total_spent": 1356.0
}
```

---

## Shared enums

### TransactionType
`income` | `expense`  

**Aliases (manual/OCR input):**  
- Expense: `out`, `debit`, `spend`, `spent`, `payment`, `paid`  
- Income: `in`, `credit`, `received`, `earn`, `earning`

### ExpenseStatus
`draft` | `pending` | `approved` | `rejected`

### MainCategory
`travel` | `food` | `bills` | `shopping` | `entertainment` | `healthcare` | `education` | `fuel` | `insurance` | `investment` | `salary` | `rent` | `utilities` | `groceries` | `personal_care` | `subscriptions` | `miscellaneous`

### PaymentMethod (string on API)
`cash` | `credit_card` | `debit_card` | `upi` | `net_banking` | `wallet` | `crypto`

### UploadMethod
`manual` | `ocr`

---

## Shared response models

### ExpenseResponse

```json
{
  "id": 8,
  "user_id": 1,
  "bill_name": "Rickys bill",
  "bill_amount": 6000.0,
  "bill_date": "2026-05-15T00:00:00Z",
  "transaction_type": "income",
  "main_category": "salary",
  "sub_category": null,
  "description": "optional notes",
  "payment_method": null,
  "vendor_name": null,
  "bill_number": null,
  "tax_amount": 0.0,
  "discount_amount": 0.0,
  "status": "draft",
  "upload_method": "manual",
  "files": [],
  "rejection_reason": null,
  "created_at": "2026-05-15T09:44:44Z",
  "updated_at": null,
  "approved_at": null,
  "file_url": null,
  "thumbnail_url": null,
  "file_name": null,
  "file_size": null,
  "mime_type": null,
  "is_duplicate": false
}
```

---

### MultiBillDraftResponse

```json
{
  "batch_id": 2,
  "bills": [
    {
      "bill_index": 1,
      "label": "Bill 1",
      "expense_id": 9,
      "is_duplicate": false,
      "prefill": {
        "bill_name": "Bill 1 — Madhuri's Kitchen",
        "bill_amount": 605.0,
        "bill_date": "2026-05-15T00:00:00Z",
        "transaction_type": "expense",
        "main_category": "food",
        "sub_category": "dining",
        "description": null,
        "file_name": "receipt.png",
        "amount_needs_review": false
      }
    },
    {
      "bill_index": 2,
      "label": "Bill 2",
      "expense_id": 10,
      "is_duplicate": false,
      "prefill": { }
    }
  ],
  "failed": [],
  "skipped_duplicates": [],
  "message": "Created 2 draft bill(s). Review Bill 1…2 and save when ready."
}
```

---

### ExpenseDetailResponse

Extends `ExpenseResponse` with:

```json
{
  "ocr_details": {
    "id": 3,
    "bill_number": "1208",
    "vendor_name": "Madhuri's Kitchen",
    "vendor_gst": "M43010GH195260",
    "subtotal": 550.0,
    "total_amount": 605.0,
    "tax_amount": 55.0,
    "tax_breakdown": { "cgst": 27.5, "sgst": 27.5 },
    "payment_method": "cash",
    "ride_distance": null,
    "ride_duration": null,
    "ride_type": null,
    "pickup_location": null,
    "dropoff_location": null,
    "restaurant_name": "Madhuri's Kitchen",
    "items_list": [{ "name": "Panner Tikka", "price": 250.0 }],
    "customer_name": "Abhinav YS",
    "confidence_score": 95.0
  }
}
```

---

### ExpenseSubmit

```json
{
  "bill_name": "Rickys bill",
  "bill_amount": 6000,
  "bill_date": "2026-05-15T00:00:00Z",
  "transaction_type": "income",
  "main_category": "salary",
  "sub_category": null,
  "description": "optional notes",
  "payment_method": "cash",
  "vendor_name": null,
  "bill_number": null,
  "tax_amount": 0,
  "discount_amount": 0,
  "save_as_pending": true,
  "auto_approve": false
}
```

---

### ExpenseUpdate

All optional: `bill_name`, `bill_amount`, `bill_date`, `main_category`, `sub_category`, `description`, `status`, `vendor_name`, `bill_number`

---

### WalletResponse

```json
{
  "id": 1,
  "user_id": 1,
  "balance": -3478.72,
  "total_income": 0.0,
  "total_expense": 3478.72,
  "created_at": "2026-05-15T08:37:26Z",
  "updated_at": "2026-05-15T09:32:28Z"
}
```

---

### WalletTransactionResponse

```json
{
  "id": 1,
  "amount": 113.01,
  "transaction_type": "expense",
  "transaction_date": "2026-05-15T09:32:28Z",
  "description": "Expense: Uber — Trip",
  "expense_id": 7
}
```

---

### OCRBillResponse

```json
{
  "id": 1,
  "user_id": 1,
  "expense_id": 7,
  "batch_id": 2,
  "bill_number": "1208",
  "bill_date": "2026-05-15T00:00:00Z",
  "vendor_name": "Uber",
  "total_amount": 113.01,
  "tax_amount": 5.89,
  "confidence_score": 90.0,
  "ride_distance": 14.64,
  "pickup_location": "...",
  "dropoff_location": "...",
  "restaurant_name": null,
  "items_list": [],
  "processed_at": "2026-05-15T09:32:27Z"
}
```

---

### OCRBatchStatusResponse

```json
{
  "batch_id": 1,
  "status": "completed",
  "total_files": 2,
  "processed_files": 2,
  "batch_name": "Drafts_20260515_100757",
  "created_at": "2026-05-15T10:07:57Z",
  "completed_at": "2026-05-15T10:08:10Z",
  "expenses": [],
  "failed_files": [],
  "skipped_duplicates": [
    { "bill_index": 1, "file_name": "uber.pdf", "existing_expense_id": 7 }
  ]
}
```

---

## Flutter / frontend flow (multi-bill)

1. User picks multiple files → `POST /ocr/scan-drafts` with `files[]`
2. Map `bills[]` to tabs: **Bill 1**, **Bill 2**, … using `prefill` for form fields
3. User edits and saves each → `POST /expenses/{expense_id}/submit`
4. Bill details screen → `GET /expenses/{expense_id}/details` (shows `ocr_details`)
5. User leaves app → drafts remain; reload via `GET /ocr/batch/{batch_id}/drafts` or `GET /expenses/drafts?batch_id=`

**Duplicate files:** Same SHA-256 returns existing `expense_id` with `is_duplicate: true` (no new wallet entry).

---

## Error responses

Typical format:
```json
{ "detail": "Expense not found" }
```

| Code | Meaning |
|------|---------|
| `400` | Validation / business rule |
| `404` | Not found |
| `500` | Server / OCR failure |

---

*Generated for Expense Tracker API v1.0.0*
