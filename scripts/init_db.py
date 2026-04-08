from finance_tracker.data.db import Base, engine
import finance_tracker.data.models  # noqa: F401


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")