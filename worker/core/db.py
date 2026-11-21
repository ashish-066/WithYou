"""Point the shared database layer at this worker's DATABASE_URL."""

import alex_db

from core.config import settings

alex_db.configure(settings.effective_database_url or None)
