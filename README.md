# AI Playground

AI Playground is a project designed to improve the visibility and accessibility of AI tooling across the DOE.

In this context, "AI tooling" includes MCP servers, agents, skills, and other AI-specific resources.

## Purpose

AI Playground aims to answer two main questions:

- **Visibility**: What AI tooling exists across the DOE?
- **Availability**: Where does this tooling live, who owns it, and how can it be accessed/used?

## What users can do

AI Playground is an informational website that helps users discover and learn about existing AI tooling. It does not create or host tooling itself.

Users will be able to:

- Browse AI tooling by category
- Learn about available tools
- Search, query, and view registered tools
- Find links to the projects and systems used to store, create or manage tooling, such as MADA and URSA

## Registration workflow

Teams and individuals can register their AI tools by submitting a form on the website. Once registered, the tool will appear in the appropriate catalog category, such as:

- MCP Server
- Agent
- Skill
- Other AI tooling types

## Deployment model

Because the intended user base spans DOE organizations, including Office of Science and NNSA laboratories, AI Playground will support both public and private deployments, as well as BYOD environments.

Each environment will use a separate backend database.

## Tool metadata

Each registered tool will include the following metadata:

- Name
- Description
- Maintainer, such as a team or individual
- Institution
- Location, such as a repository or URL
- Versions
- Category, such as simulation, geometry, or scheduler
- Tags
- Logo
- Documentation link
- etc...

## Automatic registration

Tools created from the MADA library will be registered automatically in the AI Playground database.

## Getting started for developers

These instructions will show developers how to start up the website instance in order to start modifying it.

1. SSH into HPC with port forwarding: `ssh -4L 8000:localhost:8000 USER@HPC`
2. Install the environment: `uv sync`
3. Go https://launchit.llnl.gov/ and create an instance of PostgreSQL Vector
4. Create a `src/.env` file with the information below. LaunchIT will have the DB information while you will need to create a Django Key **ONLY ONCE** with `uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`

```
SECRET_KEY=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=...
DEBUG=True
```

5. Create an admin for your database `uv run python src/manage.py createsuperuser`
6. Configure your database with `uv run python src/manage.py makemigrations` and `uv run python src/manage.py migrate`
7. Start the server: `uv run python src/manage.py runserver`
    * You can run it on a different port with `uv run python src/manage.py runserver 8999` but be sure to update port in step 1.
8. Go to http://localhost:8000/admin/ to log in
9. Go to http://localhost:8000 to interact with the site

### Running the test suite

Install the project dependencies before running tests:

```bash
uv sync
```

Move into the `src/` directory:

```bash
cd src/
```

Run the complete Django test suite:

```bash
uv run python manage.py test
```

You can also choose to run specific test files. For example, run the tests for cards:

```bash
uv run python manage.py test apps.cards
```

To run only the cards API tests:

```bash
uv run python manage.py test apps.cards.tests.CardAPITests
```

The cards tests require Django to create a temporary PostgreSQL database. The
database user in `src/.env` therefore needs the PostgreSQL `CREATEDB`
privilege. A PostgreSQL administrator can grant it with:

```sql
ALTER ROLE your_database_user CREATEDB;
```

Replace `your_database_user` with the value of `DB_USER`. After granting the
privilege, rerun:

```bash
uv run python manage.py test apps.cards
```

If you cannot grant `CREATEDB` to the application user, ask the PostgreSQL
administrator to create a dedicated test database and test user, then use
those credentials for a test-specific settings configuration. Do not point
tests at your development database: Django tests are designed to isolate and
destroy their test data automatically.

Django creates a separate temporary test database for each test run. Your
development database is not modified by the test suite. If the test database
cannot be initialized because migrations are out of date, apply migrations to
the development database first:

```bash
uv run python manage.py migrate
```

### Cards API

The cards API is available under the versioned `/api/v1/` prefix. The API uses
Django session authentication, so a user must be logged in to make any API
request. This is the same authentication system used by the HTML views.

#### API documentation

Start the development server with:

```bash
uv run python src/manage.py runserver
```

Then log in through the website or admin site and open one of these pages:

