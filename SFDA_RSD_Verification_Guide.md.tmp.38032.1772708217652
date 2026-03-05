# SFDA RSD Transaction Verification Guide

Technical guide for verifying, troubleshooting, and auditing SFDA Drug Track & Trace (DTTS) transactions in the `sfda_rsd` ERPNext app.

---

## 0. Prerequisites & Setup

Before any RSD transaction can fire, **all** of the following must be in place. A missing step in this section is the #1 reason transactions silently do nothing.

### 0.1 Install & Migrate

```bash
bench get-app sfda_rsd          # if not already installed
bench --site your-site install-app sfda_rsd
bench --site your-site migrate   # creates custom fields on Item, Supplier, Customer, Warehouse, Batch
bench restart                    # picks up new hooks and scheduled tasks
```

After `bench migrate`, the following custom fields are automatically created:

| DocType | Field | Type | Description |
|---|---|---|---|
| **Item** | `custom_rsd_section` | Section Break | "SFDA RSD" collapsible section (appears after Barcodes) |
| **Item** | `custom_gtin` | Data (14 chars) | The 14-digit Global Trade Item Number for this product |
| **Item** | `custom_is_rsd_tracked` | Check | Must be checked to enable SFDA tracking for this item |
| **Supplier** | `custom_gln` | Data (13 chars) | Supplier's 13-digit Global Location Number from SFDA |
| **Customer** | `custom_gln` | Data (13 chars) | Customer's 13-digit GLN (leave empty for end consumers) |
| **Warehouse** | `custom_gln` | Data (13 chars) | Warehouse GLN (optional) |
| **Batch** | `custom_rsd_supplied` | Check (read-only) | Auto-set when batch is notified to SFDA |

### 0.2 RSD Settings Configuration

Go to **RSD Settings** (`/app/rsd-settings`) and configure:

| Field | Required | Description |
|---|---|---|
| **Enabled** | Yes | Check this to activate the integration |
| **Environment** | Yes | `Test` (tandttest.sfda.gov.sa) or `Production` (rsd.sfda.gov.sa) |
| **DTTS Username** | Yes | Your SFDA DTTS portal username |
| **DTTS Password** | Yes | Your SFDA DTTS portal password |
| **Stakeholder GLN** | Yes | Your pharmacy's 13-digit GLN registered with SFDA |
| **Establishment GLN** | No | Parent establishment GLN (if applicable) |
| **Default Tracking Mode** | No | `Auto` (default) / `Serial Number` / `Batch Number` |
| **Pharmacy Sale TOGLN** | No | Default `0000000000000` for direct patient sales |
| **Max Retries** | No | Default `3` — how many times to retry failed SFDA calls |
| **Timeout (seconds)** | No | Default `60` — SOAP call timeout |
| **Log Raw XML** | No | Default checked — logs full SOAP request/response XML |

Use the **Test Connection** button (appears when Enabled is checked) to verify network connectivity and credentials before submitting any documents.

### 0.3 Item Setup

For each pharmaceutical product you want to track with SFDA:

1. Open the **Item** master record
2. Scroll to the **SFDA RSD** section (below Barcodes)
3. Fill in **GTIN (14-digit)** — the full 14-digit Global Trade Item Number (e.g., `06281100000123`)
4. Check **Track in SFDA RSD**
5. Ensure the item has either **Has Serial No** or **Has Batch No** checked (under Inventory section)

> **Important**: If neither `Has Serial No` nor `Has Batch No` is enabled on the Item, the RSD hook will skip that item because there's no serial number or batch number to report to SFDA.

### 0.4 Supplier Setup (for Purchase Receipt / Accept)

For each supplier you receive drugs from:

1. Open the **Supplier** master record
2. Fill in **GLN Number** — the supplier's 13-digit GLN (e.g., `6281100000456`)

> **If the Supplier has no GLN**, the Purchase Receipt `on_submit` hook will silently skip all items. No queue entry is created. This is the most common reason "nothing happened" on submit.

### 0.5 Customer Setup (for Delivery Note / Dispatch and Sales Invoice / Pharmacy Sale)

