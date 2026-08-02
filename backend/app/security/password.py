from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# One password policy for the whole application. Registration and the account
# update both import this, so a password that could not be registered can never be
# set later either — the two rules cannot drift apart.
PASSWORD_MIN_LENGTH = 8


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