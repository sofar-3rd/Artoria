<!-- START AUTOMATED TOOLS -->
<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/workflow-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/workflow-light.png"><img src="pkg/octicons/icons/workflow-light.png" width="20" height="20" alt="workflow"></picture> Actions</summary>

- **actions_get** - Get details of GitHub Actions resources (workflows, workflow runs, jobs, and artifacts)
  - **OAuth Challenge Scopes**: `repo`
  - `method`: The method to execute (string, required)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)
  - `resource_id`: The unique identifier of the resource. This will vary based on the "method" provided, so ensure you provide the correct ID:
    - Provide a workflow ID or workflow file name (e.g. ci.yaml) for 'get_workflow' method.
    - Provide a workflow run ID for 'get_workflow_run', 'get_workflow_run_usage', and 'get_workflow_run_logs_url' methods.
    - Provide an artifact ID for 'download_workflow_run_artifact' method.
    - Provide a job ID for 'get_workflow_job' method.
     (string, required)

- **actions_list** - List GitHub Actions workflows in a repository
  - **OAuth Challenge Scopes**: `repo`
  - `method`: The action to perform (string, required)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (default: 1) (number, optional)
  - `perPage`: Results per page for pagination (default: 30, max: 100) (number, optional)
  - `repo`: Repository name (string, required)
  - `resource_id`: The unique identifier of the resource. This will vary based on the "method" provided, so ensure you provide the correct ID:
    - Do not provide any resource ID for 'list_workflows' method.
    - Provide a workflow ID or workflow file name (e.g. ci.yaml) for 'list_workflow_runs' method, or omit to list all workflow runs in the repository.
    - Provide a workflow run ID for 'list_workflow_jobs' and 'list_workflow_run_artifacts' methods.
     (string, optional)
  - `workflow_jobs_filter`: Filters for workflow jobs. **ONLY** used when method is 'list_workflow_jobs' (object, optional)
  - `workflow_runs_filter`: Filters for workflow runs. **ONLY** used when method is 'list_workflow_runs' (object, optional)

- **actions_run_trigger** - Trigger GitHub Actions workflow actions
  - **OAuth Challenge Scopes**: `repo`
  - `inputs`: Inputs the workflow accepts. Only used for 'run_workflow' method. (object, optional)
  - `method`: The method to execute (string, required)
  - `owner`: Repository owner (string, required)
  - `ref`: The git reference for the workflow. The reference can be a branch or tag name. Required for 'run_workflow' method. (string, optional)
  - `repo`: Repository name (string, required)
  - `run_id`: The ID of the workflow run. Required for all methods except 'run_workflow'. (number, optional)
  - `workflow_id`: The workflow ID (numeric) or workflow file name (e.g., main.yml, ci.yaml). Required for 'run_workflow' method. (string, optional)

