from passlib.context import CryptContext
import logging
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash(password: str):
    return pwd_context.hash(password)

def verify_inHashedPass_is_savedHasedPass(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# ============================================================================
# LOG SANITIZATION FILTER
# ============================================================================
class TokenSanitizerFilter(logging.Filter):
    """Intercepts Uvicorn access log records and masks sensitive token values."""
    def filter(self, record: logging.LogRecord) -> bool:
        # Sanitize main message
        if isinstance(record.msg, str):
            record.msg = re.sub(r'(token=)[^&\s"\']+', r'\1[REDACTED]', record.msg)
        
        # Handle dict args (Uvicorn standard access log format)
        if isinstance(record.args, dict):
            for k, v in record.args.items():
                if isinstance(v, str):
                    record.args[k] = re.sub(r'(token=)[^&\s"\']+', r'\1[REDACTED]', v)
        # Handle tuple args
        elif isinstance(record.args, tuple):
            record.args = tuple(
                re.sub(r'(token=)[^&\s"\']+', r'\1[REDACTED]', arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True