| Scenario | Customer GLN | What happens on submit |
|---|---|---|
| **B2B dispatch** (to another pharmacy/distributor) | Fill in GLN | Delivery Note triggers **DispatchService** |
| **Retail / Patient sale** (pharmacy sale) | Leave GLN **empty** | Sales Invoice triggers **PharmacySaleService** |
| **B2B customer, Sales Invoice** | Fill in GLN | Sales Invoice does **nothing** (handled by Delivery Note instead) |

### 0.6 Document Requirements per Transaction Type

| ERPNext Document | SFDA Service Triggered | Required Setup |
|---|---|---|
| **Purchase Receipt** (submit) | AcceptService / AcceptBatchService | Item: GTIN + RSD tracked. Supplier: GLN. Line item: serial_no or batch_no |
| **Sales Invoice** (submit) | PharmacySaleService | Item: GTIN + RSD tracked. Customer: NO GLN (end consumer). Line item: serial_no |
| **Delivery Note** (submit) | DispatchService / DispatchBatchService | Item: GTIN + RSD tracked. Customer: HAS GLN (B2B). Line item: serial_no or batch_no |
| **Stock Entry - Material Issue** (submit) | DeactivationService | Item: GTIN + RSD tracked. Line item: serial_no. Purpose must be "Material Issue" |

### 0.7 Serial Number vs Batch Number Mode

The hook auto-detects which SFDA service to use based on the line item:

| Line Item Has | Service Used | Example |
|---|---|---|
| `serial_no` (with or without `batch_no`) | Serial-level service (e.g., AcceptService) | One SFDA call per serial number |
| `batch_no` only (no `serial_no`) | Batch-level service (e.g., AcceptBatchService) | One SFDA call with GTIN + BN + QUANTITY |
| Neither | **Skipped** — no SFDA notification | Item must have serial or batch tracking enabled |

### 0.8 Quick Validation Checklist (Before First Test)

- [ ] `bench migrate` has been run after installing the app
- [ ] RSD Settings: Enabled = checked
- [ ] RSD Settings: Environment = Test (for initial testing)
- [ ] RSD Settings: Username, Password, Stakeholder GLN filled
- [ ] RSD Settings: **Test Connection** button shows "Pass" for both steps
- [ ] Test Item: `custom_gtin` filled with 14-digit GTIN
- [ ] Test Item: `custom_is_rsd_tracked` checked
- [ ] Test Item: `Has Serial No` or `Has Batch No` enabled
- [ ] Test Supplier (for Purchase Receipt): `custom_gln` filled with 13-digit GLN
- [ ] Test Customer (for Sales Invoice): `custom_gln` is **empty** (pharmacy sale to consumer)
- [ ] Test Customer (for Delivery Note): `custom_gln` filled with 13-digit GLN
- [ ] Scheduler is running: `bench doctor` shows no issues
- [ ] Purchase Receipt line item has a serial number or batch number entered

---

## 1. Transaction Flow Overview

Every SFDA RSD transaction follows this pipeline:

```
ERPNext Document (Submit)
    -> Doc Event Handler (rsd_api.py)
    -> RSD Notification Queue (Pending)
    -> RSD Connector (SOAP call to SFDA)
    -> RSD Transaction Log (request/response XML)
    -> RSD Drug Unit (status update)
```

To verify a transaction, trace it through each stage.

---

## 2. Check the RSD Notification Queue

The queue is the first place to look. Every SFDA notification starts here.

### Access
- **Desk URL**: `/app/rsd-notification-queue`
- **List filters**: Filter by `status`, `service_name`, `reference_doctype`, `reference_name`

### Statuses

| Status | Meaning |
|---|---|
| **Pending** | Queued, not yet processed |
| **Processing** | Currently being sent to SFDA |
| **Completed** | SFDA accepted the notification |
| **Failed** | SFDA rejected or connection error occurred |

### What to check
1. **Find the queue entry** for your document:
   - Filter by `reference_doctype` (e.g., "Sales Invoice") and `reference_name` (e.g., "SINV-00123")
2. **Check `status`**: Should be "Completed" for successful transactions
3. **Check `retry_count`**: If > 0, the notification failed and was retried
4. **Check `last_error`**: Contains the traceback for the most recent failure
5. **Check `parameters`**: JSON payload that was/will be sent to SFDA

