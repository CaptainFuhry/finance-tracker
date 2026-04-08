from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from finance_tracker.data.db import Base


transaction_tag_links = Table(
    "transaction_tag_links",
    Base.metadata,
    Column("transaction_id", Integer, ForeignKey("transactions.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("transaction_tags.id"), primary_key=True),
)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    account_type = Column(String(50), nullable=False)
    institution = Column(String(100), nullable=True)
    account_last4 = Column(String(10), nullable=True)
    currency = Column(String(10), default="USD")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    transactions = relationship("Transaction", back_populates="account")


class SchemaProfile(Base):
    __tablename__ = "schema_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    institution = Column(String(100), nullable=True)
    account_type = Column(String(50), nullable=True)
    date_column = Column(String(100), nullable=True)
    post_date_column = Column(String(100), nullable=True)
    description_column = Column(String(100), nullable=True)
    amount_column = Column(String(100), nullable=True)
    debit_column = Column(String(100), nullable=True)
    credit_column = Column(String(100), nullable=True)
    balance_column = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    import_batches = relationship("ImportBatch", back_populates="schema_profile")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True)
    source_filename = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=True)
    imported_at = Column(DateTime, server_default=func.now())
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    schema_profile_id = Column(Integer, ForeignKey("schema_profiles.id"), nullable=True)
    row_count = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    notes = Column(Text, nullable=True)

    account = relationship("Account")
    schema_profile = relationship("SchemaProfile", back_populates="import_batches")
    transactions = relationship("Transaction", back_populates="import_batch")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    parent_category = Column(String(100), nullable=True)
    category_type = Column(String(50), nullable=True)
    is_income = Column(Boolean, default=False)
    is_transfer = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    transactions = relationship("Transaction", back_populates="category")
    merchant_rules = relationship("MerchantRule", back_populates="category")


class MerchantRule(Base):
    __tablename__ = "merchant_rules"

    id = Column(Integer, primary_key=True)
    merchant_keyword = Column(String(255), nullable=False)
    merchant_normalized = Column(String(255), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    priority = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    category = relationship("Category", back_populates="merchant_rules")


class TransactionTag(Base):
    __tablename__ = "transaction_tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    transactions = relationship(
        "Transaction",
        secondary=transaction_tag_links,
        back_populates="tags"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True)

    transaction_date = Column(Date, nullable=False)
    post_date = Column(Date, nullable=True)
    description = Column(String(255), nullable=False)
    merchant = Column(String(255), nullable=True)
    amount = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=True)

    transaction_type = Column(String(50), nullable=True)
    direction = Column(String(20), nullable=True)
    source_file = Column(String(255), nullable=True)
    external_id = Column(String(255), nullable=True)

    is_pending = Column(Boolean, default=False)
    is_transfer = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    import_batch = relationship("ImportBatch", back_populates="transactions")
    tags = relationship(
        "TransactionTag",
        secondary=transaction_tag_links,
        back_populates="transactions"
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)
    setting_key = Column(String(100), nullable=False, unique=True)
    setting_value = Column(Text, nullable=True)
    value_type = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())