- [Swagger UI](http://localhost:8000/api/v1/docs/) — an interactive API
  explorer. Expand an endpoint to inspect its parameters and response schema.
  Use **Try it out** to send a request from the browser.
- [ReDoc](http://localhost:8000/api/v1/redoc/) — a readable, reference-style
  view of the API schema.
- [OpenAPI schema](http://localhost:8000/api/v1/schema/) — the raw schema in
  JSON/YAML format for use with other API tools.

Because the API requires login, Swagger UI requests must have the same browser
session as the logged-in website. For state-changing requests such as POST,
PUT, PATCH, and DELETE, Django may also require a CSRF token.

#### Available endpoints

Standard CRUD endpoints are provided for cards:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/cards/` | List cards |
| `POST` | `/api/v1/cards/` | Create a card |
| `GET` | `/api/v1/cards/<id>/` | Retrieve one card |
| `PUT` | `/api/v1/cards/<id>/` | Replace a card |
| `PATCH` | `/api/v1/cards/<id>/` | Partially update a card |
| `DELETE` | `/api/v1/cards/<id>/` | Delete a card |

Category-specific list endpoints are also available:

```text
GET /api/v1/cards/mcp-servers/
GET /api/v1/cards/agents/
GET /api/v1/cards/skills/
```

All endpoints require an authenticated user. Any authenticated user can list,
retrieve, and create cards. Only the card owner, a listed maintainer whose
email matches the logged-in user, a staff user, or a superuser can update or
delete an existing card.

#### Creating a card

The server assigns the card owner from the logged-in user. Do not include an
`owner` field in the request body. Server-managed fields such as `id`,
`from_official_team`, `created_at`, and `updated_at` are read-only.

Example request body:

```json
{
  "name": "Example MCP server",
  "description": "Provides an example set of tools.",
  "maintainers": [
    {
      "name": "Example Maintainer",
      "email": "maintainer@example.com"
    }
  ],
  "institution": "Example Organization",
  "category": "mcp_server",
  "tags": ["example", "demo"],
  "logo_url": "https://example.com/logo.png",
  "documentation_url": "https://example.com/docs",
  "internal_url": "",
  "external_url": "https://example.com",
  "tools": [
    {
      "name": "example_tool",
      "description": "An example tool."
    }
  ]
}
```

Valid category values are `mcp_server`, `agent`, and `skills`. Maintainers
must be objects with an email address, tags must be non-empty strings, and
tools must be objects with a name.

### Project Layout

* `src/config/` contains the Django configuration files and settings
* `src/templates/` contains the high level html files that are used throughout the website
* `src/static/` contains the css, js, and images that are used throughout the website
* `src/apps/` contains the applications that are used throughout the website. A new app can be created with `uv run python manage.py startapp MYAPP src/apps/MYAPP`.
    * `src/apps/cards/` contains the `cards` apps that is the main focus of the website
        * `src/apps/cards/templates/` contains the html files for the cards app
        * `src/apps/cards/context_processors.py` contains data that can be called with double curly braces `{{}}` throughout the website (see `ai-playground/src/apps/cards/templates/cards/partials/stats_widget.html` for example). This references the model (datatable) `Cards` which houses the data.
        * `src/apps/cards/forms.py` contains the different forms that users can fill in for the `cards` app. This references the model (datatable) `Cards` which houses the data.
        * `src/apps/cards/models.py` contains the different models (datatables) that contain the data for the `cards` app. This is where you define the datatables and their fields. If you updated your datatables or create new ones, rerun the commands in step 7 and **git commit `src/apps/cards/migrations/*.py`**.
        * `src/apps/cards/urls.py` contains the different urls for the `cards` app. These reference the different views that connect the Python to html templates.
        * `src/apps/cards/views.py` contains the different views for the `cards` app. These connect the models, forms, and html templates to display the website.

## Release

AI Playground is distributed under the terms of the Apache License (Version 2.0) WITH LLVM Exception.

All new contributions must be made under the Apache 2.0 License WITH LLVM Exception.

See [LICENSE](./LICENSE), [COPYRIGHT](./COPYRIGHT), and [NOTICE](./NOTICE) for details.

SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

LLNL-CODE-2022047