### Via Bench Console
```python
# Find queue entries for a specific document
frappe.get_all("RSD Notification Queue",
    filters={"reference_doctype": "Sales Invoice", "reference_name": "SINV-00123"},
    fields=["name", "service_name", "status", "retry_count", "last_error"]
)

# Count pending/failed entries
frappe.db.count("RSD Notification Queue", {"status": ["in", ["Pending", "Failed"]]})
```

---

## 3. Inspect RSD Transaction Logs

Transaction logs record the actual SOAP XML exchanged with SFDA. Only created when `Log XML` is enabled in RSD Settings.

### Access
- **Desk URL**: `/app/rsd-transaction-log`
- **List filters**: Filter by `service_name`, `status`, `timestamp`

### Key Fields

| Field | What it tells you |
|---|---|
| `service_name` | Which SFDA service was called (e.g., AcceptService, PharmacySaleService) |
| `operation` | SOAP operation name (e.g., AcceptServiceRequest) |
| `status` | Success or Error |
| `request_xml` | Full SOAP envelope sent to SFDA (includes WS-Security headers) |
| `response_xml` | Full SOAP envelope received from SFDA (includes per-product RC codes) |
| `error_message` | Human-readable error summary |
| `parameters` | JSON of the parameters passed to the SOAP call |
| `stakeholder_gln` | Your GLN used for this transaction |

### How to read the Response XML

The response XML contains per-product result codes. Look for `<RC>` elements:

```xml
<PRODUCTLIST>
  <PRODUCT>
    <GTIN>06281100000123</GTIN>
    <SN>ABC123</SN>
    <RC>00000</RC>
  </PRODUCT>
  <PRODUCT>
    <GTIN>06281100000123</GTIN>
    <SN>DEF456</SN>
    <RC>10305</RC>
  </PRODUCT>
</PRODUCTLIST>
```

- `RC=00000` or `RC=10201` = Success
- Any other RC = Failure for that specific product

### Via Bench Console
```python
# Get recent error logs
logs = frappe.get_all("RSD Transaction Log",
    filters={"status": "Error"},
    fields=["name", "service_name", "error_message", "timestamp"],
    order_by="timestamp desc",
    limit=10
)

# Read full XML for a specific log
log = frappe.get_doc("RSD Transaction Log", "RSD-LOG-000042")
print(log.request_xml)
print(log.response_xml)
```

---

## 4. Verify RSD Drug Unit Status

After a successful SFDA notification, the corresponding Drug Unit record is updated.

### Access
- **Desk URL**: `/app/rsd-drug-unit`
- **Filter by**: `gtin`, `serial_number`, `batch_number`, `status`

### Expected Status After Each Operation

| Operation | Expected Drug Unit Status |
|---|---|
| AcceptService / AcceptBatchService | Accepted |
| PharmacySaleService | Sold |
| DeactivationService | Deactivated |
| DeactivationCancelService | Accepted |
| DispatchService / DispatchBatchService | Dispatched |
| DispatchCancelService | Accepted |
| ReturnService / ReturnBatchService | Returned |
| TransferService / TransferBatchService | Dispatched |
| TransferCancelService | Accepted |
| PharmacySaleCancelService | Accepted |
| SupplyService | Supplied |
| ExportService | Exported |
| ConsumeService | Consumed |

### What to check
1. **Status matches the last operation**: If you sold a product, status should be "Sold"
2. **`last_notification_type`**: Should match the service name (e.g., "PharmacySaleService")
3. **`last_notification_at`**: Timestamp of the last successful SFDA notification
4. **`current_holder_gln`**: Updated to your GLN after accept/sale/dispatch

### Via Bench Console
```python
# Look up a specific drug unit
du = frappe.get_all("RSD Drug Unit",
    filters={"gtin": "06281100000123", "serial_number": "ABC123"},
    fields=["name", "status", "last_notification_type", "last_notification_at", "current_holder_gln"]
)
```

---

## 5. Query SFDA Directly (CheckStatus)

Use the `check_status` API to query SFDA's system for the current status of a drug unit. This is the definitive source of truth.

### From the Desk (Browser Console)
```javascript
frappe.call({
    method: "sfda_rsd.sfda_rsd.sfda_rsd.api.rsd_api.check_status",
    args: {
        gtin: "06281100000123",
        serial_number: "ABC123"
    },
    callback: function(r) {
        console.log(r.message);
    }
});
```

