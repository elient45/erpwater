# Water ERP ForeignKey Relationships & Data Dependencies

## Summary
This document maps all ForeignKey, OneToOneField, and soft link relationships across the Water ERP system, including cascade behaviors and potential data integrity issues.

---

## 1. ACCOUNTS APP

### UserProfile
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `user` | `AUTH_USER_MODEL` | CASCADE | Django Auth | OneToOneField - creates 1:1 relationship with User |

### AuditLog (Generic Audit Trail)
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `content_type` | `ContentType` | CASCADE | Django CT | Works with GenericForeignKey |
| `changed_by` | `AUTH_USER_MODEL` | SET_NULL | Django Auth | User who made the change; allows null if user deleted |
| `content_object` | GenericForeignKey (no cascade) | - | All Apps | Points to any model instance across the entire system |

**Issues:**
- ✅ GenericForeignKey allows tracking changes on any model
- ⚠️ If content_type is deleted, audit logs orphaned (CASCADE)
- ✅ SET_NULL on changed_by preserves logs even if user deleted

---

## 2. EXPENSES APP

### ExpenseCategory
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No relationships; standalone lookup table |

### Expense
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `category` | `ExpenseCategory` | PROTECT | No | Prevents deletion of category if expenses exist |
| `account` | `sales.FinancialAccount` | PROTECT | **YES - SALES** | **CROSS-APP DEPENDENCY** |
| `created_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion if they created expenses |

**Issues:**
- ⚠️ **CROSS-APP COUPLING**: Expense references sales.FinancialAccount directly
- ⚠️ Deleting FinancialAccount blocked by PROTECT (good for data integrity)
- ⚠️ Deleting ExpenseCategory or creator user is blocked
- ✅ Prevents orphaned expense records

### FinancialTransaction (Denormalized Transaction Log)
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `created_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion |
| `account_id_value` | **SOFT LINK** (BigIntegerField) | - | SALES | Stores account ID as value, not FK |
| `expense_id_value` | **SOFT LINK** (BigIntegerField) | - | - | References Expense by ID only |
| `payment_id` | **SOFT LINK** (BigIntegerField) | - | SALES | References Payment by ID only |
| `counter_account_id_value` | **SOFT LINK** (BigIntegerField) | - | SALES | For transferring between accounts |

**Issues:**
- ⚠️ **DANGLING REFERENCES**: Three soft links without ForeignKey constraints
- ⚠️ `account_id_value` can reference deleted accounts (no integrity check)
- ⚠️ `expense_id_value` can reference deleted expenses (no integrity check)
- ⚠️ `payment_id` can reference deleted payments (no integrity check)
- 🔴 **DATA INTEGRITY RISK**: These soft links can become orphaned without warning
- ⚠️ Reconciliation needed: actual amounts vs. stored amounts
- ✅ Has validation in `clean()` method to check consistency

---

## 3. INVENTORY APP

### Product
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No ForeignKey relationships; referenced by other models |

### Depot
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No ForeignKey relationships; referenced by stock movements |

