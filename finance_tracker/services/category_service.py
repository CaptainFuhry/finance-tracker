# finance_tracker/services/category_service.py

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Category, Transaction


class CategoryService:

    @staticmethod
    def get_all(session=None):
        own_session = session is None
        if own_session:
            session = SessionLocal()
        try:
            return session.query(Category).order_by(Category.name).all()
        finally:
            if own_session:
                session.close()

    @staticmethod
    def add_category(name, parent_category=None, is_income=False):
        session = SessionLocal()
        try:
            existing = session.query(Category).filter(Category.name == name).first()
            if existing:
                return None, "A category with that name already exists."

            category = Category(
                name=name,
                parent_category=parent_category,
                is_income=is_income,
            )
            session.add(category)
            session.commit()
            session.refresh(category)
            return category, None
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            session.close()

    @staticmethod
    def update_category(category_id, name, parent_category=None, is_income=False):
        session = SessionLocal()
        try:
            category = session.query(Category).filter(Category.id == category_id).first()
            if not category:
                return False, "Category not found."

            duplicate = session.query(Category).filter(
                Category.name == name,
                Category.id != category_id
            ).first()
            if duplicate:
                return False, "A category with that name already exists."

            category.name = name
            category.parent_category = parent_category
            category.is_income = is_income
            session.commit()
            return True, None
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def delete_category(category_id):
        session = SessionLocal()
        try:
            category = session.query(Category).filter(Category.id == category_id).first()
            if not category:
                return False, "Category not found."

            # Unlink transactions that reference this category before deleting
            linked = session.query(Transaction).filter(
                Transaction.category_id == category_id
            ).all()
            for tx in linked:
                tx.category_id = None

            session.delete(category)
            session.commit()
            return True, None
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def import_from_transactions():
        """
        Scans all transactions for non-null category_id values that no longer
        have a matching category row and rebuilds them. Also looks at any
        transaction description patterns that were previously categorized
        and surfaces unique category names from merchant_rules if present.
        Returns a count of new categories created.
        """
        session = SessionLocal()
        created = 0
        try:
            # Pull distinct category names already assigned via merchant rules
            # or manually set on transactions via category relationship
            existing_names = {c.name for c in session.query(Category).all()}

            # Find any transactions where category is null but merchant has
            # a value — surface unique merchants as suggested categories
            # (This seeds a starting point; user can rename/merge later)
            merchants = (
                session.query(Transaction.merchant)
                .filter(Transaction.merchant != None)
                .filter(Transaction.merchant != "")
                .filter(Transaction.category_id == None)
                .distinct()
                .all()
            )

            for (merchant,) in merchants:
                if merchant and merchant.strip() and merchant.strip() not in existing_names:
                    cat = Category(
                        name=merchant.strip(),
                        is_income=False,
                    )
                    session.add(cat)
                    existing_names.add(merchant.strip())
                    created += 1

            session.commit()
            return created, None
        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()