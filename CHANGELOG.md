# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Dates are the date of each
release's tag.

## [0.10.17] - 2026-10-22

### Fixed
- `GET /topics` no longer fails on newer osTicket databases. osTicket 1.10+ dropped the `isactive`
  column from `ost_help_topic` and records whether a topic is active in the `FLAG_ACTIVE` bit of
  `flags` instead, so the old `WHERE isactive = 1` filter broke the endpoint there. The API now
  checks which column the database has: older schemas still filter on `isactive`, and newer ones
  list only topics with `FLAG_ACTIVE` set, so archived and disabled topics stay hidden.

## [0.10.16] - 2026-10-12

### Fixed
- Users without an email address, and their tickets, are no longer missing from the API. The
  queries joined `ost_user_email` with an inner join, so any user with no email row was silently
  dropped from `GET /users` and `GET /users/{user_id}`, and their tickets from `GET /tickets` and
  `GET /tickets/{ticket_id}`. These now use a left join, and the `email` field in user and ticket
  responses is `null` when the user has no email address.

## [0.10.15] - 2026-10-07

### Fixed
- `sql/add_ticket_updated_index.sql` now works on MariaDB 5.5+ and MySQL 5.5+. The 0.10.13 version
  needed MariaDB 10.0+ and failed with a syntax error on MariaDB 5.5 and on MySQL. It is still safe
  to re-run. On MariaDB 5.5 and MySQL 5.5, building the index blocks writes to `ost_ticket` for the
  few seconds it takes.

### Known limitations
- Filtering `GET /tickets` on a custom field alone (e.g. `?priority=...`) is still slow on large
  databases. Combine it with a standard filter such as `status_id` or `updated_after` to keep it
  fast.

## [0.10.14] - 2026-10-07

### Changed
- Unfiltered `GET /tickets` is faster again on large databases, with the same response as before.
  On a production database with ~235k tickets (MariaDB 5.5), the optimizer started the page query
  from the user table and sorted every ticket before applying the page limit. The query now reads
  the requested page straight off the ticket table's `created` index, stopping after `limit` rows:
  the data query dropped from about 3.8s to 0.05s, and the whole unfiltered request from 7–10s to
  2.4–3.3s. The `email` filter keeps the optimizer's own join order, since it is most selective
  through the unique email address key.

## [0.10.13] - 2026-10-07

### Added
- `sql/add_ticket_updated_index.sql` adds an index on `ost_ticket.updated` so the `updated_after` /
  `updated_before` filters on `GET /tickets` no longer scan the whole ticket table. Stock osTicket
  indexes `created` but not `updated`. Run the script once per osTicket database as a user with
  ALTER privilege (see "Recommended Database Index" in the README); the API itself still makes no
  schema changes. On 200k synthetic tickets, filtering a one-week `updated` window went from 0.105s
  to 0.0005s. This version of the script needs MariaDB 10.0+; use the one from 0.10.15 or later on
  MariaDB 5.5 or MySQL.

## [0.10.12] - 2026-10-07

### Changed
- `GET /tickets` is much faster on large databases, with the same response as before. The query
  used to join every matching ticket, including the body of its first message, then sort all of
  them before applying the page limit, so its cost grew with the total number of tickets rather
  than the page size. It now picks the requested page of ticket ids first and joins the status,
  user, topic, department, team and first message only for those rows. On 50k synthetic tickets the
  data query went from 2.48s to 0.03s.

## [0.10.11] - 2026-09-09

### Added
- `GET /attachments` and `GET /tickets/{ticket_id}/attachments` now include a `cid` field: the
  lowercased file key osTicket embeds in inline `<img src="cid:...">` tags within a message's HTML
  body. Use it to relate an inline image in a message back to its attachment; it is `null` for
  attachments not referenced inline.

## [0.10.10] - 2026-09-07

### Changed
- `GET /health` now always returns HTTP 200 and reports the database status in the response body
  (`status: degraded`, `database: error`) instead of returning 503. The endpoint doubles as the
  Cloud Run startup probe, where a non-2xx response during a database outage made Cloud Run refuse
  to start or route traffic to the container, turning it into a 502 for every request. The
  underlying error is now logged server-side instead of being included in the unauthenticated
  response.

## [0.10.9] - 2026-09-03

### Changed
- Message and note bodies (`TicketCreate.message`, `NoteCreate.body`, `MessageCreate.body`,
  `MessageUpdateRequest.body`) are capped at 65535 characters, matching osTicket's underlying TEXT
  column. Oversized input now returns a clean 422 instead of a 500 from a failed database insert.

## [0.10.8] - 2026-09-02

