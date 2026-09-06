"""backend/scripts/make_admin.py::set_role - the promote/demote logic used by
the make_admin CLI (replaces the old "UPDATE users SET role=..." README
instruction). Tests set_role() directly rather than shelling out to the CLI,
same style as the rest of this suite. Runs against your real database - see
README.md "Run the tests"."""
import pytest
from fastapi.testclient import TestClient

from backend.database.session import SessionLocal
from backend.main import app
from backend.scripts.make_admin import set_role
from backend.tests.conftest import cleanup_test_data, register_and_login, unique_email

client = TestClient(app)


def test_promotes_a_student_to_admin():
    db = SessionLocal()
    email = unique_email("makeadmin-promote")
    try:
        register_and_login(client, db, email)  # role="student" (default)
        message = set_role(db, email, "admin")
        assert "'student' -> 'admin'" in message

        db2 = SessionLocal()
        from backend.database.models import User
        user = db2.query(User).filter(User.email == email).first()
        assert user.role == "admin"
        db2.close()
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_demotes_an_admin_back_to_student():
    db = SessionLocal()
    email = unique_email("makeadmin-demote")
    try:
        register_and_login(client, db, email, role="admin")
        message = set_role(db, email, "student")
        assert "'admin' -> 'student'" in message
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_is_a_no_op_when_already_the_target_role():
    db = SessionLocal()
    email = unique_email("makeadmin-noop")
    try:
        register_and_login(client, db, email)  # already "student"
        message = set_role(db, email, "student")
        assert "already" in message
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_raises_for_an_unregistered_email():
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="No user registered"):
            set_role(db, "definitely-not-a-real-user@example.com", "admin")
    finally:
        db.close()
