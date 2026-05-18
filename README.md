# Google Workspace Tools

A collection of Python admin scripts for managing Google Workspace at scale — the kind of operations the Admin Console does one user at a time, done programmatically across an entire domain.

Organized by category. All scripts share a common auth and rate-limiting layer (`_master.py`) so they stay consistent and don't hammer API quotas.

---

## Structure

```
_master.py          ← shared utilities (auth, pagination, rate limiting, CSV export)
authenticator.py    ← Google API credential helpers
gmail_messages/     ← read, search, and purge email across mailboxes
gmail_settings/     ← audit forwarding, send-as, filters, signatures, vacation rules
groups/             ← group management (list, add/remove members, bulk delete)
users/              ← user provisioning and bulk operations
drive/              ← file search and recovery
ai/                 ← Gemini integration
```

---

## Gmail — messages (`gmail_messages/`)

| Script | What it does |
|---|---|
| `investigatePhishing.py` | Pull messages in a date range from a user's mailbox, score each on phishing indicators (suspicious sender keywords, subject patterns, link count), and rank results — useful after a reported compromise |
| `purgeMessages.py` | Delete or move to spam a message matching sender/subject across **every user's mailbox** simultaneously; uses thread pooling (10 concurrent users) and Gmail batch endpoints to handle large domains quickly |
| `searchMessages.py` | Search messages across a user's inbox with a Gmail query string |
| `Get Emails.py` / `Email Fetch.py` | Fetch and display email content |
| `message.list.py` | List messages with metadata |
| `auditAfterHoursEmails.py` | Audit a user's email activity outside business hours — useful for compliance or security investigations |
| `deleteEmail.py` | Delete specific messages by ID |

---

## Gmail — settings (`gmail_settings/`)

Security audit scripts. Useful for periodic reviews or post-incident investigation.

| Script | What it does |
|---|---|
| `auditForwarding.py` | Scan every user for auto-forwarding rules and filters pointing to a target address — finds data exfiltration and compromised-account redirects |
| `auditSendAs.py` | Flag users whose send-as settings are non-default: custom reply-to addresses, aliases that let them send as someone else, display names that don't match the directory |
| `checkFilters.py` | List all Gmail filters for a user |
| `checkForwarding.py` | Check forwarding settings for a specific user |
| `checkSignature.py` | Retrieve a user's email signature |
| `checkVacation.py` | Check vacation/out-of-office settings |
| `send_as.py` | Manage send-as aliases |

---

## Groups (`groups/`)

| Script | What it does |
|---|---|
| `listGroups.py` | List all groups in the domain |
| `searchGroups.py` | Search groups by name or email |
| `listGroupMembers.py` | List all members of a specific group |
| `listUserGroups.py` | List all groups a user belongs to |
| `groupMembersByOrgUnit.py` | Show group membership broken down by OU |
| `addUserToGroups.py` | Add a user to one or more groups |
| `removeUserFromGroups.py` | Remove a user from groups |
| `countGroups.py` | Count groups across the domain |
| `bulkDeleteGroups.py` | Delete a list of groups from CSV input |

---

## Users (`users/`)

| Script | What it does |
|---|---|
| `UserCreate.py` | Create a new user via Admin Directory API |
| `UserEdit.py` / `update user info.py` | Update user profile fields |
| `AddUsers.py` | Bulk user creation |
| `forcePasswordReset.py` | Set `changePasswordAtNextLogin` for all users under an OU — used after security incidents or compliance resets |
| `bulkChangePhoto.py` | Bulk update profile photos |
| `listOrgUnits.py` | List all OUs in the domain |
| `move_to_recruiting.py` | Move a user to a specific OU |
| `remove_suspended.py` | Remove suspended users from groups or clean them up |
| `updateDesktopSecurity.py` | Set custom schema attributes (used for GCPW profile adoption — see [Active-Directory-Tools](../Active-Directory-Tools)) |
| `format.py` | Format/normalize user data |

---

## Drive (`drive/`)

| Script | What it does |
|---|---|
| `find_file.py` | Search for files by name across a user's Drive |
| `move_deleted_files.py` | Recover files from a departed user's Drive and move them to a target folder under a different owner — useful during offboarding |

---

## AI (`ai/`)

| Script | What it does |
|---|---|
| `gemini.py` | Interactive CLI chat using Gemini 1.5 Flash with persistent conversation context |

---

## Shared utilities (`_master.py`)

All scripts import from `_master.py` rather than duplicating auth and pagination logic:

- `get_service()` — Admin Directory API client
- `get_gmail_service(email)` — Gmail API client delegated to a specific user
- `paginate_users(service, query, excluded_ous)` — handles all pagination automatically
- `rate_limited_execute(request)` — enforces 20 calls/second to stay under quota
- `paginate_groups()`, `get_members()` — group enumeration helpers
- `ask_export()` — prompt to save results to CSV in `output/`

---

## Setup

Requires a Google service account with domain-wide delegation. Scopes needed depend on which scripts you use:

| Scope | Used by |
|---|---|
| `admin.directory.user` | All user management scripts |
| `admin.directory.group` | All group scripts |
| `gmail.readonly` or `gmail.modify` | Gmail audit and purge scripts |
| `drive` | Drive scripts |
| `cloud-identity.devices.readonly` | Device mapping (in Active-Directory-Tools) |

```bash
pip install google-api-python-client google-auth pandas
```

Place service account credentials where `authenticator.py` expects them. Each script targets `yourdomain.com` — update the `DOMAIN` constant in `_master.py` for your domain.
