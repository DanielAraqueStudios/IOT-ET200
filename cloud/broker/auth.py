from passlib.context import CryptContext
from sqlalchemy.orm import Session
from models import engine, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def check_device_token(email: str, token: str) -> "dict | None":
    """Used by the MQTT broker to validate client credentials, sent as
    the standard MQTT CONNECT username/password fields.

    `User.deviceToken` stores a bcrypt hash of the token (issued by
    cloud/dashboard/backend's /api/admin/devices), never the plaintext
    value — verified here with passlib, same as a password hash.

    Returns an identity dict ({"email", "can_command"}) on success, or
    None on failure. The identity is what broker.py's per-topic ACL
    checks against (see broker.py MqttBroker._handle / SUBSCRIBE/PUBLISH).
    """
    try:
        with Session(engine) as s:
            u = s.query(User).filter_by(email=email).first()
            stored = u.deviceToken if u else None
            # A disabled device fails the same way as a wrong token: no
            # separate error path that would leak enabled-vs-nonexistent.
            ok = (
                u is not None
                and bool(u.enabled)
                and stored is not None
                and pwd_context.verify(token, stored)
            )
            print(f"[AUTH] email={email!r} found={u is not None} token_match={ok}")
            if not ok:
                return None
            return {"email": email, "can_command": bool(u.canCommand)}
    except Exception as e:
        print(f"[AUTH] DB error: {e}")
        return None
