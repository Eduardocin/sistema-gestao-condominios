import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import session as session_module


def test_failed_service_rolls_back_pending_changes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'transactions.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE operations (id INTEGER PRIMARY KEY)"))
    monkeypatch.setattr(session_module, "get_session_factory", lambda: sessionmaker(bind=engine))
    dependency = session_module.get_session()
    session = next(dependency)
    session.execute(text("INSERT INTO operations (id) VALUES (1)"))
    with pytest.raises(ValueError, match="service failed"):
        dependency.throw(ValueError("service failed"))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM operations")) == 0
    engine.dispose()
