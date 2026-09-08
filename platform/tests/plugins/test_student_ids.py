import pytest
import threading

from CTFd.models import UserFieldEntries, UserFields, Users, db
from CTFd.utils.student_ids import DUPLICATE_MESSAGE, StudentIDError
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user
from tests.plugins.test_onboarding import (
    create_google_user,
    onboarding_data,
    start_session,
)


@pytest.fixture
def app():
    app = create_ctfd(enable_plugins=True)
    yield app
    destroy_ctfd(app)


def student_field_id():
    return UserFields.query.filter_by(name="Student ID Number").one().id


def student(name, number):
    user = gen_user(db, name=name, email=f"{name}@examplectf.com")
    user_id = user.id
    terms = UserFields.query.filter_by(name="Terms of Service").one()
    db.session.add_all(
        [
            UserFieldEntries(
                user_id=user_id, field_id=student_field_id(), value=number
            ),
            UserFieldEntries(user_id=user_id, field_id=terms.id, value=True),
        ]
    )
    db.session.commit()
    return user_id


def stored_number(user_id):
    return (
        UserFieldEntries.query.filter_by(user_id=user_id, field_id=student_field_id())
        .one()
        .value
    )


def test_admin_cannot_create_or_change_a_user_to_a_duplicate_number(app):
    with app.app_context():
        student("first", "0012345")
        other_id = student("second", "0012346")
        admin = login_as_user(app, name="admin")
        data = {"fields": [{"field_id": student_field_id(), "value": " 0012345 "}]}
        response = admin.patch(f"/api/v1/users/{other_id}", json=data)
        assert response.status_code == 400
        assert DUPLICATE_MESSAGE in response.json["errors"]["fields"]
        assert stored_number(other_id) == "0012346"

        response = admin.post(
            "/api/v1/users",
            json={
                "name": "third",
                "email": "third@examplectf.com",
                "password": "password123",
                **data,
            },
        )
        assert response.status_code == 400
        assert DUPLICATE_MESSAGE in response.json["errors"]["fields"]
        assert Users.query.filter_by(name="third").count() == 0


def test_self_update_allows_own_number_and_rolls_back_duplicate_changes(app):
    with app.app_context():
        student("first", "0012345")
        user_id = student("second", "0012346")
        client = login_as_user(app, name="second")
        data = {"fields": [{"field_id": student_field_id(), "value": "0012346"}]}
        assert client.patch("/api/v1/users/me", json=data).status_code == 200
        data["fields"][0]["value"] = "0012345"
        data["name"] = "changed"
        response = client.patch("/api/v1/users/me", json=data)
        assert response.status_code == 400
        assert DUPLICATE_MESSAGE in response.json["errors"]["fields"]
        assert stored_number(user_id) == "0012346"
        assert db.session.get(Users, user_id).name == "second"


def test_onboarding_shows_duplicate_error_without_saving_credentials(app):
    with app.app_context():
        student("first", "2025000001")
        user_id = create_google_user(app)
        client = start_session(app, user_id)
        data = onboarding_data(client)
        data[f"fields[{student_field_id()}]"] = "2025000001"
        response = client.post("/onboarding/", data=data)
        assert response.status_code == 200
        assert DUPLICATE_MESSAGE in response.get_data(as_text=True)
        assert db.session.get(Users, user_id).password is None
        assert client.get("/challenges").location.endswith("/onboarding/")


def test_registration_does_not_leave_an_account_after_duplicate_failure(app):
    with app.app_context():
        student("first", "0012345")
        client = app.test_client()
        client.get("/register")
        with client.session_transaction() as session:
            nonce = session["nonce"]
        fields = {f"fields[{field.id}]": "y" for field in UserFields.query.all()}
        fields[f"fields[{student_field_id()}]"] = "0012345"
        response = client.post(
            "/register",
            data={
                "nonce": nonce,
                "name": "newstudent",
                "email": "new@examplectf.com",
                "password": "password123",
                **fields,
            },
        )
        assert response.status_code == 200
        assert DUPLICATE_MESSAGE in response.get_data(as_text=True)
        assert Users.query.filter_by(email="new@examplectf.com").count() == 0


def test_new_numbers_are_trimmed_and_keep_leading_zeroes(app):
    with app.app_context():
        user_id = student("first", " 0012345 ")
        assert stored_number(user_id) == "0012345"
        # A leading zero is part of the identifier.
        other_id = student("second", "12345")
        assert stored_number(other_id) == "12345"


def test_duplicate_numbers_in_one_transaction_are_rejected(app):
    with app.app_context():
        users = [
            gen_user(db, name=name, email=f"{name}@examplectf.com")
            for name in ("first", "second")
        ]
        field_id = student_field_id()
        db.session.add_all(
            [
                UserFieldEntries(user_id=user.id, field_id=field_id, value="0012345")
                for user in users
            ]
        )
        with pytest.raises(StudentIDError, match="이미 다른 계정"):
            db.session.commit()
        db.session.rollback()
        assert UserFieldEntries.query.filter_by(field_id=field_id).count() == 0


def test_concurrent_mysql_writes_cannot_claim_the_same_number(app):
    with app.app_context():
        if db.engine.dialect.name != "mysql":
            pytest.skip("Requires MySQL row locking")
        users = [
            gen_user(db, name=name, email=f"{name}@examplectf.com").id
            for name in ("first", "second")
        ]
        field_id = student_field_id()
    snapshot_ready = threading.Event()
    first_flushed = threading.Event()
    release_first = threading.Event()
    second_attempting = threading.Event()
    second_done = threading.Event()
    results = []

    def first():
        with app.app_context():
            try:
                assert snapshot_ready.wait(10)
                db.session.add(
                    UserFieldEntries(
                        user_id=users[0], field_id=field_id, value="0012345"
                    )
                )
                db.session.flush()
                first_flushed.set()
                assert release_first.wait(10)
                db.session.commit()
                results.append("saved")
            except Exception as error:
                results.append(type(error).__name__)
                db.session.rollback()

    def second():
        with app.app_context():
            try:
                # Establish a repeatable-read snapshot before the first commit.
                assert UserFieldEntries.query.filter_by(field_id=field_id).count() == 0
                snapshot_ready.set()
                assert first_flushed.wait(10)
                db.session.add(
                    UserFieldEntries(
                        user_id=users[1], field_id=field_id, value="0012345"
                    )
                )
                second_attempting.set()
                db.session.commit()
                results.append("saved")
            except StudentIDError:
                db.session.rollback()
                results.append("duplicate")
            except Exception as error:
                db.session.rollback()
                results.append(type(error).__name__)
            finally:
                second_done.set()

    workers = [threading.Thread(target=first), threading.Thread(target=second)]
    for worker in workers:
        worker.start()
    try:
        assert second_attempting.wait(10)
        assert not second_done.wait(0.2)
    finally:
        release_first.set()
        for worker in workers:
            worker.join(timeout=15)
    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == ["duplicate", "saved"]
    with app.app_context():
        assert UserFieldEntries.query.filter_by(field_id=field_id).count() == 1