- **get_job_logs** - Get GitHub Actions workflow job logs
  - **OAuth Challenge Scopes**: `repo`
  - `failed_only`: When true, gets logs for all failed jobs in the workflow run specified by run_id. Requires run_id to be provided. (boolean, optional)
  - `job_id`: The unique identifier of the workflow job. Required when getting logs for a single job. (number, optional)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)
  - `return_content`: Returns actual log content instead of URLs (boolean, optional)
  - `run_id`: The unique identifier of the workflow run. Required when failed_only is true to get logs for all failed jobs in the run. (number, optional)
  - `tail_lines`: Number of lines to return from the end of the log (number, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/code-square-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/code-square-light.png"><img src="pkg/octicons/icons/code-square-light.png" width="20" height="20" alt="code-square"></picture> Code Quality</summary>

- **get_code_quality_finding** - Get code quality finding
  - **OAuth Challenge Scopes**: `repo`
  - `findingNumber`: The number of the finding. (number, required)
  - `owner`: The owner of the repository. (string, required)
  - `repo`: The name of the repository. (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/codescan-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/codescan-light.png"><img src="pkg/octicons/icons/codescan-light.png" width="20" height="20" alt="codescan"></picture> Code Security</summary>

- **get_code_scanning_alert** - Get code scanning alert
  - **OAuth Challenge Scopes**: `security_events`
  - `alertNumber`: The number of the alert. (number, required)
  - `owner`: The owner of the repository. (string, required)
  - `repo`: The name of the repository. (string, required)

- **list_code_scanning_alerts** - List code scanning alerts
  - **OAuth Challenge Scopes**: `security_events`
  - `owner`: The owner of the repository. (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `ref`: The Git reference for the results you want to list. (string, optional)
  - `repo`: The name of the repository. (string, required)
  - `severity`: Filter code scanning alerts by severity (string, optional)
  - `state`: Filter code scanning alerts by state. Defaults to open (string, optional)
  - `tool_name`: The name of the tool used for code scanning. (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/person-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/person-light.png"><img src="pkg/octicons/icons/person-light.png" width="20" height="20" alt="person"></picture> Context</summary>

- **get_me** - Get my user profile
  - **MCP App UI**: `ui://github-mcp-server/get-me`
  - No parameters required

- **get_team_members** - Get team members
  - **OAuth Challenge Scopes**: `read:org`
  - `org`: Organization login (owner) that contains the team. (string, required)
  - `team_slug`: Team slug (string, required)

- **get_teams** - Get teams
  - **OAuth Challenge Scopes**: `read:org`
  - `user`: Username to get teams for. If not provided, uses the authenticated user. (string, optional)

- **ui_get** - Get UI data
  - **OAuth Challenge Scopes**: `repo`, `read:org`
  - `method`: The type of data to fetch (string, required)
  - `owner`: Repository owner (required for all methods) (string, required)
  - `repo`: Repository name (required for labels, assignees, milestones, branches, issue fields, reviewers) (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/copilot-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/copilot-light.png"><img src="pkg/octicons/icons/copilot-light.png" width="20" height="20" alt="copilot"></picture> Copilot</summary>

- **assign_copilot_to_issue** - Assign Copilot to issue
  - **OAuth Challenge Scopes**: `repo`
  - `base_ref`: Git reference (e.g., branch) that the agent will start its work from. If not specified, defaults to the repository's default branch (string, optional)
  - `custom_instructions`: Optional custom instructions to guide the agent beyond the issue body. Use this to provide additional context, constraints, or guidance that is not captured in the issue description (string, optional)
  - `issue_number`: Issue number (number, required)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **request_copilot_review** - Request Copilot review
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `pullNumber`: Pull request number (number, required)
  - `repo`: Repository name (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/copilot-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/copilot-light.png"><img src="pkg/octicons/icons/copilot-light.png" width="20" height="20" alt="copilot"></picture> Copilot Issue Intents</summary>

- **assign_copilot_to_issue_with_intent** - Assign Copilot to issue with intent
  - **OAuth Challenge Scopes**: `repo`
  - `base_ref`: Git reference (e.g., branch) that the agent will start its work from. If not specified, defaults to the repository's default branch. Ignored when is_suggestion is true (string, optional)
  - `confidence`: How confident you are in this choice. 'HIGH' for clear signal or explicit user request, 'MEDIUM' for reasonable inference with some ambiguity, 'LOW' for best guess with limited signal. (string, required)
  - `custom_instructions`: Optional custom instructions to guide the agent beyond the issue body. Ignored when is_suggestion is true (string, optional)
  - `is_suggestion`: If true, records a pending Copilot assignment intent rather than launching the agent. Approval later supplies the launch context; base_ref and custom_instructions are ignored in this case. (boolean, required)
  - `issue_number`: Issue number (number, required)
  - `owner`: Repository owner (string, required)
  - `rationale`: One concise sentence explaining what specifically about the issue led to choosing Copilot. State the concrete signal (e.g. 'Well-scoped task with clear acceptance criteria'). (string, required)
  - `repo`: Repository name (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/dependabot-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/dependabot-light.png"><img src="pkg/octicons/icons/dependabot-light.png" width="20" height="20" alt="dependabot"></picture> Dependabot</summary>

- **get_dependabot_alert** - Get dependabot alert
  - **OAuth Challenge Scopes**: `security_events`
  - `alertNumber`: The number of the alert. (number, required)
  - `owner`: The owner of the repository. (string, required)
  - `repo`: The name of the repository. (string, required)

- **list_dependabot_alerts** - List dependabot alerts
  - **OAuth Challenge Scopes**: `security_events`
  - `after`: Cursor for pagination. Use the cursor from the previous response. (string, optional)
  - `owner`: The owner of the repository. (string, required)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: The name of the repository. (string, required)
  - `severity`: Filter dependabot alerts by severity (string, optional)
  - `state`: Filter dependabot alerts by state. Defaults to open (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/comment-discussion-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/comment-discussion-light.png"><img src="pkg/octicons/icons/comment-discussion-light.png" width="20" height="20" alt="comment-discussion"></picture> Discussions</summary>

- **discussion_comment_write** - Manage discussion comments
  - **OAuth Challenge Scopes**: `repo`
  - `body`: Comment content (required for 'add', 'reply', and 'update' methods) (string, optional)
  - `commentNodeID`: The Node ID of the discussion comment (required for 'reply', 'update', 'delete', 'mark_answer', and 'unmark_answer' methods). For 'reply', this is the top-level comment to reply to; GitHub Discussions only support one level of nesting. (string, optional)
  - `discussionNumber`: Discussion number (required for 'add' and 'reply' methods) (number, optional)
  - `method`: Write operation to perform on a discussion comment.
    Options are:
    - 'add' - adds a new top-level comment to a discussion.
    - 'reply' - replies to a top-level discussion comment (GitHub Discussions only support one level of nesting).
    - 'update' - updates an existing discussion comment.
    - 'delete' - deletes a discussion comment.
    - 'mark_answer' - marks a discussion comment as the answer (Q&A only).
    - 'unmark_answer' - unmarks a discussion comment as the answer (Q&A only).
     (string, required)
  - `owner`: Repository owner (required for 'add' and 'reply' methods) (string, optional)
  - `repo`: Repository name (required for 'add' and 'reply' methods) (string, optional)

- **get_discussion** - Get discussion
  - **OAuth Challenge Scopes**: `repo`
  - `discussionNumber`: Discussion Number (number, required)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **get_discussion_comments** - Get discussion comments
  - **OAuth Challenge Scopes**: `repo`
  - `after`: Cursor for pagination. Use the cursor from the previous response. (string, optional)
  - `discussionNumber`: Discussion Number (number, required)
  - `includeReplies`: When true, each top-level comment will include its replies nested within it (up to 100 replies per comment, which is the GitHub API maximum). Defaults to false. (boolean, optional)
  - `owner`: Repository owner (string, required)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)

- **list_discussion_categories** - List discussion categories
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name. If not provided, discussion categories will be queried at the organisation level. (string, optional)

- **list_discussions** - List discussions
  - **OAuth Challenge Scopes**: `repo`
  - `after`: Cursor for pagination. Use the cursor from the previous response. (string, optional)
  - `category`: Optional filter by discussion category ID. If provided, only discussions with this category are listed. (string, optional)
  - `direction`: Order direction. (string, optional)
  - `orderBy`: Order discussions by field. If provided, the 'direction' also needs to be provided. (string, optional)
  - `owner`: Repository owner (string, required)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name. If not provided, discussions will be queried at the organisation level. (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/logo-gist-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/logo-gist-light.png"><img src="pkg/octicons/icons/logo-gist-light.png" width="20" height="20" alt="logo-gist"></picture> Gists</summary>

- **create_gist** - Create Gist
  - **OAuth Challenge Scopes**: `gist`
  - `content`: Content for simple single-file gist creation (string, required)
  - `description`: Description of the gist (string, optional)
  - `filename`: Filename for simple single-file gist creation (string, required)
  - `public`: Whether the gist is public (boolean, optional)

- **get_gist** - Get Gist Content
  - `gist_id`: The ID of the gist (string, required)

- **list_gists** - List Gists
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `since`: Only gists updated after this time (ISO 8601 timestamp) (string, optional)
  - `username`: GitHub username (omit for authenticated user's gists) (string, optional)

- **update_gist** - Update Gist
  - **OAuth Challenge Scopes**: `gist`
  - `content`: Content for the file (string, required)
  - `description`: Updated description of the gist (string, optional)
  - `filename`: Filename to update or create (string, required)
  - `gist_id`: ID of the gist to update (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/git-branch-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/git-branch-light.png"><img src="pkg/octicons/icons/git-branch-light.png" width="20" height="20" alt="git-branch"></picture> Git</summary>

- **get_repository_tree** - Get repository tree
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (username or organization) (string, required)
  - `path_filter`: Optional path prefix to filter the tree results (e.g., 'src/' to only show files in the src directory) (string, optional)
  - `recursive`: Setting this parameter to true returns the objects or subtrees referenced by the tree. Default is false (boolean, optional)
  - `repo`: Repository name (string, required)
  - `tree_sha`: The SHA1 value or ref (branch or tag) name of the tree. Defaults to the repository's default branch (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/law-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/law-light.png"><img src="pkg/octicons/icons/law-light.png" width="20" height="20" alt="law"></picture> Governance</summary>

- **create_repository_ruleset** - Create repository ruleset
  - **OAuth Challenge Scopes**: `repo`, `admin:org`, `admin:enterprise`
  - `bypass_actors`: The actors that can bypass the rules in this ruleset (object[], optional)
  - `conditions`: Conditions for when this ruleset applies, e.g. {"ref_name": {"include": ["refs/heads/main"], "exclude": []}} (object, optional)
  - `enforcement`: The enforcement level of the ruleset. 'evaluate' allows admins to test rules before enforcing them (string, required)
  - `enterprise`: Enterprise slug. Required when level is 'enterprise'. (string, optional)
  - `level`: The level at which the ruleset is configured:
    - 'repository': A ruleset on a single repository (requires 'owner' and 'repo').
    - 'organization': A ruleset covering repositories in an organization (requires 'org').
    - 'enterprise': A ruleset covering repositories across an enterprise (requires 'enterprise'). (string, required)
  - `name`: The name of the ruleset (string, required)
  - `org`: Organization name. Required when level is 'organization'. (string, optional)
  - `owner`: Repository owner. Required when level is 'repository'. (string, optional)
  - `repo`: Repository name. Required when level is 'repository'. (string, optional)
  - `rules`: An array of rules within the ruleset. Each rule is an object with a 'type' (e.g. 'creation', 'deletion', 'non_fast_forward', 'required_signatures', 'pull_request', 'required_status_checks') and, for rules that need configuration, a 'parameters' object (object[], required)
  - `target`: The target of the ruleset. Defaults to 'branch'. 'repository' is only valid for 'organization' and 'enterprise' level rulesets. (string, optional)

- **custom_properties_read** - Read custom properties
  - **OAuth Challenge Scopes**: `repo`, `read:org`, `read:enterprise`
  - `enterprise`: Enterprise slug. Required when level is 'enterprise'. (string, optional)
  - `level`: The level at which custom properties are managed:
    - 'repository': The custom property VALUES assigned to a repository (requires 'owner' and 'repo').
    - 'organization': The custom property DEFINITIONS (schema) for an organization (requires 'org').
    - 'enterprise': The custom property DEFINITIONS (schema) for an enterprise (requires 'enterprise'). (string, required)
  - `org`: Organization name. Required when level is 'organization'. (string, optional)
  - `owner`: Repository owner. Required when level is 'repository'. (string, optional)
  - `repo`: Repository name. Required when level is 'repository'. (string, optional)

- **custom_properties_write** - Set custom properties
  - **OAuth Challenge Scopes**: `repo`, `admin:org`, `admin:enterprise`
  - `enterprise`: Enterprise slug. Required when level is 'enterprise'. (string, optional)
  - `level`: The level at which custom properties are managed:
    - 'repository': The custom property VALUES assigned to a repository (requires 'owner' and 'repo').
    - 'organization': The custom property DEFINITIONS (schema) for an organization (requires 'org').
    - 'enterprise': The custom property DEFINITIONS (schema) for an enterprise (requires 'enterprise'). (string, required)
  - `org`: Organization name. Required when level is 'organization'. (string, optional)
  - `owner`: Repository owner. Required when level is 'repository'. (string, optional)
  - `properties`: The custom properties to create or update. At the repository level each item assigns a value ('property_name' and 'value'); at the organization and enterprise levels each item defines the schema ('property_name' and 'value_type', plus optional definition fields). (object[], required)
  - `repo`: Repository name. Required when level is 'repository'. (string, optional)

- **repository_ruleset_read** - Read repository rulesets
  - **OAuth Challenge Scopes**: `repo`, `read:org`, `read:enterprise`
  - `actor_name`: The handle for the GitHub user account to filter rule suites on. Used by the 'list_rule_suites' method. (string, optional)
  - `branch`: Branch name. Required for the 'get_rules_for_branch' method. (string, optional)
  - `enterprise`: Enterprise slug. Required when level is 'enterprise'. (string, optional)
  - `evaluate_status`: Filter rule suites by ruleset evaluation mode. Used by the 'list_rule_suites' method. (string, optional)
  - `includes_parents`: Include rulesets configured at higher levels that also apply. Defaults to true. Used by the 'get' and 'list' methods at the repository level. (boolean, optional)
  - `level`: The level at which the ruleset is configured:
    - 'repository': A ruleset on a single repository (requires 'owner' and 'repo').
    - 'organization': A ruleset covering repositories in an organization (requires 'org').
    - 'enterprise': A ruleset covering repositories across an enterprise (requires 'enterprise'). (string, required)
  - `method`: Operation to perform:
    - 'get': Get a specific ruleset by ID (requires 'ruleset_id'). Supported at every level.
    - 'list': List all rulesets. Supported at every level.
    - 'get_rules_for_branch': Get all rules that apply to a branch (requires 'branch'). Repository level only.
    - 'list_rule_suites': List rule suites, the evaluations of rules against pushes. Repository and organization levels only.
    - 'get_rule_suite': Get a specific rule suite by ID (requires 'rule_suite_id'). Repository and organization levels only. (string, required)
  - `org`: Organization name. Required when level is 'organization'. (string, optional)
  - `owner`: Repository owner. Required when level is 'repository'. (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `ref`: The name of the ref (branch, tag, etc.) to filter rule suites by. Used by the 'list_rule_suites' method. (string, optional)
  - `repo`: Repository name. Required when level is 'repository'. (string, optional)
  - `repository_name`: Repository name to filter rule suites by. Used by the 'list_rule_suites' method at the organization level. (string, optional)
  - `rule_suite_id`: Rule suite ID. Required for the 'get_rule_suite' method. (number, optional)
  - `rule_suite_result`: The rule suite result to filter by. Used by the 'list_rule_suites' method. (string, optional)
  - `ruleset_id`: Ruleset ID. Required for the 'get' method. (number, optional)
  - `time_period`: The time period to filter rule suites by. Used by the 'list_rule_suites' method. (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/issue-opened-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/issue-opened-light.png"><img src="pkg/octicons/icons/issue-opened-light.png" width="20" height="20" alt="issue-opened"></picture> Issues</summary>

- **add_issue_comment** - Add comment to issue or pull request
  - **OAuth Challenge Scopes**: `repo`
  - `body`: Comment content. Required unless reaction is provided. (string, optional)
  - `comment_id`: The numeric ID of the issue or pull request comment to react to. Use this for reactions to comments; omit it to react to the issue or pull request itself. Cannot be combined with body. (integer, optional)
  - `issue_number`: Issue or pull request number to comment on or react to. (number, required)
  - `owner`: Repository owner (string, required)
  - `reaction`: Emoji reaction to add. Required unless body is provided. (string, optional)
  - `repo`: Repository name (string, required)

- **get_label** - Get a specific label from a repository
  - **OAuth Challenge Scopes**: `repo`
  - `name`: Label name. (string, required)
  - `owner`: Repository owner (username or organization name) (string, required)
  - `repo`: Repository name (string, required)

- **issue_read** - Get issue details
  - **OAuth Challenge Scopes**: `repo`
  - `issue_number`: The number of the issue (number, required)
  - `method`: The read operation to perform on a single issue.
    Options are:
    1. get - Get issue details. Also returns best-effort hierarchy flags (`has_parent`, `has_children`); `parent` and `sub_issues_summary` are optional relationship summaries, and `closed_by_pull_requests` summarizes the pull requests configured to close the issue as `total_count` plus up to 5 `references`.
    2. get_comments - Get issue comments.
    3. get_sub_issues - Get sub-issues (children) of the issue.
    4. get_parent - Get the parent issue, if this issue is a sub-issue of another.
    5. get_labels - Get labels assigned to the issue.
     (string, required)
  - `owner`: The owner of the repository (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: The name of the repository (string, required)

- **issue_write** - Create or update issue/pull request
  - **OAuth Challenge Scopes**: `repo`
  - **MCP App UI**: `ui://github-mcp-server/issue-write`
  - `assignees`: Usernames to assign to this issue (string[], optional)
  - `body`: Issue body content (string, optional)
  - `duplicate_of`: Issue number that this issue is a duplicate of. Required when state_reason is 'duplicate'. (number, optional)
  - `issue_fields`: Issue field values to set or clear. Each item requires 'field_name' and exactly one of 'value', 'field_option_name', or 'delete: true'. (object[], optional)
  - `issue_number`: Issue number to update (number, optional)
  - `labels`: Labels to apply to this issue (string[], optional)
  - `method`: Write operation to perform on a single issue.
    Options are:
    - 'create' - creates a new issue.
    - 'update' - updates an existing issue.
     (string, required)
  - `milestone`: Milestone number (number, optional)
  - `owner`: Repository owner (string, required)
  - `parent_issue_number`: Issue number of the parent issue. Only used when method is 'create' and cannot be combined with issue_fields. The new issue is created and attached to this parent in the same operation. (number, optional)
  - `parent_owner`: Repository owner of the parent issue. Must be provided with parent_repo. Omit both to use owner and repo. Only used when method is 'create' and parent_issue_number is provided. (string, optional)
  - `parent_repo`: Repository name of the parent issue. Must be provided with parent_owner. Omit both to use owner and repo. Only used when method is 'create' and parent_issue_number is provided. (string, optional)
  - `repo`: Repository name (string, required)
  - `state`: New state (string, optional)
  - `state_reason`: Reason for the state change. Ignored unless state is changed. (string, optional)
  - `title`: Issue title (string, optional)
  - `type`: Type of this issue. For updates, pass null to remove the current type. Only use if issue types are enabled for this repository. Use list_issue_types to get valid type values for this repository or its owner organization. If the repository doesn't support issue types, omit this parameter. (string | null, optional)

- **list_issue_fields** - List issue fields
  - **OAuth Challenge Scopes**: `repo`, `read:org`
  - `owner`: The account owner of the repository or organization. The name is not case sensitive. (string, required)
  - `repo`: The name of the repository. When provided, returns fields for this specific repository (inherited from its organization). When omitted, returns org-level fields directly. (string, optional)

- **list_issue_types** - List available issue types
  - **OAuth Challenge Scopes**: `repo`, `read:org`
  - `owner`: The account owner of the repository or organization. (string, required)
  - `repo`: The name of the repository. When provided, returns issue types for this specific repository. When omitted, returns org-level issue types directly. (string, optional)

- **list_issues** - List issues
  - **OAuth Challenge Scopes**: `repo`
  - `after`: Cursor for pagination. Use the cursor from the previous response. (string, optional)
  - `direction`: Order direction. If provided, the 'orderBy' also needs to be provided. (string, optional)
  - `field_filters`: Filter by custom issue field values. Each entry takes a field_name and a value; the server looks up the field and coerces the value to its type (single-select option name, text, number, or YYYY-MM-DD date). (object[], optional)
  - `fields`: Subset of fields to return for each issue. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields; omitting 'body' and 'field_values' in particular drops the largest per-result data. (string[], optional)
  - `labels`: Filter by labels (string[], optional)
  - `orderBy`: Order issues by field. If provided, the 'direction' also needs to be provided. (string, optional)
  - `owner`: Repository owner (string, required)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)
  - `since`: Filter by date (ISO 8601 timestamp) (string, optional)
  - `state`: Filter by state, by default both open and closed issues are returned when not provided (string, optional)

- **search_issues** - Search issues
  - **OAuth Challenge Scopes**: `repo`
  - `fields`: Subset of fields to return for each issue result. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields; omitting 'body', 'reactions', and 'labels' in particular drops the largest per-result data. (string[], optional)
  - `order`: Sort order (string, optional)
  - `owner`: Optional repository owner. If provided with repo, only issues for this repository are listed. (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: The search query, as natural language. When the user gives alternative wordings, include them as plain words rather than joining them with OR. (string, required)
  - `repo`: Optional repository name. If provided with owner, only issues for this repository are listed. (string, optional)
  - `sort`: Sort field by number of matches of categories, defaults to best match (string, optional)

- **sub_issue_write** - Change sub-issue
  - **OAuth Challenge Scopes**: `repo`
  - `after_id`: The ID of the sub-issue to be prioritized after (either after_id OR before_id should be specified) (number, optional)
  - `before_id`: The ID of the sub-issue to be prioritized before (either after_id OR before_id should be specified) (number, optional)
  - `issue_number`: The number of the parent issue (number, required)
  - `method`: The action to perform on a single sub-issue
    Options are:
    - 'add' - add a sub-issue to a parent issue in a GitHub repository.
    - 'remove' - remove a sub-issue from a parent issue in a GitHub repository.
    - 'reprioritize' - change the order of sub-issues within a parent issue in a GitHub repository. Use either 'after_id' or 'before_id' to specify the new position.
    Writes issue hierarchy. To move a sub-issue to a new parent, use `add` with `replace_parent=true`; there is no writable parent field.
     (string, required)
  - `owner`: Repository owner (string, required)
  - `replace_parent`: When true, replaces the sub-issue's current parent issue. Use with 'add' method only. (boolean, optional)
  - `repo`: Repository name (string, required)
  - `sub_issue_id`: The ID of the sub-issue to add. ID is not the same as issue number (number, required)

- **update_issue_comment** - Update issue comment
  - **OAuth Challenge Scopes**: `repo`
  - `body`: New comment content (string, required)
  - `comment_id`: The numeric ID of the issue or pull request conversation comment to update. Do not use a pull request review comment ID. (integer, required)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/tag-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/tag-light.png"><img src="pkg/octicons/icons/tag-light.png" width="20" height="20" alt="tag"></picture> Labels</summary>

- **get_label** - Get a specific label from a repository
  - **OAuth Challenge Scopes**: `repo`
  - `name`: Label name. (string, required)
  - `owner`: Repository owner (username or organization name) (string, required)
  - `repo`: Repository name (string, required)

- **label_write** - Write operations on repository labels
  - **OAuth Challenge Scopes**: `repo`
  - `color`: Label color as 6-character hex code without '#' prefix (e.g., 'f29513'). Required for 'create', optional for 'update'. (string, optional)
  - `description`: Label description text. Optional for 'create' and 'update'. (string, optional)
  - `method`: Operation to perform: 'create', 'update', or 'delete' (string, required)
  - `name`: Label name - required for all operations (string, required)
  - `new_name`: New name for the label (used only with 'update' method to rename) (string, optional)
  - `owner`: Repository owner (username or organization name) (string, required)
  - `repo`: Repository name (string, required)

- **list_label** - List labels from a repository
  - **OAuth Challenge Scopes**: `repo`
  - `after`: Cursor for pagination. Use the cursor from the previous response. (string, optional)
  - `owner`: Repository owner (username or organization name) - required for all operations (string, required)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name - required for all operations (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/bell-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/bell-light.png"><img src="pkg/octicons/icons/bell-light.png" width="20" height="20" alt="bell"></picture> Notifications</summary>

- **dismiss_notification** - Dismiss notification
  - **OAuth Challenge Scopes**: `notifications`
  - `state`: The new state of the notification (read/done) (string, required)
  - `threadID`: The ID of the notification thread (string, required)

- **get_notification_details** - Get notification details
  - **OAuth Challenge Scopes**: `notifications`
  - `notificationID`: The ID of the notification (string, required)

- **list_notifications** - List notifications
  - **OAuth Challenge Scopes**: `notifications`
  - `before`: Only show notifications updated before the given time (ISO 8601 format) (string, optional)
  - `filter`: Filter notifications to, use default unless specified. Read notifications are ones that have already been acknowledged by the user. Participating notifications are those that the user is directly involved in, such as issues or pull requests they have commented on or created. (string, optional)
  - `owner`: Optional repository owner. If provided with repo, only notifications for this repository are listed. (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Optional repository name. If provided with owner, only notifications for this repository are listed. (string, optional)
  - `since`: Only show notifications updated after the given time (ISO 8601 format) (string, optional)

- **manage_notification_subscription** - Manage notification subscription
  - **OAuth Challenge Scopes**: `notifications`
  - `action`: Action to perform: ignore, watch, or delete the notification subscription. (string, required)
  - `notificationID`: The ID of the notification thread. (string, required)

- **manage_repository_notification_subscription** - Manage repository notification subscription
  - **OAuth Challenge Scopes**: `notifications`
  - `action`: Action to perform: ignore, watch, or delete the repository notification subscription. (string, required)
  - `owner`: The account owner of the repository. (string, required)
  - `repo`: The name of the repository. (string, required)

- **mark_all_notifications_read** - Mark all notifications as read
  - **OAuth Challenge Scopes**: `notifications`
  - `lastReadAt`: Describes the last point that notifications were checked (optional). Default: Now (string, optional)
  - `owner`: Optional repository owner. If provided with repo, only notifications for this repository are marked as read. (string, optional)
  - `repo`: Optional repository name. If provided with owner, only notifications for this repository are marked as read. (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/organization-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/organization-light.png"><img src="pkg/octicons/icons/organization-light.png" width="20" height="20" alt="organization"></picture> Organizations</summary>

- **search_orgs** - Search organizations
  - **OAuth Challenge Scopes**: `read:org`
  - `order`: Sort order (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: Organization search query. Examples: 'microsoft', 'location:california', 'created:>=2025-01-01'. Search is automatically scoped to type:org. (string, required)
  - `sort`: Sort field by category (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/project-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/project-light.png"><img src="pkg/octicons/icons/project-light.png" width="20" height="20" alt="project"></picture> Projects</summary>

- **projects_get** - Get details of GitHub Projects resources
  - **OAuth Challenge Scopes**: `read:project`
  - `field_id`: The field's ID. Required for 'get_project_field' method. (number, optional)
  - `field_names`: Specific list of field names to include in the response when getting a project item (e.g. ["Status", "Priority"]). Resolved server-side to field IDs — pass this instead of 'fields' when you only know the human-readable names. Mutually exclusive with 'fields' — provide one, not both. Only used for 'get_project_item' method. (string[], optional)
  - `fields`: Specific list of field IDs to include in the response when getting a project item (e.g. ["102589", "985201", "169875"]). If neither 'fields' nor 'field_names' is provided, only the title field is included. Mutually exclusive with 'field_names' — provide one, not both. Only used for 'get_project_item' method. (string[], optional)
  - `item_id`: The item's ID. Required for 'get_project_item' method. (number, optional)
  - `method`: The method to execute (string, required)
  - `owner`: The owner (user or organization login). The name is not case sensitive. (string, optional)
  - `owner_type`: Owner type (user or org). If not provided, will be automatically detected. (string, optional)
  - `project_number`: The project's number. (number, optional)
  - `status_update_id`: The node ID of the project status update. Required for 'get_project_status_update' method. (string, optional)
  - `view_id`: The node ID of the project view. Required for 'get_project_view' method. (string, optional)

- **projects_list** - List GitHub Projects resources
  - **OAuth Challenge Scopes**: `read:project`
  - `after`: Forward pagination cursor from previous pageInfo.nextCursor. (string, optional)
  - `before`: Backward pagination cursor from previous pageInfo.prevCursor (rare). (string, optional)
  - `field_names`: Field names to include when listing project items (e.g. ["Status", "Priority"]). Resolved server-side to field IDs — pass this instead of 'fields' when you only know the human-readable names. Names that fail to resolve return a structured error. Mutually exclusive with 'fields' — provide one, not both. Only used for 'list_project_items' method. (string[], optional)
  - `fields`: Field IDs to include when listing project items (e.g. ["102589", "985201"]). CRITICAL: Always provide to get field values. Without this (and without 'field_names'), only titles returned. Mutually exclusive with 'field_names' — provide one, not both. Only used for 'list_project_items' method. (string[], optional)
  - `method`: The action to perform (string, required)
  - `owner`: The owner (user or organization login). The name is not case sensitive. (string, required)
  - `owner_type`: Owner type (user or org). If not provided, will automatically try both. (string, optional)
  - `perPage`: Results per page (max 50) (number, optional)
  - `project_number`: The project's number. Required for 'list_project_fields', 'list_project_items', 'list_project_views', and 'list_project_status_updates' methods. (number, optional)
  - `query`: Filter/query string. For list_projects: filter by title text and state (e.g. "roadmap is:open"). For list_project_items: advanced filtering using GitHub's project filtering syntax. (string, optional)

- **projects_write** - Manage GitHub Projects
  - **OAuth Challenge Scopes**: `project`
  - `body`: The body of the status update (markdown). Used for 'create_project_status_update' method. (string, optional)
  - `field_name`: The name of the iteration field (e.g. 'Sprint'). Required for 'create_iteration_field' method. (string, optional)
  - `filter`: Saved view filter; omit on update to preserve it, or pass null to clear it. (string | null, optional)
  - `issue_number`: The issue number. Required for 'add_project_item' when item_type is 'issue'. Also accepted by 'update_project_item' to resolve the item by issue number (combine with item_owner and item_repo). (number, optional)
  - `item_id`: The project item ID. Required for 'delete_project_item'. For 'update_project_item', provide either item_id, or (item_owner + item_repo + issue_number) to resolve the item by issue. (number, optional)
  - `item_owner`: The owner (user or organization) of the repository containing the issue or pull request. Required for 'add_project_item' method. Also accepted by 'update_project_item' when resolving the item by issue number. (string, optional)
  - `item_repo`: The name of the repository containing the issue or pull request. Required for 'add_project_item' method. Also accepted by 'update_project_item' when resolving the item by issue number. (string, optional)
  - `item_type`: The item's type, either issue or pull_request. Required for 'add_project_item' method. (string, optional)
  - `items`: The items to update with the top-level 'updated_field'. Required for 'update_project_items'; prefer it over calling 'update_project_item' in a loop. Each entry must match exactly one reference variant: 'node_id', numeric 'item_id', or 'item_owner' + 'item_repo' + 'issue_number'. Limit: 50 items per call. (object[], optional)
  - `iteration_duration`: Duration in days for iterations of the field (e.g. 7 for weekly, 14 for bi-weekly). Required for 'create_iteration_field' method. (number, optional)
  - `iterations`: Custom iterations for 'create_iteration_field' method. Only set this when you need iterations with varying durations, breaks between them, or specific titles. Otherwise omit it: GitHub auto-creates three iterations of 'iteration_duration' days starting on 'start_date', which is the right choice for most cases. (object[], optional)
  - `layout`: View layout; required when creating a view. (string, optional)
  - `method`: The method to execute (string, required)
  - `name`: View name; required when creating a view. (string, optional)
  - `owner`: The project owner (user or organization login). The name is not case sensitive. (string, required)
  - `owner_type`: Owner type (user or org). Required for 'create_project' method. If not provided for other methods, will be automatically detected. (string, optional)
  - `project_number`: The project's number. Required for all methods except 'create_project'. (number, optional)
  - `pull_request_number`: The pull request number (use when item_type is 'pull_request' for 'add_project_item' method). Provide either issue_number or pull_request_number. (number, optional)
  - `start_date`: Start date in YYYY-MM-DD format. Used for 'create_project_status_update' and 'create_iteration_field' methods. (string, optional)
  - `status`: The status of the project. Used for 'create_project_status_update' method. (string, optional)
  - `target_date`: The target date of the status update in YYYY-MM-DD format. Used for 'create_project_status_update' method. (string, optional)
  - `title`: The project title. Required for 'create_project' method. (string, optional)
  - `updated_field`: The field/value to apply, using {"id": 123, "value": ...} or {"name": "Status", "value": ...}; null clears the field. Required for 'update_project_item' and 'update_project_items', where one top-level field/value applies to every item in a batch. For 'update_project_item' SINGLE_SELECT fields, the name form accepts option names; the ID form expects an option ID. (object, optional)
  - `view_id`: Project view node ID for update or delete; must belong to owner/project_number. (string, optional)
  - `visible_field_names`: Ordered project field names to show on create or replace on update; omit on update to preserve, or pass [] to reset. Mutually exclusive with visible_fields. Roadmap accepts only []. (string[], optional)
  - `visible_fields`: Ordered project field database IDs to show on create or replace on update; omit on update to preserve, or pass [] to reset. Mutually exclusive with visible_field_names. Roadmap accepts only []. (string[], optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/git-pull-request-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/git-pull-request-light.png"><img src="pkg/octicons/icons/git-pull-request-light.png" width="20" height="20" alt="git-pull-request"></picture> Pull Requests</summary>

- **add_comment_to_pending_review** - Add review comment to the requester's latest pending pull request review
  - **OAuth Challenge Scopes**: `repo`
  - `body`: The text of the review comment (string, required)
  - `line`: The line of the blob in the pull request diff that the comment applies to. For multi-line comments, the last line of the range (number, optional)
  - `owner`: Repository owner (string, required)
  - `path`: The relative path to the file that necessitates a comment (string, required)
  - `pullNumber`: Pull request number (number, required)
  - `repo`: Repository name (string, required)
  - `side`: The side of the diff to comment on. LEFT indicates the previous state, RIGHT indicates the new state (string, optional)
  - `startLine`: For multi-line comments, the first line of the range that the comment applies to (number, optional)
  - `startSide`: For multi-line comments, the starting side of the diff that the comment applies to. LEFT indicates the previous state, RIGHT indicates the new state (string, optional)
  - `subjectType`: The level at which the comment is targeted (string, required)

- **add_reply_to_pull_request_comment** - Add reply to pull request comment
  - **OAuth Challenge Scopes**: `repo`
  - `body`: The text of the reply. Required unless reaction is provided. (string, optional)
  - `commentId`: The numeric ID of the pull request review comment to reply or react to. Use the number from a #discussion_r... anchor, not the GraphQL thread node ID (PRRT_...). (number, required)
  - `owner`: Repository owner (string, required)
  - `pullNumber`: Pull request number. Required when body is provided. (number, optional)
  - `reaction`: Emoji reaction to add. Required unless body is provided. (string, optional)
  - `repo`: Repository name (string, required)

- **create_pull_request** - Open new pull request
  - **OAuth Challenge Scopes**: `repo`
  - **MCP App UI**: `ui://github-mcp-server/pr-write`
  - `base`: Branch to merge into (string, required)
  - `body`: PR description (string, optional)
  - `draft`: Create as draft PR (boolean, optional)
  - `head`: Branch containing changes (string, required)
  - `maintainer_can_modify`: Allow maintainer edits (boolean, optional)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)
  - `reviewers`: GitHub usernames or ORG/team-slug team reviewers to request reviews from (string[], optional)
  - `title`: PR title (string, required)

- **list_pull_requests** - List pull requests
  - **OAuth Challenge Scopes**: `repo`
  - `base`: Filter by base branch (string, optional)
  - `direction`: Sort direction (string, optional)
  - `fields`: Subset of fields to return for each pull request. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields; omitting 'body' in particular drops the largest per-result data. (string[], optional)
  - `head`: Filter by head user/org and branch (string, optional)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)
  - `sort`: Sort by (string, optional)
  - `state`: Filter by state (string, optional)

- **merge_pull_request** - Merge pull request
  - **OAuth Challenge Scopes**: `repo`
  - `commit_message`: Extra detail for merge commit (string, optional)
  - `commit_title`: Title for merge commit (string, optional)
  - `expectedHeadSha`: The expected SHA of the pull request's HEAD ref (string, optional)
  - `merge_method`: Merge method (string, optional)
  - `owner`: Repository owner (string, required)
  - `pullNumber`: Pull request number (number, required)
  - `repo`: Repository name (string, required)

- **pull_request_read** - Get details for a single pull request
  - **OAuth Challenge Scopes**: `repo`
  - `after`: Cursor for pagination, used only by the get_review_comments method. Pass the endCursor from the previous page's PageInfo to fetch the next page. (string, optional)
  - `method`: Action to specify what pull request data needs to be retrieved from GitHub. 
    Possible options: 
     1. get - Get details of a specific pull request.
     2. get_diff - Get the diff of a pull request.
     3. get_status - Get combined commit status of a head commit in a pull request.
     4. get_files - Get the list of files changed in a pull request. Use with pagination parameters to control the number of results returned.
     5. get_commits - Get the list of commits on a pull request. Use with pagination parameters to control the number of results returned.
     6. get_review_comments - Get review threads on a pull request. Each thread contains logically grouped review comments made on the same code location during pull request reviews. Returns thread metadata and comments with nullable current and original line-range coordinates (line, start_line, original_line, original_start_line). Current coordinates are omitted when unavailable, such as for outdated comments. Use cursor-based pagination (perPage, after) to control results.
     7. get_reviews - Get the reviews on a pull request. When asked for review comments, use get_review_comments method. Use with pagination parameters to control the number of results returned.
     8. get_comments - Get comments on a pull request. Use this if user doesn't specifically want review comments. Use with pagination parameters to control the number of results returned.
     9. get_check_runs - Get check runs for the head commit of a pull request. Check runs are the individual CI/CD jobs and checks that run on the PR.
     (string, required)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `pullNumber`: Pull request number (number, required)
  - `repo`: Repository name (string, required)

- **pull_request_review_write** - Write operations (create, submit, delete) on pull request reviews
  - **OAuth Challenge Scopes**: `repo`
  - `body`: Review comment text (string, optional)
  - `commitID`: SHA of commit to review (string, optional)
  - `event`: Review action to perform. (string, optional)
  - `method`: The write operation to perform on pull request review. (string, required)
  - `owner`: Repository owner (string, required)
  - `pullNumber`: Pull request number (number, required)
  - `repo`: Repository name (string, required)
  - `threadId`: The node ID of the review thread (e.g., PRRT_kwDOxxx). Required for resolve_thread and unresolve_thread methods. Get thread IDs from pull_request_read with method get_review_comments. (string, optional)

- **search_pull_requests** - Search pull requests
  - **OAuth Challenge Scopes**: `repo`
  - `fields`: Subset of fields to return for each pull request result. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields; omitting 'body', 'reactions', and 'labels' in particular drops the largest per-result data. (string[], optional)
  - `order`: Sort order (string, optional)
  - `owner`: Optional repository owner. If provided with repo, only pull requests for this repository are listed. (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: Search query using GitHub pull request search syntax (string, required)
  - `repo`: Optional repository name. If provided with owner, only pull requests for this repository are listed. (string, optional)
  - `sort`: Sort field by number of matches of categories, defaults to best match (string, optional)

- **update_pull_request** - Edit pull request
  - **OAuth Challenge Scopes**: `repo`
  - **MCP App UI**: `ui://github-mcp-server/pr-edit`
  - `base`: New base branch name (string, optional)
  - `body`: New description (string, optional)
  - `draft`: Mark pull request as draft (true) or ready for review (false) (boolean, optional)
  - `maintainer_can_modify`: Allow maintainer edits (boolean, optional)
  - `owner`: Repository owner (string, required)
  - `pullNumber`: Pull request number to update (number, required)
  - `repo`: Repository name (string, required)
  - `reviewers`: GitHub usernames or ORG/team-slug team reviewers to request reviews from (string[], optional)
  - `state`: New state (string, optional)
  - `title`: New title (string, optional)

- **update_pull_request_branch** - Update pull request branch
  - **OAuth Challenge Scopes**: `repo`
  - `expectedHeadSha`: The expected SHA of the pull request's HEAD ref (string, optional)
  - `owner`: Repository owner (string, required)
  - `pullNumber`: Pull request number (number, required)
  - `repo`: Repository name (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/repo-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/repo-light.png"><img src="pkg/octicons/icons/repo-light.png" width="20" height="20" alt="repo"></picture> Repositories</summary>

- **create_branch** - Create branch
  - **OAuth Challenge Scopes**: `repo`
  - `branch`: Name for new branch (string, required)
  - `from_branch`: Source branch (defaults to repo default) (string, optional)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **create_or_update_file** - Create or update file
  - **OAuth Challenge Scopes**: `repo`, `workflow`
  - `allow_symlink_write`: Set true to update a symbolic link itself; content must be its new target path. (boolean, optional)
  - `branch`: Branch to create/update the file in (string, required)
  - `content`: Content of the file, exactly as it should appear once written. Do not base64-encode it; this server does that before calling the REST API. (string, required)
  - `message`: Commit message (string, required)
  - `owner`: Repository owner (username or organization) (string, required)
  - `path`: Path where to create/update the file (string, required)
  - `repo`: Repository name (string, required)
  - `sha`: The blob SHA of the file being replaced. Required if the file already exists. Retrieve it with get_file_contents using the same owner, repo, and path, with ref set to this tool's branch value. (string, optional)

- **create_repository** - Create repository
  - **OAuth Challenge Scopes**: `repo`
  - `autoInit`: Initialize with README (boolean, optional)
  - `description`: Repository description (string, optional)
  - `name`: Repository name (string, required)
  - `organization`: Organization to create the repository in (omit to create in your personal account) (string, optional)
  - `private`: Whether the repository should be private. Defaults to true (private) when omitted. (boolean, optional)

- **delete_file** - Delete file
  - **OAuth Challenge Scopes**: `repo`, `workflow`
  - `branch`: Branch to delete the file from (string, required)
  - `message`: Commit message (string, required)
  - `owner`: Repository owner (username or organization) (string, required)
  - `path`: Path to the file to delete (string, required)
  - `repo`: Repository name (string, required)

- **delete_repository** - Delete repository
  - **OAuth Challenge Scopes**: `delete_repo`, `repo`
  - `owner`: Repository owner (username or organization) (string, required)
  - `repo`: Repository name (string, required)

- **fork_repository** - Fork repository
  - **OAuth Challenge Scopes**: `repo`
  - `organization`: Organization to fork to (string, optional)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **get_commit** - Get commit details
  - **OAuth Challenge Scopes**: `repo`
  - `detail`: Level of detail to include for changed files. "none" omits stats and files entirely. "stats" (default) includes per-file metadata: filename, status, and lines-of-code counts (additions, deletions, changes), with no patch content. "full_patch" additionally includes the unified diff content for each file and can be very large. (string, optional)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)
  - `sha`: Commit SHA, branch name, or tag name (string, required)

- **get_file_contents** - Get file or directory contents
  - **OAuth Challenge Scopes**: `repo`
  - `fields`: Subset of fields to return for each entry when the path is a directory. If omitted, all fields are returned. Ignored when the path is a single file. Use this to reduce response size when listing directories and you only need specific fields, e.g. just 'name' and 'type'. (string[], optional)
  - `owner`: Repository owner (username or organization) (string, required)
  - `path`: Path to file/directory (string, optional)
  - `ref`: Accepts optional git refs such as `refs/tags/{tag}`, `refs/heads/{branch}` or `refs/pull/{pr_number}/head` (string, optional)
  - `repo`: Repository name (string, required)
  - `sha`: Accepts optional commit SHA. If specified, it will be used instead of ref (string, optional)

- **get_latest_release** - Get latest release
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **get_release_by_tag** - Get a release by tag name
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)
  - `tag`: Tag name (e.g., 'v1.0.0') (string, required)

- **get_tag** - Get tag details
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)
  - `tag`: Tag name (string, required)

- **list_branches** - List branches
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)

- **list_commits** - List commits
  - **OAuth Challenge Scopes**: `repo`
  - `author`: Author username or email address to filter commits by (string, optional)
  - `fields`: Subset of fields to return for each commit. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields, e.g. just 'sha' and 'html_url'. (string[], optional)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `path`: Only commits containing this file path will be returned (string, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)
  - `sha`: Commit SHA, branch or tag name to list commits of. If not provided, uses the default branch of the repository. If a commit SHA is provided, will list commits up to that SHA. (string, optional)
  - `since`: Only commits after this date will be returned (ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD) (string, optional)
  - `until`: Only commits before this date will be returned (ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD) (string, optional)

- **list_releases** - List releases
  - **OAuth Challenge Scopes**: `repo`
  - `fields`: Subset of fields to return for each release. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields; omitting 'body' in particular drops the largest per-release data. (string[], optional)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)

- **list_repository_collaborators** - List repository collaborators
  - **OAuth Challenge Scopes**: `repo`
  - `affiliation`: Filter by affiliation. Can be one of: 'outside' (outside collaborators), 'direct' (all with permissions regardless of org membership), 'all' (all collaborators). Default: 'all' (string, optional)
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (default 1, min 1) (number, optional)
  - `perPage`: Results per page for pagination (default 30, min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)

- **list_tags** - List tags
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: Repository name (string, required)

- **push_files** - Push files to repository
  - **OAuth Challenge Scopes**: `repo`, `workflow`
  - `branch`: Branch to push to (string, required)
  - `files`: Array of file objects to push, each object with path (string) and content (string) (object[], required)
  - `message`: Commit message (string, required)
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **search_code** - Search code
  - **OAuth Challenge Scopes**: `repo`
  - `fields`: Subset of fields to return for each code search result. If omitted, all fields are returned. Use this to reduce response size when you only need specific fields; omitting 'repository' and 'text_matches' in particular drops the largest per-result data. (string[], optional)
  - `order`: Sort order for results (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: Search query (GitHub code search REST). Implicit AND between terms; supports `OR`, `NOT`, and `"quoted phrase"` for exact match. Qualifiers: `repo:owner/repo`, `org:`, `user:`, `language:`, `path:dir` (prefix match), `filename:exact.ext`, `extension:`, `in:file`, `in:path`, `size:`, `is:archived`, `is:fork`. Max 256 chars. Examples: `WithContext language:go org:github`; `"package main" repo:o/r`; `func extension:go path:cmd repo:o/r`; `NOT TODO language:go repo:o/r`. (string, required)
  - `sort`: Sort field ('indexed' only) (string, optional)

- **search_commits** - Search commits
  - **OAuth Challenge Scopes**: `repo`
  - `order`: Sort order (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: Commit search query (GitHub commit search REST). Searches commit messages on the default branch only. Scope the search with `repo:owner/repo`, `org:`, or `user:` (queries without a scope qualifier match across all of GitHub and are usually not what you want). Other qualifiers: `author:`, `committer:`, `author-name:`, `committer-name:`, `author-email:`, `committer-email:`, `author-date:`, `committer-date:` (supports `>`, `<`, `>=`, `<=`, and `YYYY-MM-DD..YYYY-MM-DD` ranges), `merge:true|false`, `hash:`, `tree:`, `parent:`, `is:public`. Examples: `repo:owner/repo fix panic`; `org:github author:defunkt committer-date:>=2024-01-01`; `"refactor cache" repo:o/r`; `hash:abc1234 repo:o/r`. (string, required)
  - `sort`: Sort by author or committer date (defaults to best match) (string, optional)

- **search_repositories** - Search repositories
  - **OAuth Challenge Scopes**: `repo`
  - `minimal_output`: Return minimal repository information (default: true). When false, modern clients receive additional curated repository details, not the complete GitHub API object. Legacy clients retain full GitHub API repository objects. (boolean, optional)
  - `order`: Sort order (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: Repository search query. Examples: 'machine learning in:name stars:>1000 language:python', 'topic:react', 'user:facebook'. Supports advanced search syntax for precise filtering. (string, required)
  - `sort`: Sort repositories by field, defaults to best match (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/shield-lock-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/shield-lock-light.png"><img src="pkg/octicons/icons/shield-lock-light.png" width="20" height="20" alt="shield-lock"></picture> Secret Protection</summary>

- **get_secret_scanning_alert** - Get secret scanning alert
  - **OAuth Challenge Scopes**: `security_events`
  - `alertNumber`: The number of the alert. (number, required)
  - `owner`: The owner of the repository. (string, required)
  - `repo`: The name of the repository. (string, required)

- **list_secret_scanning_alerts** - List secret scanning alerts
  - **OAuth Challenge Scopes**: `security_events`
  - `owner`: The owner of the repository. (string, required)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `repo`: The name of the repository. (string, required)
  - `resolution`: Filter by resolution (string, optional)
  - `secret_type`: A comma-separated list of secret types to return. All default secret patterns are returned. To return generic patterns, pass the token name(s) in the parameter. (string, optional)
  - `state`: Filter by state (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/shield-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/shield-light.png"><img src="pkg/octicons/icons/shield-light.png" width="20" height="20" alt="shield"></picture> Security Advisories</summary>

- **get_global_security_advisory** - Get a global security advisory
  - **OAuth Challenge Scopes**: `security_events`
  - `ghsaId`: GitHub Security Advisory ID (format: GHSA-xxxx-xxxx-xxxx). (string, required)

- **list_global_security_advisories** - List global security advisories
  - **OAuth Challenge Scopes**: `security_events`
  - `affects`: Filter advisories by affected package or version (e.g. "package1,package2@1.0.0"). (string, optional)
  - `cveId`: Filter by CVE ID. (string, optional)
  - `cwes`: Filter by Common Weakness Enumeration IDs (e.g. ["79", "284", "22"]). (string[], optional)
  - `ecosystem`: Filter by package ecosystem. (string, optional)
  - `ghsaId`: Filter by GitHub Security Advisory ID (format: GHSA-xxxx-xxxx-xxxx). (string, optional)
  - `isWithdrawn`: Whether to only return withdrawn advisories. (boolean, optional)
  - `modified`: Filter by publish or update date or date range (ISO 8601 date or range). (string, optional)
  - `published`: Filter by publish date or date range (ISO 8601 date or range). (string, optional)
  - `severity`: Filter by severity. (string, optional)
  - `type`: Advisory type. (string, optional)
  - `updated`: Filter by update date or date range (ISO 8601 date or range). (string, optional)

- **list_org_repository_security_advisories** - List org repository security advisories
  - **OAuth Challenge Scopes**: `security_events`
  - `direction`: Sort direction. (string, optional)
  - `org`: The organization login. (string, required)
  - `sort`: Sort field. (string, optional)
  - `state`: Filter by advisory state. (string, optional)

- **list_repository_security_advisories** - List repository security advisories
  - **OAuth Challenge Scopes**: `security_events`
  - `direction`: Sort direction. (string, optional)
  - `owner`: The owner of the repository. (string, required)
  - `repo`: The name of the repository. (string, required)
  - `sort`: Sort field. (string, optional)
  - `state`: Filter by advisory state. (string, optional)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/star-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/star-light.png"><img src="pkg/octicons/icons/star-light.png" width="20" height="20" alt="star"></picture> Stargazers</summary>

- **list_starred_repositories** - List starred repositories
  - **OAuth Challenge Scopes**: `repo`
  - `direction`: The direction to sort the results by. (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `sort`: How to sort the results. Can be either 'created' (when the repository was starred) or 'updated' (when the repository was last pushed to). (string, optional)
  - `username`: Username to list starred repositories for. Defaults to the authenticated user. (string, optional)

- **star_repository** - Star repository
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

- **unstar_repository** - Unstar repository
  - **OAuth Challenge Scopes**: `repo`
  - `owner`: Repository owner (string, required)
  - `repo`: Repository name (string, required)

</details>

<details>

<summary><picture><source media="(prefers-color-scheme: dark)" srcset="pkg/octicons/icons/people-dark.png"><source media="(prefers-color-scheme: light)" srcset="pkg/octicons/icons/people-light.png"><img src="pkg/octicons/icons/people-light.png" width="20" height="20" alt="people"></picture> Users</summary>

- **search_users** - Search users
  - **OAuth Challenge Scopes**: `repo`
  - `order`: Sort order (string, optional)
  - `page`: Page number for pagination (min 1) (number, optional)
  - `perPage`: Results per page for pagination (min 1, max 100) (number, optional)
  - `query`: User search query. Examples: 'john smith', 'location:seattle', 'followers:>100'. Search is automatically scoped to type:user. (string, required)
  - `sort`: Sort users by number of followers or repositories, or when the person joined GitHub. (string, optional)

</details>
<!-- END AUTOMATED TOOLS -->