import base64
from typing import Any
from urllib.parse import quote

import httpx

from app.http_identity import merge_outbound_headers

GITHUB_API_BASE_URL = "https://api.github.com"


class GitHubService:
    """Small REST client for GitHub and GitHub Enterprise API operations."""

    def __init__(self, config: dict[str, Any], client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            headers=merge_outbound_headers(
                {
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
            ),
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        self._owns_client = client is None

    def close(self) -> None:
        """Close the internally owned HTTP client, if any."""
        if self._owns_client and not self._client.is_closed:
            self._client.close()

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch repository metadata."""
        return self._request_json("GET", f"/repos/{owner}/{repo}")

    def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        """Fetch one issue by number."""
        return self._request_json("GET", f"/repos/{owner}/{repo}/issues/{issue_number}")

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repository issues."""
        response = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={"state": state or "open", "per_page": max(1, min(per_page, 100))},
        )
        if not isinstance(response, list):
            return []
        return [
            item
            for item in response
            if isinstance(item, dict) and not isinstance(item.get("pull_request"), dict)
        ]

    def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Create an issue comment."""
        return self._request_json(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )

    def lock_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        lock_reason: str | None = None,
    ) -> dict[str, Any]:
        """Lock a repository issue."""
        payload = {"lock_reason": lock_reason} if lock_reason else None
        self._request_no_content(
            "PUT",
            f"/repos/{owner}/{repo}/issues/{issue_number}/lock",
            json=payload,
            success_codes=(204,),
        )
        return {"issue_number": issue_number, "locked": True, "lock_reason": lock_reason}

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a GitHub issue."""
        payload: dict[str, Any] = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        return self._request_json("POST", f"/repos/{owner}/{repo}/issues", json=payload)

    def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing GitHub issue."""
        payload: dict[str, Any] = {}
        if title is not None and title != "":
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        if not payload:
            raise ValueError("GitHub updateIssue requires at least one field to update")
        return self._request_json(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json=payload,
        )

    def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repository pull requests."""
        response = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state or "open", "per_page": max(1, min(per_page, 100))},
        )
        return response if isinstance(response, list) else []

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request."""
        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
        }
        if body:
            payload["body"] = body
        return self._request_json("POST", f"/repos/{owner}/{repo}/pulls", json=payload)

    def list_releases(
        self,
        owner: str,
        repo: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repository releases."""
        response = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/releases",
            params={"per_page": max(1, min(per_page, 100))},
        )
        return response if isinstance(response, list) else []

    def get_release(self, owner: str, repo: str, release_id: int) -> dict[str, Any]:
        """Fetch a release by id."""
        return self._request_json("GET", f"/repos/{owner}/{repo}/releases/{release_id}")

    def create_release(
        self,
        owner: str,
        repo: str,
        tag_name: str,
        name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool = False,
        prerelease: bool = False,
    ) -> dict[str, Any]:
        """Create a release."""
        payload: dict[str, Any] = {
            "tag_name": tag_name,
            "draft": draft,
            "prerelease": prerelease,
        }
        if name:
            payload["name"] = name
        if body:
            payload["body"] = body
        if target_commitish:
            payload["target_commitish"] = target_commitish
        return self._request_json("POST", f"/repos/{owner}/{repo}/releases", json=payload)

    def update_release(
        self,
        owner: str,
        repo: str,
        release_id: int,
        tag_name: str | None = None,
        name: str | None = None,
        body: str | None = None,
        target_commitish: str | None = None,
        draft: bool | None = None,
        prerelease: bool | None = None,
    ) -> dict[str, Any]:
        """Update a release."""
        payload: dict[str, Any] = {}
        if tag_name:
            payload["tag_name"] = tag_name
        if name is not None:
            payload["name"] = name
        if body is not None:
            payload["body"] = body
        if target_commitish:
            payload["target_commitish"] = target_commitish
        if draft is not None:
            payload["draft"] = draft
        if prerelease is not None:
            payload["prerelease"] = prerelease
        if not payload:
            raise ValueError("GitHub updateRelease requires at least one field to update")
        return self._request_json(
            "PATCH", f"/repos/{owner}/{repo}/releases/{release_id}", json=payload
        )

    def delete_release(self, owner: str, repo: str, release_id: int) -> dict[str, Any]:
        """Delete a release by id."""
        self._request_no_content(
            "DELETE",
            f"/repos/{owner}/{repo}/releases/{release_id}",
            success_codes=(204,),
        )
        return {"release_id": release_id, "deleted": True}

    def list_workflows(
        self,
        owner: str,
        repo: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List GitHub Actions workflows for a repository."""
        response = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/actions/workflows",
            params={"per_page": max(1, min(per_page, 100))},
        )
        if isinstance(response, dict):
            workflows = response.get("workflows")
            return workflows if isinstance(workflows, list) else []
        return []

    def get_workflow(self, owner: str, repo: str, workflow_id: str) -> dict[str, Any]:
        """Fetch a workflow by numeric id or file name."""
        return self._request_json("GET", f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}")

    def dispatch_workflow(
        self,
        owner: str,
        repo: str,
        workflow_id: str,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a workflow run."""
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs
        self._request_no_content(
            "POST",
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json=payload,
            success_codes=(204,),
        )
        return {"workflow_id": workflow_id, "ref": ref, "inputs": inputs or {}, "dispatched": True}

    def get_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Read a repository file through the contents API."""
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        data = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/contents/{quote(path.lstrip('/'), safe='/')}",
            params=params or None,
        )
        if not isinstance(data, dict):
            raise ValueError("GitHub getFile returned an unexpected response")

        encoding = str(data.get("encoding") or "").lower()
        decoded_text: str | None = None
        if encoding == "base64" and data.get("content"):
            try:
                decoded_text = base64.b64decode(str(data["content"]).encode("utf-8")).decode(
                    "utf-8"
                )
            except Exception:
                decoded_text = None

        return {
            "name": data.get("name"),
            "path": data.get("path"),
            "sha": data.get("sha"),
            "size": data.get("size"),
            "url": data.get("html_url") or data.get("download_url") or data.get("url"),
            "content": decoded_text,
            "encoding": data.get("encoding"),
        }

    def list_files(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str | None = None,
    ) -> dict[str, Any]:
        """List files inside a repository directory via the contents API."""
        normalized_path = quote(path.lstrip("/"), safe="/")
        endpoint = f"/repos/{owner}/{repo}/contents"
        if normalized_path:
            endpoint = f"{endpoint}/{normalized_path}"
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        data = self._request_json("GET", endpoint, params=params or None)
        if not isinstance(data, list):
            raise ValueError("GitHub listFiles expects a directory path")
        items: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "sha": item.get("sha"),
                    "size": item.get("size"),
                    "url": item.get("html_url") or item.get("download_url") or item.get("url"),
                }
            )
        return {"path": path or "", "items": items, "count": len(items)}

    def upsert_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        content: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a repository file."""
        normalized_path = quote(path.lstrip("/"), safe="/")
        target_sha = sha.strip() if sha else ""
        if not target_sha:
            try:
                existing = self._request_json(
                    "GET",
                    f"/repos/{owner}/{repo}/contents/{normalized_path}",
                    params={"ref": branch} if branch else None,
                )
                if isinstance(existing, dict):
                    target_sha = str(existing.get("sha") or "").strip()
            except ValueError as exc:
                if "404" not in str(exc):
                    raise

        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if branch:
            payload["branch"] = branch
        if target_sha:
            payload["sha"] = target_sha

        data = self._request_json(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{normalized_path}",
            json=payload,
        )
        if not isinstance(data, dict):
            raise ValueError("GitHub upsertFile returned an unexpected response")

        content_data = data.get("content") if isinstance(data.get("content"), dict) else {}
        commit_data = data.get("commit") if isinstance(data.get("commit"), dict) else {}
        return {
            "path": content_data.get("path") or path,
            "sha": content_data.get("sha"),
            "commit_sha": commit_data.get("sha"),
            "url": content_data.get("html_url") or content_data.get("git_url"),
            "created": not bool(target_sha),
        }

    def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Delete a repository file."""
        normalized_path = quote(path.lstrip("/"), safe="/")
        target_sha = sha.strip() if sha else ""
        if not target_sha:
            existing = self._request_json(
                "GET",
                f"/repos/{owner}/{repo}/contents/{normalized_path}",
                params={"ref": branch} if branch else None,
            )
            if not isinstance(existing, dict):
                raise ValueError("GitHub deleteFile could not resolve the existing file SHA")
            target_sha = str(existing.get("sha") or "").strip()
        if not target_sha:
            raise ValueError("GitHub deleteFile requires a file SHA")

        payload: dict[str, Any] = {"message": message, "sha": target_sha}
        if branch:
            payload["branch"] = branch
        data = self._request_json(
            "DELETE",
            f"/repos/{owner}/{repo}/contents/{normalized_path}",
            json=payload,
        )
        if not isinstance(data, dict):
            raise ValueError("GitHub deleteFile returned an unexpected response")

        commit_data = data.get("commit") if isinstance(data.get("commit"), dict) else {}
        return {
            "path": path,
            "sha": target_sha,
            "commit_sha": commit_data.get("sha"),
            "deleted": True,
        }

    def list_organization_repositories(
        self,
        organization: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repositories for an organization."""
        response = self._request_json(
            "GET",
            f"/orgs/{organization}/repos",
            params={"per_page": max(1, min(per_page, 100))},
        )
        return response if isinstance(response, list) else []

    def list_user_repositories(
        self,
        username: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repositories for a user."""
        response = self._request_json(
            "GET",
            f"/users/{username}/repos",
            params={"per_page": max(1, min(per_page, 100))},
        )
        return response if isinstance(response, list) else []

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self._base_url()}{path}"
        response = self._client.request(
            method,
            url,
            params=params,
            json=json,
            headers=self._auth_headers(),
        )
        if response.status_code >= 400:
            raise ValueError(self._build_error_message(response))
        try:
            return response.json()
        except ValueError as exc:
            raise ValueError("GitHub API returned non-JSON response") from exc

    def _request_no_content(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        success_codes: tuple[int, ...] = (204,),
    ) -> None:
        url = f"{self._base_url()}{path}"
        response = self._client.request(
            method,
            url,
            params=params,
            json=json,
            headers=self._auth_headers(),
        )
        if response.status_code not in success_codes:
            raise ValueError(self._build_error_message(response))

    def _base_url(self) -> str:
        raw = str(self._config.get("base_url") or "").strip()
        return raw.rstrip("/") if raw else GITHUB_API_BASE_URL

    def _auth_headers(self) -> dict[str, str]:
        token = str(self._config.get("api_key") or self._config.get("token") or "").strip()
        if not token:
            raise ValueError("GitHub credential requires api_key")
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _build_error_message(response: httpx.Response) -> str:
        prefix = f"GitHub API error ({response.status_code})"
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip()
            return f"{prefix}: {text or 'unknown error'}"

        if isinstance(data, dict):
            message = str(data.get("message") or "").strip()
            errors = data.get("errors")
            if isinstance(errors, list) and errors:
                detail_parts: list[str] = []
                for item in errors:
                    if isinstance(item, dict):
                        detail = str(
                            item.get("message") or item.get("code") or item.get("field") or ""
                        ).strip()
                        if detail:
                            detail_parts.append(detail)
                    elif item:
                        detail_parts.append(str(item))
                if detail_parts:
                    message = (
                        f"{message} ({'; '.join(detail_parts)})"
                        if message
                        else "; ".join(detail_parts)
                    )
            if message:
                return f"{prefix}: {message}"

        return f"{prefix}: unknown error"
