"""Tests for POST /api/tags/import — CSV-driven tag creation with concept auto-assignment."""
import csv
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

    def write(self, data):
        self.chunks.append(data)

    def flush(self):
        pass

    def payload(self) -> dict:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)


def _make_multipart(csv_body: str, *, filename: str = "custom.csv",
                    tag_name: str | None = None, color: str | None = None) -> tuple[bytes, str]:
    boundary = "----parseboundary"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="csv"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: text/csv\r\n\r\n",
        csv_body.encode("utf-8"),
        b"\r\n",
    ]
    if tag_name is not None:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="tagName"\r\n\r\n',
            tag_name.encode(),
            b"\r\n",
        ]
    if color is not None:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="color"\r\n\r\n',
            color.encode(),
            b"\r\n",
        ]
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _invoke(tmp_path, monkeypatch, *, concepts_rows, upload_csv,
            filename: str = "custom.csv", tag_name: str | None = None, color: str | None = None,
            existing_tags: list | None = None):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    if concepts_rows is not None:
        with open(tmp_path / "concepts.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "concept_en"])
            w.writeheader()
            for r in concepts_rows:
                w.writerow(r)

    if existing_tags is not None:
        with open(tmp_path / "parse-tags.json", "w", encoding="utf-8") as f:
            json.dump(existing_tags, f)

    body, boundary = _make_multipart(upload_csv, filename=filename, tag_name=tag_name, color=color)
    hdr_text = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    headers = email.parser.Parser(policy=email.policy.compat32).parsestr(hdr_text)

    class H(server.RangeRequestHandler):
        def __init__(self):
            self.rfile = io.BytesIO(body)
            self.wfile = _FakeWfile()
            self.headers = headers

        def send_response(self, code):
            pass

        def send_header(self, *a, **kw):
            pass

        def end_headers(self):
            pass

    handler = H()
    handler._api_post_tags_import()
    result = handler.wfile.payload()

    tags_path = tmp_path / "parse-tags.json"
    tags = json.loads(tags_path.read_text("utf-8")) if tags_path.exists() else []
    return result, tags


def test_tags_import_creates_tag_and_matches_by_label(tmp_path, monkeypatch):
    concepts = [
        {"id": "1", "concept_en": "hair"},
        {"id": "2", "concept_en": "forehead"},
        {"id": "3", "concept_en": "eyelid"},
    ]
    upload = "id,concept_en\n,hair\n,forehead\n,sky\n"
    result, tags = _invoke(
        tmp_path, monkeypatch,
        concepts_rows=concepts, upload_csv=upload, tag_name="Custom SK",
    )

    assert result["ok"] is True
    assert result["tagId"] == "custom-sk"
    assert result["matchedCount"] == 2
    assert result["missedCount"] == 1
    assert result["missedLabels"] == ["sky"]
    assert len(tags) == 1
    assert tags[0]["label"] == "Custom SK"
    assert set(tags[0]["concepts"]) == {"1", "2"}


def test_tags_import_matches_by_id_when_label_missing(tmp_path, monkeypatch):
    concepts = [{"id": "1", "concept_en": "hair"}]
    upload = "id\n1\n"
    result, tags = _invoke(tmp_path, monkeypatch, concepts_rows=concepts,
                           upload_csv=upload, tag_name="Oxford")
    assert result["matchedCount"] == 1
    assert set(tags[0]["concepts"]) == {"1"}


def test_tags_import_defaults_tag_name_to_filename_stem(tmp_path, monkeypatch):
    concepts = [{"id": "1", "concept_en": "hair"}]
    upload = "concept_en\nhair\n"
    result, tags = _invoke(tmp_path, monkeypatch, concepts_rows=concepts,
                           upload_csv=upload, filename="oxford_85.csv")
    assert result["tagName"] == "oxford_85"
    assert result["tagId"] == "oxford-85"


def test_tags_import_is_additive_on_existing_tag_id(tmp_path, monkeypatch):
    concepts = [
        {"id": "1", "concept_en": "hair"},
        {"id": "2", "concept_en": "forehead"},
        {"id": "3", "concept_en": "eyelid"},
    ]
    existing = [
        {"id": "oxford", "label": "Oxford", "color": "#ff0000", "concepts": ["1"]},
    ]
    upload = "concept_en\nforehead\neyelid\n"
    result, tags = _invoke(tmp_path, monkeypatch, concepts_rows=concepts,
                           upload_csv=upload, tag_name="Oxford", existing_tags=existing)
    assert result["matchedCount"] == 2
    oxford = next(t for t in tags if t["id"] == "oxford")
    assert set(oxford["concepts"]) == {"1", "2", "3"}  # 1 preserved, 2 and 3 added


def test_tags_import_errors_on_all_misses(tmp_path, monkeypatch):
    concepts = [{"id": "1", "concept_en": "hair"}]
    upload = "concept_en\nsky\ncloud\n"
    try:
        _invoke(tmp_path, monkeypatch, concepts_rows=concepts,
                upload_csv=upload, tag_name="Bad")
    except server.ApiError as exc:
        assert "No rows matched" in exc.message
    else:
        raise AssertionError("expected ApiError")


def test_tags_import_uses_default_color_when_omitted(tmp_path, monkeypatch):
    concepts = [{"id": "1", "concept_en": "hair"}]
    upload = "concept_en\nhair\n"
    result, tags = _invoke(tmp_path, monkeypatch, concepts_rows=concepts,
                           upload_csv=upload, tag_name="X")
    assert tags[0]["color"] == "#4461d4"
    assert result["color"] == "#4461d4"
