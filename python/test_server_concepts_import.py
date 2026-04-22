"""Tests for POST /api/concepts/import endpoint (merge vs replace)."""
import csv
import email
import email.parser
import email.policy
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def flush(self) -> None:
        pass

    def payload(self) -> dict:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict) -> None:
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self._headers = headers
        self.status: int | None = None

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        pass

    def end_headers(self):
        pass


def _make_multipart(csv_body: str, mode: str = "") -> tuple[bytes, str]:
    boundary = "----parseboundary"
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="csv"; filename="concepts.csv"\r\n',
        b"Content-Type: text/csv\r\n\r\n",
        csv_body.encode("utf-8"),
        b"\r\n",
    ]
    if mode:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="mode"\r\n\r\n',
            mode.encode(),
            b"\r\n",
        ]
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    return body, boundary


def _invoke(tmp_path, monkeypatch, existing_rows, upload_csv, mode=""):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    concepts_path = tmp_path / "concepts.csv"
    if existing_rows is not None:
        with open(concepts_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "concept_en", "survey_item", "custom_order"])
            w.writeheader()
            for row in existing_rows:
                w.writerow({k: row.get(k, "") for k in w.fieldnames})

    body, boundary = _make_multipart(upload_csv, mode=mode)
    # cgi.FieldStorage expects an email.message.Message-like headers object
    hdr_text = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    headers = email.parser.Parser(policy=email.policy.compat32).parsestr(hdr_text)
    req = _FakeRequest(body, headers)

    class H(server.RangeRequestHandler):
        def __init__(self):
            self.rfile = req.rfile
            self.wfile = req.wfile
            self.headers = headers

        def send_response(self, code):
            req.status = code

        def send_header(self, *a, **kw):
            pass

        def end_headers(self):
            pass

    handler = H()
    handler._api_post_concepts_import()

    result = req.wfile.payload()

    with open(concepts_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return result, rows


def test_import_merges_survey_and_custom_order(tmp_path, monkeypatch):
    existing = [
        {"id": "1", "concept_en": "hair", "survey_item": "", "custom_order": ""},
        {"id": "2", "concept_en": "forehead", "survey_item": "", "custom_order": ""},
        {"id": "3", "concept_en": "eyelid", "survey_item": "", "custom_order": ""},
    ]
    upload = "id,concept_en,survey_item,custom_order\n1,hair,1.1,10\n2,forehead,1.2,20\n"
    result, rows = _invoke(tmp_path, monkeypatch, existing, upload)

    assert result["ok"] is True
    assert result["matched"] == 2
    assert result["added"] == 0
    rows_by_id = {r["id"]: r for r in rows}
    assert rows_by_id["1"]["survey_item"] == "1.1"
    assert rows_by_id["1"]["custom_order"] == "10"
    assert rows_by_id["2"]["survey_item"] == "1.2"
    assert rows_by_id["3"]["survey_item"] == ""  # unchanged


def test_import_matches_by_label_when_id_missing(tmp_path, monkeypatch):
    existing = [{"id": "1", "concept_en": "hair", "survey_item": "", "custom_order": ""}]
    upload = "concept_en,custom_order\nhair,5\n"
    result, rows = _invoke(tmp_path, monkeypatch, existing, upload)

    assert result["matched"] == 1
    assert rows[0]["custom_order"] == "5"


def test_import_adds_new_concepts(tmp_path, monkeypatch):
    existing = [{"id": "1", "concept_en": "hair", "survey_item": "", "custom_order": ""}]
    upload = "id,concept_en,survey_item\n99,sky,3.1\n"
    result, rows = _invoke(tmp_path, monkeypatch, existing, upload)

    assert result["matched"] == 0
    assert result["added"] == 1
    ids = [r["id"] for r in rows]
    assert ids == ["1", "99"]
    assert rows[1]["survey_item"] == "3.1"


def test_import_replace_mode_clears_unmatched(tmp_path, monkeypatch):
    existing = [
        {"id": "1", "concept_en": "hair", "survey_item": "1.1", "custom_order": "10"},
        {"id": "2", "concept_en": "forehead", "survey_item": "1.2", "custom_order": "20"},
    ]
    upload = "id,concept_en,custom_order\n1,hair,1\n"
    result, rows = _invoke(tmp_path, monkeypatch, existing, upload, mode="replace")

    assert result["mode"] == "replace"
    rows_by_id = {r["id"]: r for r in rows}
    assert rows_by_id["1"]["custom_order"] == "1"
    assert rows_by_id["2"]["custom_order"] == ""
    # Replace clears both fields on every existing row, then merges upload values.
    # Upload didn't provide survey_item for row 1 → stays cleared.
    assert rows_by_id["1"]["survey_item"] == ""
    assert rows_by_id["2"]["survey_item"] == ""


def test_workspace_config_surfaces_survey_and_custom_order(tmp_path, monkeypatch):
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    with open(tmp_path / "concepts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "concept_en", "survey_item", "custom_order"])
        w.writeheader()
        w.writerow({"id": "1", "concept_en": "hair", "survey_item": "1.1", "custom_order": "10"})
        w.writerow({"id": "2", "concept_en": "forehead", "survey_item": "", "custom_order": ""})

    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    cfg = server._workspace_frontend_config({})
    concepts = cfg["concepts"]
    assert concepts[0]["id"] == "1"
    assert concepts[0]["survey_item"] == "1.1"
    assert concepts[0]["custom_order"] == 10
    assert "survey_item" not in concepts[1]
    assert "custom_order" not in concepts[1]
