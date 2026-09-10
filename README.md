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

## Release

AI Playground is distributed under the terms of the Apache License (Version 2.0) WITH LLVM Exception.

All new contributions must be made under the Apache 2.0 License WITH LLVM Exception.

See [LICENSE](./LICENSE), [COPYRIGHT](./COPYRIGHT), and [NOTICE](./NOTICE) for details.

SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

LLNL-CODE-2022047


## Getting started for developers

These instructions will show developers how to start up the website instance in order to start modifying it.
The `backend/` directory only contains the Django project which is currently acting as the backend and frontend of the website.
The `frontend/` directory only contains the React-TS project which is currently not being used at all.

1. SSH into HPC with port forwarding: `ssh -4L 8000:localhost:8000 USER@HPC`
2. Install the environment: `uv sync`
3. Go https://launchit.llnl.gov/ and create an instance of PostgreSQL Vector
4. Create a `backend/.env` file with the information below. LaunchIT will have the DB information while you will need to create a Django Key **ONLY ONCE** with `uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())`

```
SECRET_KEY=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=...
DEBUG=True
```

4. Start the server: `uv run python backend/manage.py runserver`
5. Open up Firefox and go to `localhost:8000`
6. Create an admin for your database `uv run python backend/manage.py createsuperuser` and go to `http://localhost:8000/admin/` to log in.
7. Configure your database with `uv run python backend/manage.py makemigrations` and `uv run python backend/manage.py migrate`


### Project Layout

#### `backend/`

As mentioned above, the `backend/` directory only contains the Django project which is currently acting as the backend and frontend of the website.

* `backend/config/` contains the Django configuration files and settings
* `backend/templates/` contains the high level html files that are used throughout the website
* `backend/static/` contains the css, js, and images that are used throughout the website
* `backend/apps/` contains the applications that are used throughout the website. A new app can be created with `uv run python backend/manage.py startapp MYAPP backend/apps/MYAPP`.
    * `backend/apps/cards/` contains the `cards` apps that is the main focus of the website
        * `backend/apps/cards/templates/` contains the html files for the cards app
        * `backend/apps/cards/context_processors.py` contains data that can be called with double curly braces `{{}}` throughout the website (see `ai-playground/backend/apps/cards/templates/cards/partials/stats_widget.html` for example). This references the model (datatable) `Cards` which houses the data.
        * `backend/apps/cards/forms.py` contains the different forms that users can fill in for the `cards` app. This references the model (datatable) `Cards` which houses the data.
        * `backend/apps/cards/models.py` contains the different models (datatables) that contain the data for the `cards` app. This is where you define the datatables and their fields. If you updated your datatables or create new ones, rerun the commands in step 7 and **git commit `backend/apps/cards/migrations/*.py`**.
        * `backend/apps/cards/urls.py` contains the different urls for the `cards` app. These reference the different views that connect the Python to html templates.
        * `backend/apps/cards/views.py` contains the different views for the `cards` app. These connect the models, forms, and html templates to display the website.

#### `backend/`

As mentioned above, the `frontend/` directory only contains the React-TS project which is currently not being used at all.
