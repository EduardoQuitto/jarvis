# J.A.R.V.I.S. — Utility Tools (Fase 15.1, v0.6.1)

13 built-in tools, all `SecurityLevel.GREEN`, executed exclusively through
`ToolRegistry.execute_tool()` + `PolicyEngine`. No shell (`shell=True` is
never used), no `eval()`, no threads/daemons/schedulers, no new dependencies
(stdlib + `psutil`, both already in the project).

## Network (`tools/builtin/network_tool.py`)

| Tool | Params | Returns |
|------|--------|---------|
| `ping_host` | `hostname: str`, `count: int = 4` (1–10) | `hostname`, `resolved_addresses`, `count`, `successful`, `failed`, `refused_count`, `timeout_count`, `packet_loss_percent`, `latency_min/avg/max_ms`, `reachable`, `method: "tcp_connect"` (+ `dns_error` when unresolvable) |
| `dns_lookup` | `domain: str` | `domain`, `addresses`, `ipv4`, `ipv6`, `canonical_names`, `resolved` (+ `error`) |
| `get_network_interfaces` | — | `interfaces[]` (`name`, `is_up`, `speed_mbps`, `mtu`, `flags`, `addresses[]` with family/address/netmask/broadcast/ptp), `count` |

**Limitations.** Reachability is measured with TCP handshakes on ports
80/443, not ICMP echo (raw ICMP needs privileges; parsing the system `ping`
binary is fragile across Windows/Linux). `reachable` means at least one
handshake completed; refused/timeout are reported separately. DNS failure is
a structured result, never a crash.

## Notifications (`tools/builtin/notification_tool.py`, `core/notifications/`)

| Tool | Params |
|------|--------|
| `send_notification` | `title: str`, `message: str`, `priority: low\|normal\|high`, `channel: push\|desktop\|webhook` |
| `check_pending_notifications` | — (lists PENDING without delivering) |

Flow: `send_notification()` → `NotificationService` → provider → channel.
State (`notification_id`, `title`, `message`, `priority`, `channel`,
`created_at`, `delivered_at`, `status`, `error`) persists in the runtime
memory backend under `notification:{id}` plus a `notification:index` list, so
listing works on local and central backends.

**Which channels really work:**
- `push` — **pending only**. No mobile/ADB infrastructure exists; the
  notification is stored and the result says so explicitly. Real delivery
  needs a future provider (e.g. companion app / FCM).
- `desktop` — **pending only**. No multiplatform mechanism without new
  dependencies; same honest treatment as push.
- `webhook` — **delivered** via POST to the single URL configured in
  `JARVIS_NOTIFICATION_WEBHOOK_URL`. Never to caller-supplied URLs. Empty
  configuration → explicit `FAILED` (never silent, never crash).

Statuses: `pending` (stored, awaiting a capable provider), `delivered`
(provider confirmed), `failed` (explicit error). Only `id`, `channel` and
status reach the logs — never titles, bodies or URLs.

## Filesystem (`tools/builtin/filesystem_analysis_tool.py`)

| Tool | Params |
|------|--------|
| `find_duplicates` | `directory: str` |
| `disk_usage_analysis` | `path = "."`, `max_depth = 5` (0–10), `max_entries = 200` (1–2000), `top_n = 10` (1–50) |

Both use `AllowlistValidator.validate_sandbox_path()` (same PATH semantics
as the policy): traversal/escapes blocked, `allowed_paths` respected,
directory symlinks never followed, symlinked files resolving outside are
skipped and counted. Files hash in 64 KB chunks (never fully loaded);
size pre-grouping avoids hashing unique sizes; caps (20k files, 200 groups)
bound time/output. Unreadable/vanishing files are counted as `skipped`
(documented, never fatal). `disk_usage_analysis` never returns an unbounded
tree; a file path returns a single-file summary.

## Security (`tools/builtin/security_tool.py`)

| Tool | Params |
|------|--------|
| `generate_password` | `length = 16` (8–128), `complexity = high` (`low`/`medium`/`high`) |
| `hash_file` | `file_path`, `algorithm = sha256` (`sha256`, `sha512`, `sha1`, `md5`) |
| `verify_checksum` | `file_path`, `expected_hash`, `algorithm = sha256` or `"auto"` |

- Passwords use `secrets` (never `random`), guarantee one char per required
  class (medium/high), are never logged and never persisted. Ambiguous
  lookalikes are intentionally kept to maximize entropy.
- Hashes stream in 64 KB chunks; algorithms are an explicit allowlist (no
  dynamic `getattr` on user input). MD5/SHA-1 exist for compatibility and
  non-cryptographic integrity only.
- `verify_checksum` normalizes hex, validates length, compares with
  `hmac.compare_digest`, returns `{file_path, algorithm, actual_hash,
  expected_hash, matches}`. `"auto"` infers only from documented lengths
  (64/128/40/32); anything else requires an explicit algorithm.

## Math (`tools/builtin/utility_tool.py`)

`calculate_math(expression)` — no `eval()`, only a strict AST whitelist:
`+ - * / // % **`, parens, `abs round sqrt sin cos tan log log10 exp floor
ceil`, constants `pi`/`e`. Guards: 500-char limit, AST depth 20, static
exponent cap 1000, non-finite rejection, magnitude cap. Division by zero,
unknown names/calls/attributes and oversized input fail explicitly with
`{expression, result, type}` on success.

## System diagnostics (`tools/builtin/system_info_tool.py`)

- `get_system_info()` — hostname, OS/version, architecture, processor, Python
  version, CPU counts, total RAM, JARVIS version/node identity. Explicit
  field allowlist: settings secrets can never leak.
- `get_system_uptime()` — `boot_time`, `uptime_seconds`, `uptime_human`
  (`Xd Xh Xm Xs`) via `psutil`, no shell commands.

## Multiplatform behavior

Windows + Linux supported with stdlib/`psutil` only. Known platform notes:
symlink tests skip without OS privilege (same pattern as the file-sandbox
suite); `ping_host` measures TCP handshakes, not ICMP; interface names/flags
follow each OS (`lo` vs `Loopback*`).
