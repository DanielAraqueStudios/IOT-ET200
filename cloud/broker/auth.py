from sqlalchemy.orm import Session
from models import engine, User


def check_device_token(email: str, token: str) -> bool:
    """Used by the MQTT broker to validate client credentials, sent as
    the standard MQTT CONNECT username/password fields."""
    try:
        with Session(engine) as s:
            u = s.query(User).filter_by(email=email).first()
            stored = u.deviceToken if u else None
            ok = u is not None and stored == token
            print(f"[AUTH] email={email!r} found={u is not None} token_match={ok}")
            return ok
    except Exception as e:
        print(f"[AUTH] DB error: {e}")
        return False
