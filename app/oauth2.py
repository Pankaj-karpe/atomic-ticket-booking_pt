from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import schema, database, models
from .config import settings

# Route endpoint matching app/routers/auth.py for Swagger UI auto-login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

# -------------------------------------------------------------------
# Create the token 
# -------------------------------------------------------------------
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, settings.ALGORITHM)
    return encoded_jwt


# -------------------------------------------------------------------
# NON-RAISING token resolver.
# -------------------------------------------------------------------
def resolve_user_from_token(token: str, db: Session) -> models.User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        return db.query(models.User).filter(models.User.id == int(user_id)).first()
    except (JWTError, ValueError):
        return None


# -------------------------------------------------------------------
# Get current user
# -------------------------------------------------------------------
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)) -> models.User:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"},)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")

        if user_id is None:
            raise credentials_exception

        token_data = schema.TokenData(id=str(user_id))

    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
        
    return user

# ==========================================
# ROLE-BASED ACCESS CONTROL DEPENDENCIES
# ==========================================
class RequireRole:
    """Flexible role-checker dependency class."""
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of the following roles: {self.allowed_roles}"
            )
        return current_user


# Specific role dependencies based on action permissions
get_current_buyer = RequireRole(["buyer", "seller", "admin"])  # Holds, browsing, purchasing
get_current_seller = RequireRole(["seller", "admin"])         # Event/Venue CRUD & manual ticket creation
get_current_admin = RequireRole(["admin"])                    # Admin-only operations
