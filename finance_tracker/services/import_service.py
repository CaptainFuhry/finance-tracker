# finance_tracker/services/import_service.py

import csv
from datetime import datetime
from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Transaction, ImportBatch, Category


def _parse_date(value):
    if not value or not str(value).strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value):
    if not value or not str(value).strip():
        return None
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


# Columns that should be checked for category values
CATEGORY_COL_CANDIDATES = {"category", "type", "transaction type"}


class ImportService:

    @staticmethod
    def read_csv_headers(filepath):
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return list(reader.fieldnames or [])

    @staticmethod
    def preview_rows(filepath, max_rows=5):
        rows = []
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(dict(row))
        return rows

    @staticmethod
    def import_transactions(
        filepath,
        account_id,
        schema_profile_id,
        date_col,
        post_date_col,
        description_col,
        amount_col,       # single signed column (Chase style) — None if using split
        debit_col,        # split debit column (Capital One style) — None if using single
        credit_col,       # split credit column (Capital One style) — None if using single
        ignored_cols,     # set of column names to skip entirely
        account_type="credit",
    ):
        session = SessionLocal()
        try:
            rows_imported = 0
            source_filename = filepath.replace("\\", "/").split("/")[-1]
            cat_cache = {c.name: c.id for c in session.query(Category).all()}
            transactions = []

            with open(filepath, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # ── Date ────────────────────────────────────────────────
                    tx_date = _parse_date(row.get(date_col, ""))
                    if not tx_date:
                        continue

                    post_date = _parse_date(row.get(post_date_col, "")) if post_date_col else None

                    # ── Description ─────────────────────────────────────────
                    description = str(row.get(description_col, "")).strip()
                    if not description:
                        continue

                    # ── Amount ───────────────────────────────────────────────
                    # Mode 1: Single signed column (Chase)
                    #   Amount is already signed — negative = debit, positive = credit
                    #   Do NOT negate — use value as-is
                    #
                    # Mode 2: Split debit/credit (Capital One)
                    #   Debit column = outflow (store as negative)
                    #   Credit column = inflow (store as positive)

                    if amount_col:
                        raw = _parse_amount(row.get(amount_col, ""))
                        amount = raw if raw is not None else 0.0
                        # Amount is already signed — no transformation needed

                    else:
                        debit_val = _parse_amount(row.get(debit_col, "")) if debit_col else None
                        credit_val = _parse_amount(row.get(credit_col, "")) if credit_col else None

                        if debit_val and (credit_val is None or credit_val == 0):
                            amount = -abs(debit_val)   # outflow → negative
                        elif credit_val and (debit_val is None or debit_val == 0):
                            amount = abs(credit_val)   # inflow → positive
                        elif debit_val and credit_val:
                            amount = credit_val - debit_val
                        else:
                            amount = 0.0

                    # ── Category ─────────────────────────────────────────────
                    # Look for a category/type column not in ignored_cols
                    category_id = None
                    for col in row.keys():
                        if col in (ignored_cols or set()):
                            continue
                        if col.lower() in CATEGORY_COL_CANDIDATES:
                            cat_name = str(row.get(col, "")).strip()
                            if cat_name:
                                if cat_name not in cat_cache:
                                    new_cat = Category(name=cat_name, is_income=False)
                                    session.add(new_cat)
                                    session.flush()
                                    cat_cache[cat_name] = new_cat.id
                                category_id = cat_cache[cat_name]
                            break

                    # ── Build transaction ────────────────────────────────────
                    tx = Transaction(
                        account_id=account_id,
                        category_id=category_id,
                        transaction_date=tx_date,
                        post_date=post_date,
                        description=description,
                        merchant=description,
                        amount=amount,
                        transaction_type="debit" if amount < 0 else "credit",
                        source_file=source_filename,
                        is_transfer=False,
                    )
                    transactions.append(tx)

            session.add_all(transactions)
            rows_imported = len(transactions)

            batch = ImportBatch(
                source_filename=source_filename,
                source_type="csv",
                account_id=account_id,
                schema_profile_id=schema_profile_id,
                row_count=rows_imported,
                status="completed",
            )
            session.add(batch)
            session.commit()

            return batch.id, rows_imported, None

        except Exception as e:
            session.rollback()
            return None, 0, str(e)
        finally:
            session.close()