### StockMovement
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `depot_from` | `Depot` | PROTECT | No | Prevents depot deletion while movements exist |
| `depot_to` | `Depot` | PROTECT | No | Prevents depot deletion while movements exist |
| `created_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion |

**Issues:**
- ✅ PROTECT prevents integrity issues
- ⚠️ Cannot delete depots if they have movements (may block deactivation)
- ⚠️ `ref_type` and `ref_id` form soft link (can reference any type of reference)
- ✅ Has validation in `clean()` ensuring depot_from/to consistency

### StockMovementItem
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `movement` | `StockMovement` | CASCADE | No | Deleting movement cascade-deletes all items |
| `product` | `Product` | PROTECT | No | Protects product deletion while used in movements |

**Issues:**
- ✅ CASCADE on movement is correct (items belong to movement)
- ✅ PROTECT on product prevents deletion while in movements
- ✅ Good relationship design

### StockBalance (Denormalized Current Stock)
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `depot` | `Depot` | PROTECT | No | Prevents depot deletion |
| `product` | `Product` | PROTECT | No | Prevents product deletion |

**Issues:**
- ✅ Unique constraint on (depot, product) prevents duplicates
- ⚠️ If Depot or Product is somehow deleted, balance is orphaned (PROTECT prevents this)
- 🔴 **CRITICAL**: StockBalance can become out-of-sync with actual movements
- ⚠️ No automatic synchronization mechanism visible

### ProductionOrder
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `created_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion |
| `validated_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion if they validated |
| `product_id_value` | **SOFT LINK** (BigIntegerField) | - | - | Stores product ID as value, not FK |
| `depot_id_value` | **SOFT LINK** (BigIntegerField) | - | - | Stores depot ID as value, not FK |
| `stock_movement_id_value` | **SOFT LINK** (BigIntegerField) | - | - | References StockMovement by ID only |

**Issues:**
- 🔴 **DANGLING REFERENCES**: Three soft links without FK constraints
- ⚠️ `product_id_value` can reference deleted products
- ⚠️ `depot_id_value` can reference deleted depots
- ⚠️ `stock_movement_id_value` can reference deleted movements
- 🔴 **DATA INTEGRITY RISK**: Can cause orphaned production records
- ⚠️ Quantities (planned, actual, loss, net) can become inconsistent

### Supplier
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No ForeignKey relationships; referenced by purchases |

### Purchase
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `supplier` | `inventory.Supplier` | PROTECT | No | Prevents supplier deletion while purchases exist |
| `created_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion |
| `validated_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion if they validated |
| `depot_id_value` | **SOFT LINK** (BigIntegerField) | - | - | Stores depot ID as value, not FK |
| `stock_movement_id_value` | **SOFT LINK** (BigIntegerField) | - | - | References StockMovement by ID only |
| `expense_id_value` | **SOFT LINK** (BigIntegerField) | - | EXPENSES | References Expense by ID only |

**Issues:**
- 🔴 **DANGLING REFERENCES**: Three soft links without FK constraints
- ⚠️ `depot_id_value` can reference deleted depots
- ⚠️ `stock_movement_id_value` can reference deleted movements
- ⚠️ `expense_id_value` can reference deleted expenses
- 🔴 **FLAG MISMATCH RISK**: `expense_registered` boolean could be out-of-sync with actual expense records
- ⚠️ Cannot cascade delete `stock_movement_id_value` due to soft link
- ✅ Has validation in `clean()` preventing cancelation if expense registered

### SupplyItem
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No ForeignKey relationships; referenced by purchase items & production usage |

### PurchaseItem
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `purchase` | `inventory.Purchase` | CASCADE | No | Deleting purchase cascade-deletes items |
| `supply_item_id_value` | **SOFT LINK** (BigIntegerField) | - | - | Stores supply item ID as value, not FK |

**Issues:**
- ✅ CASCADE on purchase is correct (items belong to purchase)
- ⚠️ **DANGLING REFERENCE**: `supply_item_id_value` can reference deleted supply items
- ⚠️ No integrity check on supply item availability

### ProductionSupplyUsage
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `production` | `inventory.ProductionOrder` | CASCADE | No | Deleting production cascade-deletes usage records |
| `supply_item_id_value` | **SOFT LINK** (BigIntegerField) | - | - | Stores supply item ID as value, not FK |

**Issues:**
- ✅ CASCADE on production is correct (usage records belong to production)
- ⚠️ **DANGLING REFERENCE**: `supply_item_id_value` can reference deleted supply items
- ⚠️ `unit_cost_snapshot` can become outdated

---

## 4. SALES APP

### Client
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No ForeignKey relationships; referenced by invoices |

### Invoice
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `customer` | `Client` | PROTECT | No | Prevents client deletion while invoices exist |
| `created_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion |
| `validated_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion if they validated |

**Issues:**
- ✅ PROTECT prevents integrity issues
- ⚠️ Cannot delete clients if they have invoices (may block deactivation)
- 🔴 **RECONCILIATION RISK**: `paid_amount` must stay in sync with Payment records' sum
- ⚠️ Status workflow (DRAFT → VALIDATED → PARTIAL → PAID) must be enforced
- ✅ Has validation in `clean()` preventing reversion to DRAFT

### InvoiceItem
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `invoice` | `Invoice` | CASCADE | No | Deleting invoice cascade-deletes items |
| `product` | `inventory.Product` | PROTECT | **YES - INVENTORY** | **CROSS-APP DEPENDENCY** |

**Issues:**
- ✅ CASCADE on invoice is correct (items belong to invoice)
- ⚠️ **CROSS-APP COUPLING**: References inventory.Product directly
- ⚠️ Deleting product blocked by PROTECT (prevents data loss)
- ⚠️ Cannot delete products if they're on any invoice
- ✅ Good relationship design for integrity

### FinancialAccount
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| - | - | - | - | No ForeignKey relationships; referenced by payments & expenses |

### Payment
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `invoice` | `Invoice` | PROTECT | No | Prevents invoice deletion while payments exist |
| `account` | `FinancialAccount` | PROTECT | No | Prevents account deletion while payments exist |
| `received_by` | `AUTH_USER_MODEL` | PROTECT | Django Auth | Prevents user deletion if they received payment |

**Issues:**
- ✅ PROTECT is appropriate (payment references important records)
- 🔴 **RECONCILIATION RISK**: Sum of payments must equal invoice.paid_amount
- ⚠️ Partial payments allowed but invoice.status must stay synchronized
- ✅ Has validation in `clean()` preventing overpayment

### InvoiceStockLink (Bridge between Sales & Inventory)
| Field | Foreign Key | Cascade | Cross-App | Notes |
|-------|-------------|---------|-----------|-------|
| `invoice` | `Invoice` | CASCADE | No | OneToOneField - invoice linked to max 1 stock movement |
| `stock_movement` | `inventory.StockMovement` | PROTECT | **YES - INVENTORY** | **CROSS-APP DEPENDENCY** |

**Issues:**
- ✅ CASCADE on invoice is correct (link belongs to invoice)
- ⚠️ **CRITICAL CROSS-APP**: Tightly couples Sales to Inventory
- ⚠️ Deleting stock movement blocked by PROTECT (may prevent inventory corrections)
- ⚠️ OneToOneField ensures 1:1 mapping enforced
- ⚠️ Invoice status and stock movement status must stay synchronized

---

## 5. CROSS-APP DEPENDENCIES SUMMARY

### Outgoing Dependencies (External References)

| From App | From Model | Field | To App | To Model | Constraint | Risk Level |
|----------|-----------|--------|---------|----------|-----------|-----------|
| expenses | Expense | account | **sales** | FinancialAccount | PROTECT | 🟡 Medium |
| expenses | FinancialTransaction | account_id_value | **sales** | FinancialAccount | SOFT LINK | 🔴 High |
| expenses | FinancialTransaction | payment_id | **sales** | Payment | SOFT LINK | 🔴 High |
| inventory | InvoiceItem | product | **inventory** | Product | PROTECT | 🟡 Medium |
| sales | InvoiceStockLink | stock_movement | **inventory** | StockMovement | PROTECT | 🟡 Medium |

### Central Dependency Hub: AUTH_USER_MODEL
- **Accounts**: UserProfile.user (CASCADE), AuditLog.changed_by (SET_NULL)
- **Expenses**: Expense.created_by, FinancialTransaction.created_by (both PROTECT)
- **Inventory**: StockMovement.created_by, ProductionOrder created_by/validated_by, Purchase created_by/validated_by (all PROTECT)
- **Sales**: Invoice created_by/validated_by, Payment.received_by (all PROTECT)

**Risk**: Deleting user is blocked by multiple PROTECT constraints (good for data integrity)

---

## 6. DATA INTEGRITY ISSUES & DANGLING REFERENCES

### 🔴 HIGH RISK - Soft Links Without Constraints

| App | Model | Field | References | Impact | Recommended Fix |
|-----|-------|-------|-----------|--------|-----------------|
| expenses | FinancialTransaction | account_id_value | FinancialAccount | Can reference deleted account | Add ForeignKey constraint |
| expenses | FinancialTransaction | expense_id_value | Expense | Can reference deleted expense | Add ForeignKey constraint |
| expenses | FinancialTransaction | payment_id | Payment | Can reference deleted payment | Add ForeignKey constraint |
| inventory | ProductionOrder | product_id_value | Product | Can reference deleted product | Add ForeignKey constraint |
| inventory | ProductionOrder | depot_id_value | Depot | Can reference deleted depot | Add ForeignKey constraint |
| inventory | ProductionOrder | stock_movement_id_value | StockMovement | Can reference deleted movement | Add ForeignKey constraint |
| inventory | Purchase | depot_id_value | Depot | Can reference deleted depot | Add ForeignKey constraint |
| inventory | Purchase | stock_movement_id_value | StockMovement | Can reference deleted movement | Add ForeignKey constraint |
| inventory | Purchase | expense_id_value | Expense | Can reference deleted expense | Add ForeignKey constraint |
| inventory | PurchaseItem | supply_item_id_value | SupplyItem | Can reference deleted item | Add ForeignKey constraint |
| inventory | ProductionSupplyUsage | supply_item_id_value | SupplyItem | Can reference deleted item | Add ForeignKey constraint |

---

## 7. RECONCILIATION FIELDS NEEDING SYNCHRONIZATION

### Balance Fields (Can become out-of-sync)

| App | Model | Field | Dependency | Sync Method | Risk |
|-----|-------|-------|-----------|-----------|------|
| sales | Invoice | paid_amount | Payment.amount (sum) | Manual updates | 🔴 Manual sync required |
| sales | Invoice | balance_due | computed property | Formula: total - paid_amount | 🟡 Depends on paid_amount accuracy |
| inventory | StockBalance | qty_packs | StockMovementItem movements | Manual updates | 🔴 Manual sync required |
| expenses | FinancialTransaction | amount | Source transaction | Stored separately | 🔴 No automatic sync |
| inventory | Purchase | expense_registered | Expense records | Boolean flag | 🔴 Flag can mismatch reality |

### Issues:
- `Invoice.paid_amount` must be updated when Payment records change
- `StockBalance.qty_packs` can drift from actual movements if updates are missed
- `Purchase.expense_registered` flag could be true but actual Expense missing
- `FinancialTransaction` denormalizes data without automatic sync

---

## 8. MISSING CONSTRAINTS & RECOMMENDATIONS

### Add ForeignKey Constraints (Replace Soft Links)

```python
# In expenses/models.py - FinancialTransaction
account = models.ForeignKey(
    'sales.FinancialAccount',
    on_delete=models.PROTECT,
    db_column='account_id',
    db_constraint=True,
)
expense = models.ForeignKey(
    'Expense',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    db_column='expense_id',
)
payment = models.ForeignKey(
    'sales.Payment',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    db_column='payment_id',
)
counter_account = models.ForeignKey(
    'sales.FinancialAccount',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name='counter_account_transactions',
)

