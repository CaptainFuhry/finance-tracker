# finance_tracker/services/schema_profile_service.py

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import SchemaProfile


class SchemaProfileService:

    @staticmethod
    def get_all():
        session = SessionLocal()
        try:
            return (
                session.query(SchemaProfile)
                .filter(SchemaProfile.is_active == True)
                .order_by(SchemaProfile.name)
                .all()
            )
        finally:
            session.close()

    @staticmethod
    def get_by_id(profile_id):
        session = SessionLocal()
        try:
            return session.query(SchemaProfile).filter(SchemaProfile.id == profile_id).first()
        finally:
            session.close()

    @staticmethod
    def get_last_used_for_account(account_id):
        """
        Looks up app_settings for the last schema profile used with this account.
        Returns a SchemaProfile or None.
        """
        from finance_tracker.data.models import AppSetting
        session = SessionLocal()
        try:
            key = f"last_schema_profile_account_{account_id}"
            setting = session.query(AppSetting).filter(AppSetting.setting_key == key).first()
            if setting and setting.setting_value:
                profile_id = int(setting.setting_value)
                return session.query(SchemaProfile).filter(SchemaProfile.id == profile_id).first()
            return None
        finally:
            session.close()

    @staticmethod
    def save_last_used_for_account(account_id, profile_id):
        from finance_tracker.data.models import AppSetting
        from datetime import datetime
        session = SessionLocal()
        try:
            key = f"last_schema_profile_account_{account_id}"
            setting = session.query(AppSetting).filter(AppSetting.setting_key == key).first()
            if setting:
                setting.setting_value = str(profile_id)
                setting.updated_at = datetime.now()
            else:
                setting = AppSetting(
                    setting_key=key,
                    setting_value=str(profile_id),
                    value_type="int",
                    description=f"Last schema profile used for account {account_id}",
                )
                session.add(setting)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def create_or_update(
        name,
        institution,
        account_type,
        date_column,
        post_date_column,
        description_column,
        amount_column,
        debit_column,
        credit_column,
        balance_column,
        notes,
        category_column=None,   # NEW
    ):
        session = SessionLocal()
        try:
            existing = session.query(SchemaProfile).filter(SchemaProfile.name == name).first()
            if existing:
                existing.institution        = institution
                existing.account_type       = account_type
                existing.date_column        = date_column
                existing.post_date_column   = post_date_column
                existing.description_column = description_column
                existing.amount_column      = amount_column
                existing.debit_column       = debit_column
                existing.credit_column      = credit_column
                existing.balance_column     = balance_column
                existing.notes              = notes
                existing.category_column    = category_column   # NEW
                existing.is_active          = True
                session.commit()
                return existing.id, None
            else:
                profile = SchemaProfile(
                    name=name,
                    institution=institution,
                    account_type=account_type,
                    date_column=date_column,
                    post_date_column=post_date_column,
                    description_column=description_column,
                    amount_column=amount_column,
                    debit_column=debit_column,
                    credit_column=credit_column,
                    balance_column=balance_column,
                    notes=notes,
                    category_column=category_column,            # NEW
                    is_active=True,
                )
                session.add(profile)
                session.commit()
                return profile.id, None
        except Exception as e:
            session.rollback()
            return None, str(e)
        finally:
            session.close()