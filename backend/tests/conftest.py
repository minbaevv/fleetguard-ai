import os

# Настройки должны быть заданы до импорта app.core.config, иначе конфиг закэшируется.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
