"""Point the shared database layer at this service's DATABASE_URL.

Imported for its side effect by anything that touches the database (routes,
scripts); importing it twice is harmless.
"""

import alex_db

from core.config import settings

alex_db.configure(settings.effective_database_url or None)
