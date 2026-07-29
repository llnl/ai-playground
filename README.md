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
