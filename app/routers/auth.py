from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from .. import schema, models, oauth2, utils
from ..database import get_db

router = APIRouter(
    tags=["Authentication"]
)

# -------------------------------------------------------------------
# Create a user
# -------------------------------------------------------------------
@router.post("/signup", response_model=schema.UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user: schema.UserCreate, db: Session = Depends(get_db)):

    # Check if email already exists
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Hash password and store
    hasded_password = utils.hash(user.password)
    new_user = models.User(
        email = user.email,
        hashed_pwd = hasded_password,
        role = user.role or "buyer"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# -------------------------------------------------------------------
# login - generate new jwt token
# -------------------------------------------------------------------
@router.post("/login")
def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_credentials.username).first()

    if not user or not utils.verify_inHashedPass_is_savedHasedPass(user_credentials.password, user.hashed_pwd):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail = "Invalid Credentials")

    # Generate JWT token
    access_token = oauth2.create_access_token(data={"user_id": user.id, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}