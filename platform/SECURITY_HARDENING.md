# Security patch deployment notes

This patch requires new application images and the updated Nginx configuration.
It does not update the running service automatically.

- Session cookies default to Secure. Production bootstrap explicitly sets
  `SESSION_COOKIE_SECURE=true`. Local HTTP Docker Compose defaults to false;
  local direct runs can set the same environment variable to false.
- HTTPS responses carry `Strict-Transport-Security: max-age=31536000`.
  The TLS proxy must forward `X-Forwarded-Proto`, and `REVERSE_PROXY` must match
  the trusted proxy topology.
- Ordinary request bodies and CSV imports default to 16 MiB
  (`MAX_CONTENT_LENGTH=16777216`). Authenticated administrators may upload
  attachments up to 256 MiB (`MAX_UPLOAD_CONTENT_LENGTH=268435456`) and backup
  archives up to 512 MiB (`MAX_IMPORT_CONTENT_LENGTH=536870912`). These are
  whole-request limits, including multipart framing. Backup members are limited
  to 512 MiB each and 2 GiB in total after expansion
  (`MAX_IMPORT_EXTRACTED_LENGTH=2147483648`).
  Nginx allows 16 MiB normally and 512 MiB on the upload/import routes, with
  request buffering disabled on those routes. Flask checks administrator
  identity before parsing them; file content streams directly to temporary disk.
  Text fields have a 512 KiB aggregate budget across chunks and fields, and
  multipart requests allow at most 100 parts. Increasing file limits therefore
  does not increase the text-field memory budget. Align Nginx ceilings when
  increasing environment limits, and provision temporary disk for uploads.
- Flask 2.2.5 and Werkzeug 2.3.8 preserve compatibility with the existing Flask
  extensions while fixing CVE-2023-46136. The later multipart memory advisory
  GHSA-q34m-jh98-gwm2 is mitigated by explicit aggregate field-byte accounting
  in the application parser, in addition to request caps; this is not a claim
  that all dependency audit findings are removed.
- Login IDs and email aliases share a per-account budget of 10 attempts per
  five-minute UTC window, across source IPs. Successful login resets the budget.
  The existing classroom-wide IP limit remains in force. Production uses Redis
  atomic add/increment operations across workers.
- Public profile histories, score totals, and ranking graphs exclude hidden
  and locked challenges. Admin accounts do not contribute to public standings.
  Administrator score views and grade exports retain the original records.
- Students cannot Test problems with a positive Max Attempts setting. Tests
  on unlimited practice problems remain ungraded, but obey the deadline and
  competition end. Administrator Test remains available for problem review.

Upstream advisories:

- https://github.com/pallets/werkzeug/security/advisories/GHSA-hrfv-mqp8-q5rw
- https://github.com/pallets/werkzeug/security/advisories/GHSA-q34m-jh98-gwm2
