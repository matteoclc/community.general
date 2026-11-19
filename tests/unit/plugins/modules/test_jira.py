# Copyright (c) Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from ansible_collections.community.internal_test_tools.tests.unit.plugins.modules.utils import set_module_args

from ansible_collections.community.general.plugins.modules import jira


BASE_ARGS = {
    "uri": "https://jira.example.com",
    "username": "user@example.com",
    "password": "secret",
}


def make_response(body, status=200):
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode("utf-8") if body is not None else b""
    return (response, {"status": status, "msg": "OK", "body": ""})


@pytest.fixture
def fetch_url_mock():
    with patch.object(jira, "fetch_url") as mock:
        mock.return_value = make_response({})
        yield mock


def run_module(capfd, extra_args, side_effect=None):
    args = dict(BASE_ARGS)
    args.update(extra_args)
    if side_effect is not None:
        fetch = patch.object(jira, "fetch_url", side_effect=side_effect)
    else:
        fetch = patch.object(jira, "fetch_url", return_value=make_response({}))
    with fetch as fetch_url_mock:
        with set_module_args(args):
            with pytest.raises(SystemExit):
                jira.main()
        out, err = capfd.readouterr()
        result = json.loads(out)
    return result, fetch_url_mock


def last_request(fetch_url_mock):
    call = fetch_url_mock.call_args_list[-1]
    url = call.args[1]
    data = call.kwargs.get("data")
    payload = json.loads(data) if data else None
    return url, payload


def test_to_adf_single_line():
    assert jira.JIRA.to_adf("hello") == {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}],
    }


def test_to_adf_line_break_and_paragraph():
    assert jira.JIRA.to_adf("line one\nline two\n\npara two") == {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "line two"},
                ],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": "para two"}]},
        ],
    }


def test_to_adf_empty_string():
    assert jira.JIRA.to_adf("") == {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": []}],
    }


def test_create_cloud_uses_v3_and_adf_description(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {
            "cloud": True,
            "operation": "create",
            "project": "ANS",
            "issuetype": "Task",
            "summary": "Example Issue",
            "description": "first line\nsecond line",
        },
    )
    assert result["changed"] is True
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/3/issue/"
    assert payload["fields"]["description"] == jira.JIRA.to_adf("first line\nsecond line")


def test_create_cloud_adf_description_in_fields(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {
            "cloud": True,
            "operation": "create",
            "project": "ANS",
            "issuetype": "Task",
            "summary": "Example Issue",
            "fields": {"description": "from fields"},
        },
    )
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/3/issue/"
    assert payload["fields"]["description"] == jira.JIRA.to_adf("from fields")


def test_create_server_uses_v2_and_plain_description(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {
            "operation": "create",
            "project": "ANS",
            "issuetype": "Task",
            "summary": "Example Issue",
            "description": "first line\nsecond line",
        },
    )
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/2/issue/"
    assert payload["fields"]["description"] == "first line\nsecond line"


def test_comment_cloud_uses_v3_and_adf_body(capfd):
    result, fetch_url_mock = run_module(capfd, {"cloud": True, "operation": "comment", "issue": "ANS-1", "comment": "bleep\nbleep"})
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/3/issue/ANS-1/comment"
    assert payload["body"] == jira.JIRA.to_adf("bleep\nbleep")


def test_comment_server_uses_v2_and_plain_body(capfd):
    result, fetch_url_mock = run_module(capfd, {"operation": "comment", "issue": "ANS-1", "comment": "bleep\nbleep"})
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/2/issue/ANS-1/comment"
    assert payload["body"] == "bleep\nbleep"


def test_worklog_cloud_uses_v3_and_adf_comment(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {"cloud": True, "operation": "worklog", "issue": "ANS-1", "comment": "work done", "fields": {"timeSpentSeconds": 1200}},
    )
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/3/issue/ANS-1/worklog"
    assert payload["comment"] == jira.JIRA.to_adf("work done")
    assert payload["timeSpentSeconds"] == 1200


def test_transition_cloud_uses_v3_adf_comment_and_description(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {
            "cloud": True,
            "operation": "transition",
            "issue": "ANS-1",
            "status": "Resolve Issue",
            "comment": "-> resolved",
            "description": "done\n\nreally",
        },
        side_effect=[
            make_response({"transitions": [{"id": "31", "name": "Resolve Issue"}]}),
            make_response({}),
        ],
    )
    get_url = fetch_url_mock.call_args_list[0].args[1]
    assert get_url == "https://jira.example.com/rest/api/3/issue/ANS-1/transitions"
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/3/issue/ANS-1/transitions"
    assert payload["transition"] == {"id": "31"}
    assert payload["fields"]["description"] == jira.JIRA.to_adf("done\n\nreally")
    assert payload["update"]["comment"] == [{"add": {"body": jira.JIRA.to_adf("-> resolved")}}]


def test_transition_server_uses_v2_and_plain_values(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {
            "operation": "transition",
            "issue": "ANS-1",
            "status": "Resolve Issue",
            "comment": "-> resolved",
            "description": "done",
        },
        side_effect=[
            make_response({"transitions": [{"id": "31", "name": "Resolve Issue"}]}),
            make_response({}),
        ],
    )
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/2/issue/ANS-1/transitions"
    assert payload["fields"]["description"] == "done"
    assert payload["update"]["comment"] == [{"add": {"body": "-> resolved"}}]


def test_search_cloud_uses_v3_search_jql(capfd):
    result, fetch_url_mock = run_module(capfd, {"cloud": True, "operation": "search", "jql": "project = ANS", "maxresults": 10})
    url = fetch_url_mock.call_args_list[-1].args[1]
    assert url.startswith("https://jira.example.com/rest/api/3/search/jql?")
    assert "jql=project%20%3D%20ANS" in url
    assert "maxResults=10" in url
    assert "fields=*navigable" in url


def test_search_server_uses_v2_search(capfd):
    result, fetch_url_mock = run_module(capfd, {"operation": "search", "jql": "project = ANS"})
    url = fetch_url_mock.call_args_list[-1].args[1]
    assert url.startswith("https://jira.example.com/rest/api/2/search?")
    assert "jql=project%20%3D%20ANS" in url


def test_fetch_cloud_uses_v3(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {"cloud": True, "operation": "fetch", "issue": "ANS-1"},
        side_effect=None,
    )
    url = fetch_url_mock.call_args_list[-1].args[1]
    assert url == "https://jira.example.com/rest/api/3/issue/ANS-1"


def test_edit_cloud_uses_v3(capfd):
    result, fetch_url_mock = run_module(capfd, {"cloud": True, "operation": "edit", "issue": "ANS-1", "fields": {"labels": ["ansible"]}})
    call = fetch_url_mock.call_args_list[-1]
    assert call.args[1] == "https://jira.example.com/rest/api/3/issue/ANS-1"
    assert call.kwargs["method"] == "PUT"
    assert json.loads(call.kwargs["data"]) == {"fields": {"labels": ["ansible"]}}


def test_link_cloud_uses_v3(capfd):
    result, fetch_url_mock = run_module(
        capfd,
        {"cloud": True, "operation": "link", "linktype": "Relates", "inwardissue": "ANS-1", "outwardissue": "ANS-2"},
    )
    url, payload = last_request(fetch_url_mock)
    assert url == "https://jira.example.com/rest/api/3/issueLink/"
    assert payload == {
        "type": {"name": "Relates"},
        "inwardIssue": {"key": "ANS-1"},
        "outwardIssue": {"key": "ANS-2"},
    }