### Added
- Optional HTTP fallback for `GET /attachments` and `GET /tickets/{ticket_id}/attachments`: when a
  file has no database-stored content, the API can fetch it through osTicket itself, so `content`
  is no longer always `null`. Enable it with the new `OSTICKET_BASE_URL`, `OSTICKET_SECRET_SALT`,
  `OSTICKET_STAFF_USERNAME` and `OSTICKET_STAFF_PASSWORD` environment variables. Behavior is
  unchanged when they are unset.

## [0.10.7] - 2026-08-31

### Fixed
- `GET /attachments`, `GET /tickets/{ticket_id}/attachments` and their deprecated equivalents
  returned `content: ""` for files stored outside the database (`ost_file.bk != 'D'`, e.g.
  filesystem storage), which looked like a genuinely empty file. `content` is now `null` in that
  case; check `size` for the real file size.

## [0.10.6] - 2026-08-31

### Fixed
- `GET /users` and `GET /users/{user_id}` could fail with "Input should be a valid datetime" for
  `ost_user` rows with a NULL `updated` column. `UserResponse.updated` is now optional.

## [0.10.5] - 2026-08-31

### Fixed
- `GET /messages` and `GET /tickets/{ticket_id}/messages` returned a 500 ("Input should be a valid
  datetime" on `updated`) for thread entries with a NULL `updated` column, which some osTicket
  installations have on legacy rows. `updated` can now be `null`.

## [0.10.4] - 2026-08-31

### Added
- `PATCH /tickets/{ticket_id}/status`, `.../department`, `.../team`, `.../messages/{entry_id}` and
  `.../attachments/{file_id}`: the same behavior as the `PUT` equivalents, with the correct HTTP
  verb for a partial update.
- `PUT /tickets/{ticket_id}/closed` closes a ticket, replacing the verb-based `.../close`.

### Deprecated
- `PUT /tickets/{ticket_id}/status`, `.../department`, `.../team`, `.../messages/{entry_id}` and
  `.../attachments/{file_id}`: use the `PATCH` equivalents.
- `PUT /tickets/{ticket_id}/close`: use `PUT /tickets/{ticket_id}/closed`.

All deprecated endpoints remain fully functional.

## [0.10.3] - 2026-08-31

### Added
- `POST /tickets/{ticket_id}/messages` creates a message.
- `PUT /tickets/{ticket_id}/messages/{entry_id}` updates a specific message entry, instead of
  implicitly targeting the latest one.
- `POST /tickets/{ticket_id}/messages/{entry_id}/attachments` attaches a file.
- `POST /tickets/{ticket_id}/notes` adds a note.
- `PUT /tickets/{ticket_id}/attachments/{file_id}` replaces an attachment's contents.

### Deprecated
- `POST /tickets/{ticket_id}/message`: use `POST /tickets/{ticket_id}/messages`.
- `PUT /tickets/{ticket_id}/message`: use `PUT /tickets/{ticket_id}/messages/{entry_id}`. The old
  form still edits the latest thread entry.
- `POST /tickets/{ticket_id}/messages/{entry_id}/attach`: use `.../attachments`.
- `POST /tickets/{ticket_id}/note`: use `POST /tickets/{ticket_id}/notes`.
- `PUT /tickets/{ticket_id}/attachment/{file_id}`: use `.../attachments/{file_id}`.

All deprecated endpoints remain fully functional.

## [0.10.2] - 2026-08-31

### Added
- `GET /messages?ticket_ids=...` and `GET /attachments?ticket_ids=...`: messages and attachments
  for one or more tickets, as top-level resources.

### Deprecated
- `GET /tickets/messages?ticket_ids=...`: use `GET /messages`.
- `GET /tickets/attachments?ticket_ids=...`: use `GET /attachments`.

## [0.10.1] - 2026-08-31

### Added
- `GET /tickets/{ticket_id}/messages` and `GET /tickets/{ticket_id}/attachments` are back for the
  single-ticket case, alongside the multi-ticket `?ticket_ids=...` forms.

## [0.10.0] - 2026-08-31

### Added
- `GET /teams` lists available teams.
- `GET /tickets/messages?ticket_ids=...` and `GET /tickets/attachments?ticket_ids=...` return
  messages and attachments for one or more tickets.
- `POST /tickets/{ticket_id}/message` adds a public message or reply to a ticket's thread.
- `GET /tickets` now includes `subject` and `message` for each ticket.

### Changed (breaking)
- `GET /tickets/{ticket_id}/messages` became `GET /tickets/messages?ticket_ids=...`.
- `GET /tickets/{ticket_id}/attachments` became `GET /tickets/attachments?ticket_ids=...`.
- `POST /tickets/{ticket_id}/attach` became `POST /tickets/{ticket_id}/messages/{entry_id}/attach`,
  which targets a specific thread entry instead of always the latest one.

### Fixed
- Attaching a file no longer allows targeting an entry that belongs to a different object type's
  thread with the same numeric id as the ticket.
- `GET /tickets/messages` and `GET /tickets/attachments` return 422 instead of 500 when
  `ticket_ids` is omitted.

## [0.9.3] - 2026-08-26

### Added
- `GET /tickets/{ticket_id}/messages` returns the messages and replies in a ticket's thread.
- `GET /tickets/{ticket_id}/attachments` returns a ticket's attachments, with file metadata and
  base64-encoded content.
- `POST /tickets/{ticket_id}/message` adds a public message or reply to a ticket's thread and
  returns the created thread and entry ids.

## [0.9.2] - 2026-08-23

### Added
- An endpoint to retrieve the messages in a ticket's thread.

## [0.9.1] - 2026-08-20

### Fixed
- Pagination `next` / `previous` URLs now honor `X-Forwarded-Proto` and `X-Forwarded-Host`, so
  clients calling the API through a gateway get links to the host they actually used instead of the
  internal backend host.

## [0.9.0] - 2026-08-14

### Added
- `POST /tickets/{ticket_id}/note` adds an internal, staff-only note to a ticket's thread. Notes are
  never visible to the ticket's owner and send no email.
- `GET /tickets/{ticket_id}` now includes `subject`, `message` (the thread's first entry) and the
  `closed` timestamp.
- `ROOT_PATH` environment variable for deploying behind a reverse proxy under a sub-path.

### Changed
- The minimum supported Python version is now 3.14.

## [0.8.3] - 2026-08-13

### Changed
- Relicensed from MIT to the GNU General Public License v2.0.

## [0.8.2] - 2026-08-11

### Added
- `PUT /tickets/{ticket_id}/status`, `.../department` and `.../team` update a ticket's status,
  department and team.
- `PUT /tickets/{ticket_id}/message` updates the latest message entry in a ticket's thread.
- `PUT /tickets/{ticket_id}/attachment/{file_id}` replaces the contents of an attachment.

## [0.8.1] - 2026-07-31

### Fixed
- Custom field filters on `GET /tickets` failed with `FUNCTION db.JSON_UNQUOTE does not exist` on
  servers without JSON functions (before MariaDB 10.2 / MySQL 5.7.8, e.g. MariaDB 5.5). The API now
  detects JSON function support and falls back to a plain `LIKE` match where it is missing.

## [0.8.0] - 2026-07-14

### Changed
- Switched the MySQL driver from PyMySQL to mysqlclient. PyMySQL encodes passwords as Latin-1 during
  authentication, so non-ASCII passwords (e.g. containing `£`) set with UTF-8 tools failed to
  authenticate even when correct. The Docker image now installs mysqlclient's native build
  dependencies.

## [0.7.1] - 2026-07-14

### Fixed
- The database connection failed when `DB_PASSWORD` contained special characters such as `#`. The
  connection URL is now built with SQLAlchemy's `URL.create()`, which encodes credentials correctly.

## [0.7.0] - 2026-07-13

### Added
- A Docker image is published to the GitHub Container Registry for each GitHub release.

## [0.6.0] - 2026-04-18

### Added
- `MAX_UPLOAD_MB` environment variable caps attachment uploads (default 10 MB).

### Changed
- File fingerprints use SHA-256 instead of SHA-1.
- Open and closed status ids are looked up from `ost_ticket_status` instead of being hardcoded.

### Fixed
- Closing a ticket that does not exist returns 404.
- Adding an attachment to a ticket that does not exist returns 404 instead of failing.
- The `subject` given when creating a ticket is now stored as the first thread entry's title.
- `updated_after` and `updated_before` are no longer mistaken for custom field filters.
- Creating a ticket no longer exposes raw database error details.
- The health check no longer leaks a database connection when it fails.

## [0.5.0] - 2026-02-25

### Added
- `updated_after` and `updated_before` filters on `GET /tickets`.

## [0.4.1] - 2026-02-11

### Fixed
- The version shown in the API docs is now set directly instead of read from package metadata,
  which showed `0.0.0-dev` when the package was not installed.

## [0.4.0] - 2026-02-11

### Removed
- IP address restrictions on API keys (the `ipaddr` column of `ost_api_key`) are no longer
  enforced.

### Added
- Continuous integration running the test suite against MariaDB.

## [0.3.0] - 2026-02-08

### Changed (breaking)
- API keys are now read from osTicket's `ost_api_key` table instead of the `API_KEYS` environment
  variable. Inactive keys are rejected.

### Added
- Custom form fields on tickets, and filtering `GET /tickets` by custom field.
- Ticket ids and typed response models.
- Support for Python 3.13.

### Security
- Attachment upload errors no longer expose internal error details in the response.

## [0.2.0] - 2026-02-02

### Added
- First tagged release: create, search and manage osTicket tickets through a REST API, with
  ReDoc documentation at the root and a health check endpoint.
