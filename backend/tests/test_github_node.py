"""Unit tests for GitHubService and the workflow executor GitHub branch."""

import base64
import unittest
import uuid
from unittest.mock import MagicMock, patch

import httpx

from app.db.models import CredentialType
from app.services.github_service import GitHubService


def _make_config() -> dict[str, str]:
    return {
        "api_key": "ghp_test_token",
        "base_url": "https://api.github.com",
    }


def _make_response(status_code: int, payload: object) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/test")
    return httpx.Response(status_code=status_code, json=payload, request=request)


class GitHubServiceTests(unittest.TestCase):
    def test_get_repository_returns_json(self) -> None:
        client = MagicMock()
        client.request.return_value = _make_response(200, {"full_name": "octo/repo"})

        service = GitHubService(_make_config(), client=client)
        result = service.get_repository("octo", "repo")

        self.assertEqual(result["full_name"], "octo/repo")
        _, kwargs = client.request.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer ghp_test_token")

    def test_create_issue_sends_optional_fields(self) -> None:
        client = MagicMock()
        client.request.return_value = _make_response(201, {"number": 42, "title": "Bug"})

        service = GitHubService(_make_config(), client=client)
        result = service.create_issue(
            "octo",
            "repo",
            "Bug",
            body="Details",
            labels=["bug"],
            assignees=["monalisa"],
        )

        self.assertEqual(result["number"], 42)
        _, kwargs = client.request.call_args
        self.assertEqual(
            kwargs["json"],
            {
                "title": "Bug",
                "body": "Details",
                "labels": ["bug"],
                "assignees": ["monalisa"],
            },
        )

    def test_list_issues_filters_out_pull_requests(self) -> None:
        client = MagicMock()
        client.request.return_value = _make_response(
            200,
            [
                {"number": 1, "title": "Issue only"},
                {
                    "number": 2,
                    "title": "Actually a PR",
                    "pull_request": {"url": "https://api.github.com/pulls/2"},
                },
            ],
        )

        service = GitHubService(_make_config(), client=client)
        result = service.list_issues("octo", "repo")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["number"], 1)

    def test_get_file_decodes_base64(self) -> None:
        encoded = base64.b64encode("hello".encode("utf-8")).decode("ascii")
        client = MagicMock()
        client.request.return_value = _make_response(
            200,
            {
                "name": "README.md",
                "path": "README.md",
                "sha": "abc123",
                "encoding": "base64",
                "content": encoded,
                "html_url": "https://github.com/octo/repo/blob/main/README.md",
            },
        )

        service = GitHubService(_make_config(), client=client)
        result = service.get_file("octo", "repo", "README.md")

        self.assertEqual(result["content"], "hello")
        self.assertEqual(result["sha"], "abc123")

    def test_upsert_file_reuses_existing_sha_when_available(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            _make_response(200, {"sha": "existing-sha"}),
            _make_response(
                200,
                {
                    "content": {"path": "README.md", "sha": "new-sha"},
                    "commit": {"sha": "commit-sha"},
                },
            ),
        ]

        service = GitHubService(_make_config(), client=client)
        result = service.upsert_file(
            "octo",
            "repo",
            "README.md",
            "Update README",
            "Hello world",
            branch="main",
        )

        self.assertEqual(result["sha"], "new-sha")
        _, kwargs = client.request.call_args
        self.assertEqual(kwargs["json"]["sha"], "existing-sha")
        self.assertIn("content", kwargs["json"])

    def test_delete_file_fetches_sha_before_delete(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            _make_response(200, {"sha": "existing-sha"}),
            _make_response(200, {"commit": {"sha": "commit-sha"}}),
        ]

        service = GitHubService(_make_config(), client=client)
        result = service.delete_file(
            "octo",
            "repo",
            "README.md",
            "Remove README",
            branch="main",
        )

        self.assertTrue(result["deleted"])
        _, kwargs = client.request.call_args
        self.assertEqual(kwargs["json"]["sha"], "existing-sha")
        self.assertEqual(kwargs["json"]["message"], "Remove README")

    def test_create_release_sends_release_payload(self) -> None:
        client = MagicMock()
        client.request.return_value = _make_response(201, {"id": 7, "tag_name": "v1.2.3"})

        service = GitHubService(_make_config(), client=client)
        result = service.create_release(
            "octo",
            "repo",
            "v1.2.3",
            name="Version 1.2.3",
            body="Release notes",
            target_commitish="main",
            draft=True,
            prerelease=False,
        )

        self.assertEqual(result["id"], 7)
        _, kwargs = client.request.call_args
        self.assertEqual(
            kwargs["json"],
            {
                "tag_name": "v1.2.3",
                "name": "Version 1.2.3",
                "body": "Release notes",
                "target_commitish": "main",
                "draft": True,
                "prerelease": False,
            },
        )

    def test_dispatch_workflow_accepts_no_content_response(self) -> None:
        client = MagicMock()
        request = httpx.Request("POST", "https://api.github.com/test")
        client.request.return_value = httpx.Response(status_code=204, request=request)

        service = GitHubService(_make_config(), client=client)
        result = service.dispatch_workflow(
            "octo",
            "repo",
            "build.yml",
            "main",
            inputs={"environment": "prod"},
        )

        self.assertTrue(result["dispatched"])
        _, kwargs = client.request.call_args
        self.assertEqual(kwargs["json"]["ref"], "main")
        self.assertEqual(kwargs["json"]["inputs"], {"environment": "prod"})

    def test_update_release_includes_false_boolean_fields(self) -> None:
        client = MagicMock()
        client.request.return_value = _make_response(200, {"id": 7, "tag_name": "v1.2.4"})

        service = GitHubService(_make_config(), client=client)
        result = service.update_release(
            "octo",
            "repo",
            7,
            name="",
            body="",
            draft=False,
            prerelease=False,
        )

        self.assertEqual(result["id"], 7)
        _, kwargs = client.request.call_args
        self.assertEqual(
            kwargs["json"],
            {
                "name": "",
                "body": "",
                "draft": False,
                "prerelease": False,
            },
        )

    def test_request_raises_value_error_on_api_error(self) -> None:
        client = MagicMock()
        client.request.return_value = _make_response(404, {"message": "Not Found"})

        service = GitHubService(_make_config(), client=client)

        with self.assertRaises(ValueError) as ctx:
            service.get_repository("octo", "missing")

        self.assertIn("GitHub API error", str(ctx.exception))