### From Bench Console
```python
from sfda_rsd.sfda_rsd.connectors.services.query_service import check_status
result = check_status("06281100000123", "ABC123")
print(result)
```

### From URL (GET)
```
/api/method/sfda_rsd.sfda_rsd.sfda_rsd.api.rsd_api.check_status?gtin=06281100000123&serial_number=ABC123
```

The response will include the product's current status, holder GLN, and last notification details as known by SFDA.

---

## 6. Retry Failed Notifications

### Automatic Retry
A scheduled job runs every 15 minutes to retry failed/pending notifications (up to `max_retries` from RSD Settings, default 3).

### Manual Retry
```javascript
// From browser console
frappe.call({
    method: "sfda_rsd.sfda_rsd.sfda_rsd.api.rsd_api.retry_failed",
    callback: function(r) {
        console.log(r.message);  // {"status": "ok", "message": "Retry triggered"}
    }
});
```

### From Bench Console
```python
from sfda_rsd.sfda_rsd.connectors.rsd_connector import retry_failed_notifications
retry_failed_notifications()
```

### Manually Reprocess a Specific Queue Entry
```python
import frappe
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector

entry = frappe.get_doc("RSD Notification Queue", "RSD-Q-000015")
connector = RSDConnector()
params = frappe.parse_json(entry.parameters)
response = connector.call_service(entry.service_name, entry.operation, params)

# If successful, update queue status
frappe.db.set_value("RSD Notification Queue", entry.name, "status", "Completed")
frappe.db.commit()
```

---

## 7. SFDA Response Code Reference

### Success Codes
| Code | Meaning |
|---|---|
| `00000` | Operation successful |
| `10201` | Product already in requested state (idempotent success) |

### Common Error Codes
Use the `get_error_codes` API to look up any code:

```javascript
frappe.call({
    method: "sfda_rsd.sfda_rsd.sfda_rsd.api.rsd_api.get_error_codes",
    args: { error_code: "10305" },
    callback: function(r) { console.log(r.message); }
});
```

Or fetch the full error code list:
```python
from sfda_rsd.sfda_rsd.connectors.services.query_service import get_error_codes
codes = get_error_codes()
```

---

## 8. End-to-End Verification Checklist

Use this checklist to verify a transaction from start to finish.

### Step 1: Document Created
- [ ] ERPNext document submitted (e.g., Sales Invoice, Purchase Receipt)
- [ ] Item has `custom_is_rsd_tracked = 1`
- [ ] Item has `custom_gtin` set
- [ ] Item has `serial_no` or `batch_no` on the line item
- [ ] For Purchase Receipt: Supplier has `custom_gln` set
- [ ] For Delivery Note: Customer has `custom_gln` set (B2B dispatch)
- [ ] For Sales Invoice: Customer has NO `custom_gln` (pharmacy sale to consumer)

### Step 2: Queue Entry Created
- [ ] RSD Notification Queue entry exists with `reference_name` = document name
- [ ] `service_name` is correct for the operation type
- [ ] `parameters` JSON contains correct GTIN, SN/BN, FROMGLN/TOGLN
- [ ] `status` = "Pending" initially

### Step 3: SFDA Call Executed
- [ ] Queue entry status changed from "Pending" to "Completed" (or "Failed")
- [ ] RSD Transaction Log entry created (if `Log XML` enabled)
- [ ] Transaction Log `status` = "Success"
- [ ] Response XML contains `<RC>00000</RC>` for each product

### Step 4: Drug Unit Updated
- [ ] RSD Drug Unit record exists for each GTIN+SN combination
- [ ] `status` matches expected value (see table in Section 4)
- [ ] `last_notification_type` matches the service name
- [ ] `last_notification_at` is recent

### Step 5: Cross-Verify with SFDA
- [ ] `check_status` API returns matching status from SFDA's system
- [ ] Holder GLN matches your stakeholder GLN (for accepted/sold products)

---

## 9. Troubleshooting Common Issues

### Nothing happened after submitting a Purchase Receipt / Sales Invoice / Delivery Note
This is the most common issue. The hook ran but silently exited because a prerequisite was missing. Check in this order:

