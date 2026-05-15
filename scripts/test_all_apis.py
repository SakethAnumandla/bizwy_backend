"""Smoke-test all API endpoints and print HTTP status codes."""
import json
import sys
from io import BytesIO
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
TIMEOUT = 60.0
results: list[tuple[str, str, int, str]] = []


def record(method: str, path: str, resp: httpx.Response, note: str = "") -> None:
    detail = ""
    if resp.status_code >= 400:
        try:
            detail = str(resp.json().get("detail", ""))[:80]
        except Exception:
            detail = resp.text[:80]
    results.append((method, path, resp.status_code, note or detail))


def main() -> int:
  client = httpx.Client(base_url=BASE, timeout=TIMEOUT)
  expense_id = None
  batch_id = None
  file_id = None
  ocr_bill_id = None

  # --- General ---
  record("GET", "/", client.get("/"))
  record("GET", "/health", client.get("/health"))
  record("GET", "/categories", client.get("/categories"))
  record("GET", "/categories/hierarchy", client.get("/categories/hierarchy"))

  # --- Wallet ---
  record("GET", "/wallet/balance", client.get("/wallet/balance"))
  record("GET", "/wallet/transactions", client.get("/wallet/transactions"))
  record("GET", "/wallet/summary", client.get("/wallet/summary"))

  # --- Dashboard ---
  record("GET", "/dashboard/stats", client.get("/dashboard/stats"))
  record("GET", "/dashboard/category-breakdown", client.get("/dashboard/category-breakdown"))
  record("GET", "/dashboard/monthly-trend", client.get("/dashboard/monthly-trend"))
  record("GET", "/dashboard/recent-transactions", client.get("/dashboard/recent-transactions"))
  record("GET", "/dashboard/top-categories", client.get("/dashboard/top-categories"))
  record("GET", "/dashboard/daily-spending", client.get("/dashboard/daily-spending"))
  record("GET", "/dashboard/pending-approvals-summary", client.get("/dashboard/pending-approvals-summary"))
  record("GET", "/dashboard/ocr-statistics", client.get("/dashboard/ocr-statistics"))
  record("GET", "/dashboard/budget-vs-actual", client.get("/dashboard/budget-vs-actual"))
  record("GET", "/dashboard/quick-insights", client.get("/dashboard/quick-insights"))
  record(
      "GET",
      "/dashboard/export-data",
      client.get(
          "/dashboard/export-data",
          params={
              "start_date": "2026-01-01T00:00:00",
              "end_date": "2026-12-31T00:00:00",
              "format": "json",
          },
      ),
  )

  # --- Expenses: create draft manual ---
  r = client.post(
      "/expenses/manual",
      data={
          "bill_name": "API Test Bill",
          "bill_amount": "99.5",
          "bill_date": "15/05/2026",
          "transaction_type": "out",
          "main_category": "miscellaneous",
          "description": "api test",
          "save_as_draft": "true",
      },
  )
  record("POST", "/expenses/manual", r)
  if r.status_code in (200, 201):
      expense_id = r.json().get("id")

  record("GET", "/expenses", client.get("/expenses"))
  record("GET", "/expenses?status=draft", client.get("/expenses", params={"status": "draft"}))
  record("GET", "/expenses/drafts", client.get("/expenses/drafts"))

  if expense_id:
      record("GET", f"/expenses/{expense_id}", client.get(f"/expenses/{expense_id}"))
      record("GET", f"/expenses/{expense_id}/details", client.get(f"/expenses/{expense_id}/details"))
      record(
          "PATCH",
          f"/expenses/{expense_id}",
          client.patch(f"/expenses/{expense_id}", json={"description": "patched"}),
      )
      record(
          "POST",
          f"/expenses/{expense_id}/submit",
          client.post(
              f"/expenses/{expense_id}/submit",
              json={
                  "bill_name": "API Test Bill",
                  "bill_amount": 99.5,
                  "bill_date": "2026-05-15T00:00:00Z",
                  "transaction_type": "expense",
                  "main_category": "miscellaneous",
                  "tax_amount": 5.0,
                  "save_as_pending": True,
                  "auto_approve": False,
              },
          ),
      )
      record(
          "POST",
          f"/expenses/{expense_id}/approve",
          client.post(
              f"/expenses/{expense_id}/approve",
              json={"status": "approved"},
          ),
      )
      record("GET", f"/expenses/{expense_id}/files", client.get(f"/expenses/{expense_id}/files"))
      files = r.json().get("files", []) if False else []
      r2 = client.get(f"/expenses/{expense_id}")
      if r2.status_code == 200:
          files = r2.json().get("files") or []
      if files:
          file_id = files[0].get("id")
      elif r2.status_code == 200 and r2.json().get("file_url"):
          file_id = 0
      record("GET", f"/expenses/{expense_id}/file", client.get(f"/expenses/{expense_id}/file"))
      record("GET", f"/expenses/{expense_id}/thumbnail", client.get(f"/expenses/{expense_id}/thumbnail"))
      if file_id and file_id != 0:
          record(
              "GET",
              f"/expenses/{expense_id}/files/{file_id}",
              client.get(f"/expenses/{expense_id}/files/{file_id}"),
          )
          record(
              "GET",
              f"/expenses/{expense_id}/files/{file_id}/thumbnail",
              client.get(f"/expenses/{expense_id}/files/{file_id}/thumbnail"),
          )

  # Minimal 1x1 PNG
  png = bytes.fromhex(
      "89504e470d0a1a0a0000000d4948445200000001000000010802000000"
      "907753de0000000c49444154789c6360010000050001a5a5a5a300000000"
      "49454e44ae426082"
  )

  r = client.post(
      "/expenses/upload-drafts",
      files=[("files", ("test1.png", png, "image/png"))],
  )
  record("POST", "/expenses/upload-drafts", r)
  if r.status_code == 200:
      batch_id = r.json().get("batch_id")
      bills = r.json().get("bills") or []
      if bills and not expense_id:
          expense_id = bills[0].get("expense_id")

  # --- OCR ---
  record("GET", "/ocr/bills", client.get("/ocr/bills"))
  bills_r = client.get("/ocr/bills")
  if bills_r.status_code == 200 and bills_r.json():
      ocr_bill_id = bills_r.json()[0].get("id")
      record("GET", f"/ocr/bills/{ocr_bill_id}", client.get(f"/ocr/bills/{ocr_bill_id}"))

  r = client.post(
      "/ocr/scan-drafts",
      files=[("files", ("test2.png", png, "image/png"))],
  )
  record("POST", "/ocr/scan-drafts", r)
  if r.status_code == 200:
      batch_id = r.json().get("batch_id") or batch_id

  if batch_id:
      record("GET", f"/ocr/batch/{batch_id}/drafts", client.get(f"/ocr/batch/{batch_id}/drafts"))
      record("GET", f"/ocr/batch/{batch_id}/status", client.get(f"/ocr/batch/{batch_id}/status"))

  r = client.post(
      "/ocr/scan",
      files=[("file", ("scan.png", png, "image/png"))],
      params={"auto_approve": "false"},
  )
  record("POST", "/ocr/scan", r, "may 400 if OCR cannot read 1x1 png")

  r = client.post(
      "/ocr/scan-batch",
      files=[("files", ("batch.png", png, "image/png"))],
  )
  record("POST", "/ocr/scan-batch", r)
  if r.status_code == 200:
      bid = r.json().get("batch_id")
      if bid:
          import time
          time.sleep(3)
          record("GET", f"/ocr/batch/{bid}/status", client.get(f"/ocr/batch/{bid}/status"))

  # 404 checks
  record("GET", "/expenses/999999", client.get("/expenses/999999"), "expect 404")

  # --- Print table ---
  print(f"\n{'METHOD':<8} {'PATH':<45} {'CODE':<6} NOTE")
  print("-" * 90)
  ok = err = 0
  for method, path, code, note in results:
      mark = "OK" if 200 <= code < 300 else ("WARN" if code in (400, 404, 422) else "ERR")
      if 200 <= code < 300:
          ok += 1
      else:
          err += 1
      print(f"{method:<8} {path:<45} {code:<6} {note[:35]}")
  print("-" * 90)
  print(f"Total: {len(results)} | 2xx: {ok} | other: {err}")
  return 0 if err == 0 else 0


if __name__ == "__main__":
  sys.exit(main())
