"""Platform Updates: group origin/master commits by JIRA key across FE+BE."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

import platform_updates  # noqa: E402
from platform_updates import (  # noqa: E402
    bitbucket_commit_url,
    build_platform_report,
    collect_master_commits,
    extract_jira_keys,
    fallback_title,
    format_platform_report,
    group_commits_by_ticket,
    summarize_ticket,
)


def test_extract_jira_keys_finds_unique_keys_in_subject_and_body():
    text = "TEL-123 fix hanging viewer\nAlso covers TEL-123 and TEL-99 extras"
    assert extract_jira_keys(text) == ["TEL-123", "TEL-99"]


def test_extract_jira_keys_empty_when_no_ticket():
    assert extract_jira_keys("tidy logging in the worker") == []


def test_extract_jira_keys_ignores_encoding_and_hash_labels():
    assert extract_jira_keys("charset UTF-8 and digest SHA-256") == []
    assert extract_jira_keys("ISO-8859-1 fallback") == []
    assert extract_jira_keys("TPC-4832 load UTF-8 DICOM tags") == ["TPC-4832"]


def test_group_commits_by_ticket_merges_backend_and_frontend():
    commits = [
        {
            "hash": "aaa111",
            "author": "Rong Yin",
            "date": "2026-08-20 10:00:00 +0200",
            "subject": "TEL-123 stream tiles in chunks",
            "body": "",
            "repo_name": "Teleradiology Cloud Backend",
            "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
        },
        {
            "hash": "bbb222",
            "author": "Eason Li",
            "date": "2026-08-21 16:30:00 +0200",
            "subject": "TEL-123 progress spinner for large studies",
            "body": "",
            "repo_name": "Teleradiology Cloud Frontend",
            "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-frontend.git",
        },
        {
            "hash": "ccc333",
            "author": "Someone",
            "date": "2026-08-21 09:00:00 +0200",
            "subject": "chore: bump eslint",
            "body": "",
            "repo_name": "Teleradiology Cloud Frontend",
            "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-frontend.git",
        },
    ]
    grouped = group_commits_by_ticket(commits)
    assert list(grouped) == ["TEL-123"]
    task = grouped["TEL-123"]
    assert task["authors"] == ["Rong Yin", "Eason Li"]
    assert task["repos"] == [
        "Teleradiology Cloud Backend",
        "Teleradiology Cloud Frontend",
    ]
    assert task["merge_date"].startswith("2026-08-21")
    assert len(task["commits"]) == 2


def test_fallback_title_strips_jira_key_from_subject():
    assert fallback_title("TEL-123: stream tiles in chunks", "TEL-123") == (
        "stream tiles in chunks"
    )


def test_bitbucket_commit_url_from_scm_origin():
    url = bitbucket_commit_url(
        "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
        "aaa111",
    )
    assert url == (
        "https://git.medavis.local/projects/TEL/repos/"
        "teleradiology-cloud-backend/commits/aaa111"
    )


def test_format_platform_report_has_key_authors_date_links_no_commit_list():
    tasks = [
        {
            "key": "TEL-123",
            "title": "Viewer hanging on large studies",
            "blurb": (
                "Backend streams tiles in chunks and the frontend shows a "
                "progress spinner so large studies no longer freeze."
            ),
            "merge_date": "2026-08-21",
            "authors": ["Rong Yin", "Eason Li"],
            "repos": [
                "Teleradiology Cloud Backend",
                "Teleradiology Cloud Frontend",
            ],
            "jira_url": "https://medavis.atlassian.net/browse/TEL-123",
            "commit_links": [
                (
                    "Teleradiology Cloud Backend",
                    "https://git.medavis.local/projects/TEL/repos/"
                    "teleradiology-cloud-backend/commits/aaa111",
                ),
                (
                    "Teleradiology Cloud Frontend",
                    "https://git.medavis.local/projects/TEL/repos/"
                    "teleradiology-cloud-frontend/commits/bbb222",
                ),
            ],
        }
    ]
    report = format_platform_report(
        platform_label="Radiology Platform",
        date_from="2026-08-17",
        date_to="2026-08-24",
        tasks=tasks,
        warnings=["frontend: git fetch failed (using local origin/master)"],
    )
    assert "Radiology Platform" in report
    assert "TEL-123" in report
    assert "Viewer hanging on large studies" in report
    assert "Rong Yin" in report
    assert "Eason Li" in report
    assert "2026-08-21" in report
    assert "https://medavis.atlassian.net/browse/TEL-123" in report
    assert "teleradiology-cloud-backend/commits/aaa111" in report
    assert "progress spinner" in report
    before_url, _, after_url = report.partition("commits/aaa111")
    assert "aaa111" not in before_url
    assert "aaa111" not in after_url
    assert "chore: bump eslint" not in report
    assert "git fetch failed" in report


def test_format_platform_report_empty_state():
    report = format_platform_report(
        platform_label="Radiology Platform",
        date_from="2026-08-01",
        date_to="2026-08-02",
        tasks=[],
        warnings=[],
    )
    assert "No master-merged JIRA tasks" in report
    assert "Radiology Platform" in report


class _FakeChatResp:
    def __init__(self, text: str):
        self._text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"message": {"content": self._text}}


def test_summarize_ticket_returns_model_text():
    blurb = summarize_ticket(
        {
            "key": "TEL-1",
            "title": "Hang",
            "subjects": ["TEL-1 stream tiles"],
            "repos": ["Backend"],
        },
        http_post=lambda *a, **k: _FakeChatResp("Backend streams tiles."),
    )
    assert blurb == "Backend streams tiles."


def test_require_platform_rejects_unknown():
    with pytest.raises(platform_updates.UnknownPlatformError, match="Unknown platform"):
        platform_updates.require_platform("nope")
    with pytest.raises(platform_updates.UnknownPlatformError, match="radiology"):
        platform_updates.require_platform("nope")


def test_build_platform_report_unknown_platform():
    with pytest.raises(platform_updates.UnknownPlatformError, match="Unknown platform"):
        build_platform_report("nope", "2026-08-01", "2026-08-02")


def test_build_platform_report_groups_fe_be_and_drops_unkeyed(monkeypatch):
    def fake_collect(name, path, date_from, date_to):
        if "Backend" in name:
            commits = [
                {
                    "hash": "aaa111",
                    "author": "Rong Yin",
                    "date": "2026-08-20 10:00:00 +0200",
                    "subject": "TEL-123 stream tiles in chunks",
                    "body": "",
                    "repo_name": name,
                    "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
                }
            ]
        else:
            commits = [
                {
                    "hash": "bbb222",
                    "author": "Eason Li",
                    "date": "2026-08-21 16:30:00 +0200",
                    "subject": "TEL-123 progress spinner for large studies",
                    "body": "",
                    "repo_name": name,
                    "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-frontend.git",
                },
                {
                    "hash": "ccc333",
                    "author": "Someone",
                    "date": "2026-08-21 09:00:00 +0200",
                    "subject": "chore: bump eslint",
                    "body": "",
                    "repo_name": name,
                    "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-frontend.git",
                },
            ]
        return commits, []

    monkeypatch.setattr(platform_updates, "collect_master_commits", fake_collect)
    report = build_platform_report(
        "radiology",
        "2026-08-17",
        "2026-08-24",
        http_post=lambda *a, **k: _FakeChatResp(
            "Backend streams tiles and the frontend shows a progress spinner."
        ),
    )
    assert "TEL-123" in report
    assert "Rong Yin" in report
    assert "Eason Li" in report
    assert "progress spinner" in report
    assert "chore: bump eslint" not in report
    assert "teleradiology-cloud-backend/commits/aaa111" in report
    assert "teleradiology-cloud-frontend/commits/bbb222" in report


def test_build_platform_report_caps_llm_calls(monkeypatch):
    monkeypatch.setattr(platform_updates, "MAX_TASKS", 2)
    calls = {"n": 0}

    def fake_collect(name, path, date_from, date_to):
        if "Frontend" in name:
            return [], []
        commits = []
        for i in range(5):
            commits.append(
                {
                    "hash": f"abc{i}",
                    "author": "Rong Yin",
                    "date": f"2026-08-2{i} 10:00:00 +0200",
                    "subject": f"TEL-{100 + i} change {i}",
                    "body": "",
                    "repo_name": name,
                    "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
                }
            )
        return commits, []

    def fake_post(*a, **k):
        calls["n"] += 1
        return _FakeChatResp("blurb")

    monkeypatch.setattr(platform_updates, "collect_master_commits", fake_collect)
    monkeypatch.setattr(platform_updates, "fetch_jira_title", lambda *a, **k: "")
    report = build_platform_report(
        "radiology", "2026-08-01", "2026-08-24", http_post=fake_post
    )
    assert calls["n"] == 2
    assert "2 most recent of 5" in report


def test_build_platform_report_jira_only_for_capped_tasks(monkeypatch):
    monkeypatch.setattr(platform_updates, "MAX_TASKS", 2)
    jira_keys: list[str] = []

    def fake_collect(name, path, date_from, date_to):
        if "Frontend" in name:
            return [], []
        commits = []
        for i in range(5):
            commits.append(
                {
                    "hash": f"abc{i}",
                    "author": "Rong Yin",
                    "date": f"2026-08-2{i} 10:00:00 +0200",
                    "subject": f"TEL-{100 + i} change {i}",
                    "body": "",
                    "repo_name": name,
                    "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
                }
            )
        return commits, []

    def fake_jira(key, http_get=None):
        jira_keys.append(key)
        return ""

    monkeypatch.setattr(platform_updates, "collect_master_commits", fake_collect)
    monkeypatch.setattr(platform_updates, "fetch_jira_title", fake_jira)
    build_platform_report(
        "radiology",
        "2026-08-01",
        "2026-08-24",
        http_post=lambda *a, **k: _FakeChatResp("blurb"),
    )
    assert jira_keys == ["TEL-104", "TEL-103"]


def test_task_commit_links_keeps_newer_same_day_commit():
    task = {
        "commits": [
            {
                "hash": "new111",
                "date": "2026-08-21 16:00:00 +0200",
                "repo_name": "Teleradiology Cloud Backend",
                "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
            },
            {
                "hash": "old222",
                "date": "2026-08-21 09:00:00 +0200",
                "repo_name": "Teleradiology Cloud Backend",
                "remote_url": "https://git.medavis.local/scm/tel/teleradiology-cloud-backend.git",
            },
        ]
    }
    links = platform_updates._task_commit_links(task)
    assert len(links) == 1
    assert links[0][1].endswith("/commits/new111")

    task["commits"] = list(reversed(task["commits"]))
    links = platform_updates._task_commit_links(task)
    assert links[0][1].endswith("/commits/new111")


class _Proc:
    def __init__(self, code: int, stdout: str = "", stderr: str = ""):
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def test_master_ref_origin_only_no_local_master_fallback(monkeypatch):
    def fake_run(cmd, path, timeout=10):
        if "origin/master" in cmd:
            return _Proc(1, stderr="missing")
        if cmd and cmd[-1] == "master":
            return _Proc(0, stdout="abc123")
        return _Proc(1)

    monkeypatch.setattr(platform_updates, "_run_git", fake_run)
    assert platform_updates._master_ref("/tmp/repo") == ""


def test_master_ref_uses_origin_master(monkeypatch):
    monkeypatch.setattr(
        platform_updates,
        "_run_git",
        lambda cmd, path, timeout=10: _Proc(0, stdout="def456"),
    )
    assert platform_updates._master_ref("/tmp/repo") == "origin/master"


def test_collect_skips_repo_without_origin_master(monkeypatch, tmp_path):
    monkeypatch.setattr(platform_updates, "_fetch_repo", lambda p: "")
    monkeypatch.setattr(platform_updates, "_master_ref", lambda p: "")
    commits, warnings = collect_master_commits(
        "Backend", str(tmp_path), "2026-08-01", "2026-08-24"
    )
    assert commits == []
    assert any("origin/master" in w and "or master" not in w for w in warnings)


def test_collect_fetch_fail_without_origin_master_omits_local_promise(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        platform_updates, "_fetch_repo", lambda p: "git fetch failed (offline)"
    )
    monkeypatch.setattr(platform_updates, "_master_ref", lambda p: "")
    commits, warnings = collect_master_commits(
        "Backend", str(tmp_path), "2026-08-01", "2026-08-24"
    )
    assert commits == []
    assert any("git fetch failed" in w for w in warnings)
    assert not any("using local origin/master" in w for w in warnings)


def test_collect_master_commits_defaults_empty_dates(monkeypatch, tmp_path):
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(platform_updates, "_fetch_repo", lambda p: "")
    monkeypatch.setattr(platform_updates, "_master_ref", lambda p: "origin/master")
    monkeypatch.setattr(platform_updates, "_remote_url", lambda p: "")

    def fake_run(cmd, path, timeout=60):
        captured["cmd"] = cmd
        return _Proc(0, stdout="")

    monkeypatch.setattr(platform_updates, "_run_git", fake_run)
    collect_master_commits("Backend", str(tmp_path), "", "")
    cmd = captured["cmd"]
    today = date.today()
    expected_from = (today - timedelta(days=7)).isoformat()
    expected_to = today.isoformat()
    assert any(f"--since={expected_from} 00:00:00" in part for part in cmd)
    assert any(f"--until={expected_to} 23:59:59" in part for part in cmd)


def test_build_platform_report_defaults_empty_dates(monkeypatch):
    seen: list[tuple[str, str]] = []

    def fake_collect(name, path, date_from, date_to):
        seen.append((date_from, date_to))
        return [], []

    monkeypatch.setattr(platform_updates, "collect_master_commits", fake_collect)
    build_platform_report("radiology", "", "")
    assert seen
    today = date.today()
    expected = ((today - timedelta(days=7)).isoformat(), today.isoformat())
    assert all(pair == expected for pair in seen)


def test_resolve_date_range_fills_missing_ends():
    today = date.today()
    date_from, date_to = platform_updates.resolve_date_range("", "")
    assert date_from == (today - timedelta(days=7)).isoformat()
    assert date_to == today.isoformat()
    assert platform_updates.resolve_date_range("2026-08-01", "2026-08-24") == (
        "2026-08-01",
        "2026-08-24",
    )


def test_clip_report_appends_warning_within_limit():
    body = "x" * 200
    limit = 80
    clipped = platform_updates.clip_report(body, limit=limit)
    note = platform_updates._truncation_note(limit)
    assert len(clipped) == limit
    assert clipped.endswith(note)
    assert "truncated" in note.lower()


def test_clip_report_tiny_limit_stays_within_cap():
    clipped = platform_updates.clip_report("x" * 200, limit=20)
    assert len(clipped) <= 20


def test_clip_report_leaves_short_report_unchanged():
    assert platform_updates.clip_report("hello", limit=80) == "hello"


def test_platform_updates_post_unknown_platform_returns_400():
    from web_api import Flask

    _routes = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "rag", "routes")
    )
    if _routes not in sys.path:
        sys.path.insert(0, _routes)
    import toolbar as toolbar_mod  # noqa: E402

    app = Flask(__name__)
    app.register_blueprint(toolbar_mod.toolbar_bp)
    resp = app.test_client().post(
        "/api/toolbar/platform-updates",
        json={"platform": "nope"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data is not None
    assert "Unknown platform" in data["error"]
    assert "radiology" in data["error"]