# In inventory/models.py - ProductionOrder
product = models.ForeignKey(
    Product,
    on_delete=models.PROTECT,
    db_column='product_id',
)
depot = models.ForeignKey(
    Depot,
    on_delete=models.PROTECT,
    db_column='depot_id',
)
stock_movement = models.ForeignKey(
    StockMovement,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
)

# In inventory/models.py - Purchase
depot = models.ForeignKey(
    Depot,
    on_delete=models.PROTECT,
    db_column='depot_id',
)
stock_movement = models.ForeignKey(
    StockMovement,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
)
expense = models.ForeignKey(
    'expenses.Expense',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
)

# In inventory/models.py - PurchaseItem
supply_item = models.ForeignKey(
    SupplyItem,
    on_delete=models.PROTECT,
    db_column='supply_item_id',
)

# In inventory/models.py - ProductionSupplyUsage
supply_item = models.ForeignKey(
    SupplyItem,
    on_delete=models.PROTECT,
    db_column='supply_item_id',
)
```

### Add Cascade Rules for Dependent Objects

| Parent Model | Child Model | Current | Recommended | Reason |
|---------------------------|------------------|---------|-------------|-------|
| Invoice | InvoiceItem | CASCADE | ✅ Correct | Items belong to invoice |
| Invoice | Payment | PROTECT | Consider CASCADE | Orphaned payments if invoice deleted |
| StockMovement | StockMovementItem | CASCADE | ✅ Correct | Items belong to movement |
| Purchase | PurchaseItem | CASCADE | ✅ Correct | Items belong to purchase |
| ProductionOrder | SupplyUsage | CASCADE | ✅ Correct | Usage records belong to production |

### Deactivation vs. Deletion Strategy

**Current Issue**: Many PROTECT constraints prevent deletion, making it hard to deactivate obsolete records.

**Recommendation**: Add `is_active` / `is_deleted` flags to prevent CASCADE deletions while allowing logical soft deletes:
- Product (add is_active if not present)
- Depot (add is_active if not present)
- Supplier (has is_active ✅)
- Client (add is_active if not present)
- FinancialAccount (add is_active if not present)

---

## 9. CASCADE BEHAVIOR MATRIX

```
CASCADE (child deleted when parent deleted):
  - StockMovementItem → StockMovement
  - InvoiceItem → Invoice
  - PurchaseItem → Purchase
  - ProductionSupplyUsage → ProductionOrder
  - InvoiceStockLink → Invoice (OneToOne)

PROTECT (parent cannot be deleted if children exist):
  - ALL others (Depot, Product, Client, ExpenseCategory, USER, etc.)

SET_NULL (record orphaned if parent deleted, FK becomes null):
  - AuditLog.changed_by → USER (preserves audit trail)
  - (Recommended) Production/Purchase → StockMovement
  - (Recommended) Purchase → Expense
```

---

## 10. ACTION ITEMS FOR DATA INTEGRITY

- [ ] Validate all soft links haven't created orphaned records
- [ ] Convert 9 soft link fields to proper ForeignKey constraints
- [ ] Add synchronization logic for balance fields (Invoice.paid_amount, StockBalance.qty_packs)
- [ ] Implement `is_active` flags instead of relying on PROTECT
- [ ] Add database constraints to prevent setting `expense_registered` without actual Expense
- [ ] Review cascade deletion permissions (some PROTECT may need SET_NULL)
- [ ] Add unique constraints where needed (Invoice.number already unique ✅)
- [ ] Create data integrity audit checks (dangling references, balance mismatches)
