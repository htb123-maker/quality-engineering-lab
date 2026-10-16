# Yuque Project Hub Runbook

## Purpose

Publish the repository documents (goals, plan, ADRs, architecture notes,
runbooks, test strategy, daily and weekly reports) into a Yuque (语雀)
knowledge base, so the project can be read on a phone. The repository stays the
single source of truth; Yuque is only the reading surface.

## Why an API token is required

- The Yuque desktop and mobile apps are reading and editing surfaces. They
  expose no automation interface this repository can drive, so "sync when a
  report is finished" cannot be done through the app alone.
- `scripts/sync_yuque.py` talks to the Yuque Open API v2
  (`https://www.yuque.com/api/v2`) with a personal access token.
- Manual fallback: copy a page, or use Yuque "Import -> Markdown" per file. It
  works for a one-off page but has to be repeated by hand every week.

## Prerequisites

- A Yuque account and one knowledge base (book) this project may write to.
- A personal access token: Yuque -> Settings -> token management. Treat it as a
  secret; it only belongs in `.env`, which is git-ignored.
- `uv sync` has been run once.

## Cost and eligibility

Checked 2026-10-15 by rendering the official pages in a browser; a plain HTTP
fetch only returns the JavaScript shell, so a browser (or Playwright) is needed
to read them.

- Overview page <https://www.yuque.com/yuque/developer/api> labels the two
  authentication sections as paid benefits: personal authentication is marked
  as a Super Member (超级会员) benefit, and team authentication as a Flagship
  space (旗舰版空间) benefit. The same page states that every Open API call must
  authenticate with `X-Auth-Token`, which is what this script sends.
- Announcement <https://www.yuque.com/yuque/developer/vzippmige58g7r9t>
  ("语雀开放 API 访问范围变更") says that since 2022-04-10 a personal token only
  reaches documents that token has permission for. Comments from 2024 and 2025
  on that page are users asking whether a Super Member subscription is required
  to use the API at all.

So the API is documented and publicly reachable, but personal use sits behind
the Super Member tier and team use behind a Flagship space. An invalid token
answers `401`, which only proves the endpoint exists, not that a free account
may use it.

Free alternatives when the subscription is not worth it:

- Import the Markdown by hand. A Yuque book accepts Markdown files (multi
  select) through its import entry, so the existing documents can be imported
  once and each new report imported as it is written. The repository stays the
  source of truth.
- Read on GitHub instead. This repository is public, and GitHub renders both
  Markdown and the Mermaid blocks used in these documents in the mobile app and
  the mobile web UI, at no cost.

## Configure

1. Create the personal access token first: Yuque -> Settings -> token
   management. Put it in `.env` on its own:

   ```text
   YUQUE_TOKEN=your-personal-access-token
   ```

2. Let the token report the account and its knowledge bases, so the namespace
   and book slug do not have to be guessed from a URL:

   ```powershell
   uv run python scripts/sync_yuque.py --books
   ```

   The output table has one row per knowledge base; `namespace` and `book` are
   exactly the two segments of `https://www.yuque.com/<namespace>/<book>`.
   `--books` needs nothing but the token.

3. Add the two values from the target row to `.env` (never to `.env.example`):

   ```text
   YUQUE_NAMESPACE=your-login-or-team
   YUQUE_BOOK=your-book-slug
   YUQUE_TOKEN=your-personal-access-token
   ```

4. Verify the token and the target book:

   ```powershell
   uv run python scripts/sync_yuque.py --check
   ```

Without a token, `--books` exits with a configuration error instead of a
network call, so a missing token is visible immediately.

## Publish

```powershell
# Dry run: prints what would happen, performs no HTTP request.
uv run python scripts/sync_yuque.py

# Create or update the pages.
uv run python scripts/sync_yuque.py --apply
```

Behaviour worth knowing:

- The sync is idempotent. Pages are matched by slug and updated in place, so
  re-running it after editing a report refreshes that page and keeps its URL.
- A generated `index` page groups every document and is the entry point on a
  phone. It is regenerated from the repository, so do not edit it in Yuque.
- Cross-document links such as `[goals](GOALS.md)` are rewritten to the Yuque
  URL of the target page. Heading anchors are dropped because Yuque generates
  its own anchor ids.
- `--only WEEK-09.md` publishes one document and skips the index page, so a
  filtered run can never overwrite the index with a partial list.
- `--include docs` limits the sync to the `docs` top-level directory.
- `--list` prints the slugs and paths without reading `.env` or using the
  network.
- `--books` prints the namespace, book slug and name of every knowledge base
  the token can see; it only needs `YUQUE_TOKEN`.
- `TEMPLATE.md` files are skipped by design.

## Slug map

| Repository path | Yuque slug |
| --- | --- |
| `docs/GOALS.md` | `goals` |
| `docs/PLAN.md` | `plan` |
| `docs/adr/0007-transaction-isolation-and-lock-testing.md` | `adr-0007-transaction-isolation-and-lock-testing` |
| `docs/architecture/*.md` | `arch-*` |
| `docs/runbooks/*.md` | `runbook-*` |
| `docs/test-strategy/*.md` | `test-strategy-*` |
| `reports/weekly/WEEK-09.md` | `week-09` |
| `reports/daily/DAY-01.md` | `day-01` |
| generated index page | `index` |

Two different paths that produce the same slug abort the sync with
`slug collision` instead of silently overwriting a page.

## Diagrams

Diagrams in `docs/**` are Mermaid code blocks, and the sync leaves them
untouched. Check once in your own book that
`docs/architecture/project-overview.md` renders as a diagram. If a book does
not render Mermaid, extract the block into a `.mmd` file and export a PNG with
the Mermaid CLI, then paste the image into a Yuque 画板:

```powershell
npx --yes @mermaid-js/mermaid-cli@11 -i diagram.mmd -o diagram.png
```

## Troubleshooting

| Symptom | Cause | Action |
| --- | --- | --- |
| `Yuque API returned 401` | token missing, wrong, or expired | regenerate `YUQUE_TOKEN` |
| `Yuque API returned 403` | the token cannot write this book | use your own book, re-check namespace and book slug |
| `Yuque API returned 404` | namespace or book slug wrong | re-copy both parts from the book URL |
| `configuration error: missing ...` | `.env` not filled in | complete the Configure section |
| browser shows "页面迷路了" for `https://www.yuque.com/<namespace>/<book>` | the angle brackets are placeholders, not a real URL | run `--books`, or copy the two path segments of a book you opened in the browser |
| `slug collision` | two paths map to one slug | rename one file or extend `slug_for` |
| a page shows literal `#` and `|` markers | Yuque stored rich text instead of Markdown | check the create/update parameters in the official API docs and adjust `YuqueClient.create_document` |
| `429` | rate limited | wait; the client already retries twice with backoff |

## What was verified

- `uv run pytest tests/unit/test_sync_yuque.py` covers slug mapping, discovery,
  link rewriting, the dry-run guarantee, create/update behaviour, and the HTTP
  client contract through `httpx.MockTransport`. No test uses the network.
- Endpoint reachability, checked 2026-10-15: `GET
  https://www.yuque.com/api/v2/user` with an invalid token answers `401`,
  confirming the base path and the `X-Auth-Token` header.
- Not verified: a real create/update round trip, which needs a personal token
  and a writable book. Run `--check`, then one `--only` publish, then `--apply`.

## Security

- The token lives only in `.env`. Never paste it into a document, a report, or
  `.env.example`.
- Publishing makes the synced documents readable to whoever the book is shared
  with. Keep the book private while the reports contain internal detail.
- Never commit the generated `.env`; `.gitignore` already covers it.