1. **RSD Settings not enabled** — Go to `/app/rsd-settings` and verify `Enabled` is checked
2. **Item not tracked** — Open the Item, scroll to "SFDA RSD" section, verify `Track in SFDA RSD` is checked AND `GTIN (14-digit)` is filled
3. **No serial/batch on line item** — The Purchase Receipt / Sales Invoice line item must have a `serial_no` or `batch_no`. If the Item doesn't have `Has Serial No` or `Has Batch No` enabled, the hook skips it
4. **Supplier missing GLN** (Purchase Receipt only) — Open the Supplier record, verify `GLN Number` is filled with a 13-digit GLN. Without this, the entire Purchase Receipt is skipped
5. **Customer has GLN** (Sales Invoice only) — Pharmacy Sale only fires for customers WITHOUT a GLN (end consumers). If the Customer has a GLN, the hook assumes it's B2B and skips the invoice
6. **Customer missing GLN** (Delivery Note only) — Dispatch only fires for customers WITH a GLN. If the Customer has no GLN, the Delivery Note is skipped
7. **Check Error Log** — Go to `/app/error-log` and search for "RSD" — import errors or exceptions will appear here

### "RSD Integration is not enabled"
- Go to **RSD Settings** and check `Enabled`
- Ensure `username`, `password`, and `stakeholder_gln` are filled

### Queue entries stuck in "Pending"
- Check that the scheduler is running: `bench doctor`
- Manually trigger: call `retry_failed` API
- Check Error Log for scheduler errors

### SOAP Fault in Transaction Log
- Read the `error_message` field for details
- Common causes: invalid credentials, expired session, network timeout
- Check `request_xml` to verify the SOAP envelope structure
- Test connectivity: try `check_status` for a known product

### Partial Success (Some Products Failed)
- The Transaction Log `status` will be "Error" with `error_summary` listing failed GTINs
- Successful products within the same batch ARE updated in RSD Drug Unit
- Failed products need individual investigation using their RC code

### "Product not in expected state" (RC != 00000)
- Product may have already been accepted/sold/dispatched by another entity
- Use `check_status` to see current SFDA state
- If product was already processed, RC `10201` means idempotent success

### Drug Unit not updated after successful call
- Verify the service name exists in `SERVICE_STATUS_MAP` in `rsd_connector.py`
- Check Error Log for "Failed to update RSD Drug Unit" messages
- Verify the GTIN and SN in the response match existing Drug Unit records

---

## 10. Useful SQL Queries

Run from **Bench Console** or **MariaDB** directly.

```sql
-- Failed notifications in the last 24 hours
SELECT name, service_name, status, retry_count, last_error, creation
FROM `tabRSD Notification Queue`
WHERE status = 'Failed' AND creation > NOW() - INTERVAL 1 DAY
ORDER BY creation DESC;

-- Transaction success rate by service (last 7 days)
SELECT service_name,
       COUNT(*) as total,
       SUM(status = 'Success') as success,
       SUM(status = 'Error') as errors
FROM `tabRSD Transaction Log`
WHERE timestamp > NOW() - INTERVAL 7 DAY
GROUP BY service_name;

-- Drug units by current status
SELECT status, COUNT(*) as count
FROM `tabRSD Drug Unit`
GROUP BY status
ORDER BY count DESC;

-- Orphaned queue entries (no matching transaction log)
SELECT q.name, q.service_name, q.status, q.creation
FROM `tabRSD Notification Queue` q
LEFT JOIN `tabRSD Transaction Log` l
    ON l.service_name = q.service_name
    AND l.timestamp >= q.creation
WHERE q.status = 'Completed'
    AND l.name IS NULL;

-- Products sold today via SFDA
SELECT gtin, serial_number, last_notification_at
FROM `tabRSD Drug Unit`
WHERE status = 'Sold'
    AND DATE(last_notification_at) = CURDATE();
```

---

## 11. Environment Switching

RSD Settings supports two environments:

| Environment | Base URL |
|---|---|
| Test | `https://tandttest.sfda.gov.sa` |
| Production | `https://rsd.sfda.gov.sa` |

**Always test in the Test environment first.** Switch by changing the `Environment` dropdown in RSD Settings. WSDL URLs are constructed automatically:
```
{base}/ws/{ServiceName}/{ServiceName}?wsdl
```

Test credentials and production credentials are different. Update `username` and `password` when switching environments.
