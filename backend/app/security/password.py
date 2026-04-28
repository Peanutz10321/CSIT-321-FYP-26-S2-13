from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Convert plain password into hashed password.
    This hashed password will be stored in the database.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Compare user input password with hashed password from database.
    Returns True if password is correct.
    """
    return pwd_context.verify(plain_password, hashed_password)