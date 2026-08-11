from sqlalchemy.orm import Session

from shuttlecube.application.idempotency import find_idempotent, save_idempotent


def test_idempotency_round_trip(db: Session) -> None:
    save_idempotent(db, "test", "key", {"id": "one"})
    db.commit()
    assert find_idempotent(db, "test", "key") == {"id": "one"}
