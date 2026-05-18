import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def test_engine():
    from shared.models import Base
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(test_engine):
    Session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()
