from io import BytesIO
import zipfile

import pytest
from flask import request
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.test import EnvironBuilder

from CTFd.utils.security.forms import BoundedFormDataParser
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user


@pytest.fixture
def app():
    app = create_ctfd()
    app.config.update(
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        MAX_UPLOAD_CONTENT_LENGTH=4 * 1024 * 1024,
        MAX_IMPORT_CONTENT_LENGTH=8 * 1024 * 1024,
    )

    def inspect_upload(**kwargs):
        upload = next(iter(request.files.values()))
        # fileno exists because the body is disk-backed, not retained in RAM.
        assert upload.stream.fileno() >= 0
        upload.stream.seek(0, 2)
        return {"size": upload.stream.tell()}

    for endpoint in ("api.files_files_list", "admin.import_ctf", "admin.import_csv"):
        app.view_functions[endpoint] = inspect_upload
    try:
        yield app
    finally:
        destroy_ctfd(app)


def upload(client, path, size):
    with client.session_transaction() as session:
        nonce = session.get("nonce", "")
    return client.post(path, data={
        "nonce": nonce, "file": (BytesIO(b"x" * size), "test.bin"),
    })


@pytest.mark.parametrize("path,size,expected", [
    ("/api/v1/files", 3 * 1024 * 1024, 200),
    ("/api/v1/files", 5 * 1024 * 1024, 413),
    ("/admin/import", 5 * 1024 * 1024, 200),
    ("/admin/import", 9 * 1024 * 1024, 413),
    ("/admin/import/csv", 3 * 1024 * 1024, 413),
    ("/login", 3 * 1024 * 1024, 413),
])
def test_authenticated_upload_budget_is_endpoint_specific(app, path, size, expected):
    client = login_as_user(app, name="admin")
    response = upload(client, path, size)
    assert response.status_code == expected
    if expected == 200:
        assert response.get_json()["size"] == size


@pytest.mark.parametrize("path", ["/api/v1/files", "/admin/import", "/admin/import/csv"])
@pytest.mark.parametrize("role", ["anonymous", "student"])
def test_non_admin_rejected_before_multipart_parser_runs(app, monkeypatch, path, role):
    if role == "student":
        with app.app_context():
            gen_user(app.db, name="student", email="student@examplectf.com")
        client = login_as_user(app, name="student")
    else:
        client = app.test_client()

    def forbidden_parse(*args, **kwargs):
        pytest.fail("unauthorized upload body was parsed")

    monkeypatch.setattr(BoundedFormDataParser, "parse", forbidden_parse)
    assert upload(client, path, 3 * 1024 * 1024).status_code == 403


@pytest.mark.parametrize("data", [
    {"field": "x" * (600 * 1024)},
    {"first": "x" * (300 * 1024), "second": "x" * (300 * 1024)},
    {f"field{i}": "x" for i in range(101)},
])
def test_form_memory_budget_cannot_be_bypassed_by_chunks_or_fields(data):
    builder = EnvironBuilder(method="POST", data=data, content_type="multipart/form-data")
    try:
        parser = BoundedFormDataParser(
            max_form_memory_size=512 * 1024, max_form_parts=100,
        )
        with pytest.raises(RequestEntityTooLarge):
            parser.parse_from_environ(builder.get_environ())
    finally:
        builder.close()


def test_parser_closes_temporary_files_on_field_limit_error():
    opened = []

    def factory(**kwargs):
        stream = BytesIO()
        opened.append(stream)
        return stream

    boundary = b"test-boundary"
    body = (
        b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="x"\r\n\r\nfile\r\n'
        b'--test-boundary\r\nContent-Disposition: form-data; name="field"\r\n\r\n'
        + b"x" * (600 * 1024) + b"\r\n--test-boundary--\r\n"
    )
    parser = BoundedFormDataParser(stream_factory=factory, max_form_memory_size=512 * 1024)
    with pytest.raises(RequestEntityTooLarge):
        parser.parse(BytesIO(body), "multipart/form-data", len(body), {"boundary": boundary.decode()})
    assert opened and all(stream.closed for stream in opened)


def test_archive_expansion_has_a_separate_aggregate_budget(app, monkeypatch):
    from CTFd.utils.exports import import_ctf

    backup = BytesIO()
    with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("db/users.json", b"x" * 60)
        archive.writestr("db/teams.json", b"x" * 60)
    backup.seek(0)
    # Stop at archive validation; no live database or import is involved.
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "mysql://unused")
    app.config.update(MAX_IMPORT_CONTENT_LENGTH=64, MAX_IMPORT_EXTRACTED_LENGTH=100)
    with app.app_context(), pytest.raises(zipfile.LargeZipFile):
        import_ctf(backup)
