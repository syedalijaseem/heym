# GitHub Node

The **GitHub** node adds native GitHub REST operations to a workflow, similar to the multi-operation GitHub nodes you may know from tools like n8n.

## Overview

| Property | Value |
|----------|-------|
| Inputs | 1 |
| Outputs | 1 |
| Credential | GitHub |
| Output | `$nodeLabel.*` |

## Supported Operations

- `Get Repository`
- `List Organization Repositories`
- `List User Repositories`
- `Get Issue`
- `List Issues`
- `Create Comment`
- `Create Issue`
- `Update Issue`
- `Lock Issue`
- `List Pull Requests`
- `Create Pull Request`
- `List Releases`
- `Get Release`
- `Create Release`
- `Update Release`
- `Delete Release`
- `List Workflows`
- `Get Workflow`
- `Dispatch Workflow`
- `Get File`
- `List Files`
- `Create or Update File`
- `Delete File`

## Credential

Create a **GitHub** credential in the [Credentials Tab](../tabs/credentials-tab.md) with:

- A personal access token
- Optional API base URL for GitHub Enterprise

Leave the base URL empty for GitHub.com. Fine-grained PATs are recommended.

If you use GitHub Enterprise Server and later edit the credential to rotate the token, re-enter the `base_url` when saving. The edit dialog masks the stored URL, and saving a new token without it removes the Enterprise endpoint from the credential.

## Common Fields

Most operations use:

- **Owner** – Repository owner, organization name, or username
- **Repository** – Repository name

`List Organization Repositories` only requires **Owner** (the organization name) and does not use the repository field.

`List User Repositories` only requires **Owner** (the username) and does not use the repository field.

Example:

- Owner: `heymrun`
- Repository: `heym`

## Issues

Issue operations support title/body fields and optional JSON-array fields for labels and assignees.

`List Issues` returns repository issues only. Pull requests are excluded; use `List Pull Requests` for PR results.

```json
["bug", "backend"]
```

```json
["octocat"]
```

### Update Issue field semantics

For `Update Issue`, only fields you explicitly set are sent to GitHub:

- **State** – Choose `Don't change`, `Open`, or `Closed`. Leave unset to keep the current state.
- **Title / Body** – Leave blank to keep the current value.
- **Labels / Assignees** – Leave the field empty to keep the current value. Use `[]` to clear all labels or assignees. Use a JSON array such as `["bug"]` to replace them.

`Update Issue` requires at least one field to change at runtime. If you only provide an issue number, execution fails with a validation error from the GitHub API layer.

## Lock Issue

`Lock Issue` accepts an optional **Lock reason**. When provided, it must be one of GitHub's supported values:

- `off-topic`
- `too heated`
- `resolved`
- `spam`

Leave the reason empty to lock without a specific reason.

## Pull Requests

Create PR requires:

- Title
- Head branch
- Base branch
- Optional body
- Optional draft mode

## Releases

| Operation | Required fields at runtime | Commonly optional |
|-----------|---------------------------|-------------------|
| `Create Release` | Tag name | Release name (title), body, target branch, draft, prerelease |
| `Update Release` | Release ID | Tag name, release name, body, target branch, draft, prerelease |
| `Get Release` / `Delete Release` | Release ID | — |

`Update Release` can explicitly set `draft` / `prerelease` to either `true` or `false`.

### Canvas validation notes

Before you run a workflow from the editor, Heym validates a few GitHub fields more strictly than the runtime API requires:

- `Create Release` – The canvas requires **Name / Title** even though GitHub only requires a tag name at runtime.
- `Update Release` – The canvas requires **Tag Name** even though runtime updates can change only the release ID, body, or draft flags.
- `List Files` – The canvas currently requires **Directory Path** even though an empty path lists the repository root at runtime.

If you hit one of these validation errors, fill the requested field or adjust the operation configuration before executing.

## Workflows

Workflow operations support:

- Listing repository workflows
- Getting a workflow by numeric ID or workflow file name
- Dispatching a workflow with a ref or branch plus optional JSON inputs object

## File Contents

`Get File` reads a repository file through GitHub's contents API and decodes text content when available. Binary files and non-UTF-8 content may return metadata without a decoded `content` field.

`List Files` returns directory entries from the repository contents API for a given folder path and optional ref. Leave **Directory Path** empty to list the repository root.

`Create or Update File` writes text content to a repository path using:

- File path
- Commit message
- File content
- Optional branch

`Delete File` removes a repository path using a commit message and optional branch. If the file exists, Heym fetches the current SHA automatically before deleting it.

If the file already exists, Heym fetches the current SHA automatically before updating it.

## Pagination

`List Issues`, `List Pull Requests`, `List Releases`, `List Workflows`, `List Organization Repositories`, and `List User Repositories` support **Per Page** (1–100). Heym requests a single page of results; there is no `page` parameter for fetching additional pages in the same operation.

## Output

The exact shape depends on the selected operation. Common fields include:

- `$github.success`
- `$github.operation`
- `$github.repository`
- `$github.issue`
- `$github.issues`
- `$github.pull_request`
- `$github.pull_requests`
- `$github.release`
- `$github.releases`
- `$github.workflow`
- `$github.workflows`
- `$github.file`
- `$github.items`
- `$github.path`
- `$github.sha`
- `$github.commit_sha`
- `$github.deleted`
- `$github.created`
- `$github.ref`
- `$github.inputs`

Replace `github` with your node label.

## Notes

- Labels and assignees must be valid JSON arrays when provided.
- Workflow dispatch inputs must be a valid JSON object when provided.
- `Update Issue` uses `state` only when you explicitly set it; leave it unset to keep the current issue state.
- GitHub API permissions depend on the token scopes or fine-grained repository permissions you grant.

## Related

- [Credentials Tab](../tabs/credentials-tab.md) – Add and manage GitHub credentials
- [Third-Party Integrations](../reference/integrations.md) – GitHub credential setup and Enterprise `base_url`
- [Agent Node](./agent-node.md) – Use GitHub credentials with `@modelcontextprotocol/server-github`
- [Node Types](../reference/node-types.md) – Full node catalog
