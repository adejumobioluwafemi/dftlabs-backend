# app/models/__init__.py
# Importing all models here ensures SQLModel registers all tables
# before create_db_and_tables() runs at startup.
from app.models.blog import BlogPost  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.registration import Registration  # noqa: F401
from app.models.product import Product  # noqa: F401