def _make_github_workflow(github_data: dict) -> tuple[list[dict], list[dict], dict]:
    nodes = [
        {
            "id": "start",
            "type": "textInput",
            "position": {"x": 0, "y": 0},
            "data": {"label": "start", "value": "hello", "inputFields": [{"key": "text"}]},
        },
        {
            "id": "github",
            "type": "github",
            "position": {"x": 200, "y": 0},
            "data": {"label": "githubNode", **github_data},
        },
        {
            "id": "out",
            "type": "output",
            "position": {"x": 400, "y": 0},
            "data": {"label": "out", "message": "$githubNode", "allowDownstream": False},
        },
    ]
    edges = [
        {"id": "e1", "source": "start", "target": "github"},
        {"id": "e2", "source": "github", "target": "out"},
    ]
    return nodes, edges, {"text": "hello"}


class GitHubExecutorBranchTests(unittest.TestCase):
    def test_missing_credential_results_in_error(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "",
                "githubOperation": "getRepository",
                "githubOwner": "octo",
                "githubRepo": "repo",
            }
        )
        executor = WorkflowExecutor(nodes=nodes, edges=edges)
        result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        self.assertEqual(result.status, "error")
        github_result = next(
            (r for r in result.node_results if r["node_label"] == "githubNode"), None
        )
        self.assertIsNotNone(github_result)
        self.assertIn("credential", github_result.get("error", "").lower())

    def test_get_repository_operation_calls_service(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "getRepository",
                "githubOwner": "octo",
                "githubRepo": "repo",
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.get_repository",
                    return_value={"full_name": "octo/repo"},
                ) as mock_get_repo:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_get_repo.assert_called_once_with("octo", "repo")
        self.assertEqual(result.status, "success")

    def test_create_issue_operation_parses_json_arrays(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "createIssue",
                "githubOwner": "octo",
                "githubRepo": "repo",
                "githubTitle": "Bug report",
                "githubBody": "$input.text",
                "githubLabels": '["bug", "triage"]',
                "githubAssignees": '["monalisa"]',
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.create_issue",
                    return_value={"number": 9, "title": "Bug report"},
                ) as mock_create_issue:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_create_issue.assert_called_once_with(
            "octo",
            "repo",
            "Bug report",
            body="hello",
            labels=["bug", "triage"],
            assignees=["monalisa"],
        )
        self.assertEqual(result.status, "success")

    def test_invalid_labels_json_results_in_error(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "createIssue",
                "githubOwner": "octo",
                "githubRepo": "repo",
                "githubTitle": "Bug report",
                "githubLabels": "{bad json",
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                executor = WorkflowExecutor(nodes=nodes, edges=edges, actor_user_id=uuid.uuid4())
                result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        self.assertEqual(result.status, "error")
        github_result = next(
            (r for r in result.node_results if r["node_label"] == "githubNode"), None
        )
        self.assertIsNotNone(github_result)
        self.assertIn("labels", github_result.get("error", "").lower())

    def test_create_comment_operation_calls_service(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "createComment",
                "githubOwner": "octo",
                "githubRepo": "repo",
                "githubIssueNumber": "14",
                "githubCommentBody": "$input.text",
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.create_issue_comment",
                    return_value={"id": 88, "html_url": "https://github.com/comment"},
                ) as mock_create_comment:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_create_comment.assert_called_once_with("octo", "repo", 14, "hello")
        self.assertEqual(result.status, "success")

    def test_list_organization_repositories_does_not_require_repo(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "listOrganizationRepositories",
                "githubOwner": "octo-org",
                "githubRepo": "",
                "githubPerPage": "50",
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.list_organization_repositories",
                    return_value=[{"full_name": "octo-org/repo"}],
                ) as mock_list_repos:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_list_repos.assert_called_once_with("octo-org", per_page=50)
        self.assertEqual(result.status, "success")

    def test_dispatch_workflow_parses_inputs_json(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "dispatchWorkflow",
                "githubOwner": "octo",
                "githubRepo": "repo",
                "githubWorkflowId": "build.yml",
                "githubBranch": "main",
                "githubWorkflowInputs": '{"environment":"prod"}',
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.dispatch_workflow",
                    return_value={"dispatched": True, "workflow_id": "build.yml"},
                ) as mock_dispatch:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_dispatch.assert_called_once_with(
            "octo",
            "repo",
            "build.yml",
            "main",
            inputs={"environment": "prod"},
        )
        self.assertEqual(result.status, "success")

    def test_invalid_credential_type_results_in_error(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "getRepository",
                "githubOwner": "octo",
                "githubRepo": "repo",
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.custom,
            )
            mock_session.return_value = mock_db

            executor = WorkflowExecutor(nodes=nodes, edges=edges, actor_user_id=uuid.uuid4())
            result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        self.assertEqual(result.status, "error")
        github_result = next(
            (r for r in result.node_results if r["node_label"] == "githubNode"), None
        )
        self.assertIsNotNone(github_result)
        self.assertIn("github credential", github_result.get("error", "").lower())

    def test_update_issue_ignores_empty_lists_from_default_values(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "updateIssue",
                "githubOwner": "octo",
                "githubRepo": "repo",
                "githubIssueNumber": "14",
                "githubLabels": "[]",
                "githubAssignees": "[]",
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.update_issue",
                    return_value={"number": 14, "title": "Issue"},
                ) as mock_update_issue:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_update_issue.assert_called_once_with(
            "octo",
            "repo",
            14,
            title=None,
            body=None,
            state=None,
            labels=None,
            assignees=None,
        )
        self.assertEqual(result.status, "success")

    def test_update_release_passes_false_booleans_and_empty_body(self) -> None:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges, inputs = _make_github_workflow(
            {
                "credentialId": "cred-1",
                "githubOperation": "updateRelease",
                "githubOwner": "octo",
                "githubRepo": "repo",
                "githubReleaseId": "7",
                "githubTagName": "v1.2.4",
                "githubTitle": "",
                "githubBody": "",
                "githubDraft": False,
                "githubPrerelease": False,
            }
        )

        with patch("app.db.session.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                encrypted_config="{}",
                type=CredentialType.github,
            )
            mock_session.return_value = mock_db

            with patch("app.services.encryption.decrypt_config", return_value=_make_config()):
                with patch(
                    "app.services.github_service.GitHubService.update_release",
                    return_value={"id": 7, "tag_name": "v1.2.4"},
                ) as mock_update_release:
                    executor = WorkflowExecutor(
                        nodes=nodes, edges=edges, actor_user_id=uuid.uuid4()
                    )
                    result = executor.execute(workflow_id=uuid.uuid4(), initial_inputs=inputs)

        mock_update_release.assert_called_once_with(
            "octo",
            "repo",
            7,
            tag_name="v1.2.4",
            name="",
            body="",
            target_commitish=None,
            draft=False,
            prerelease=False,
        )
        self.assertEqual(result.status, "success")
