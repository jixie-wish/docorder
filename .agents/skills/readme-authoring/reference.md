# README reference

Sources: [Create a README File for Your Git Repo — Azure Repos](https://learn.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops), GitHub's [`create-readme` skill](https://github.com/github/awesome-copilot/blob/main/skills/create-readme/SKILL.md), and the Azure-Samples READMEs it cites (e.g. [serverless-chat-langchainjs](https://github.com/Azure-Samples/serverless-chat-langchainjs)).

## Why a README matters

On GitHub and Azure Repos, the README is the default landing page. Viewers decide in seconds whether they can run, build, or contribute to the project. Contributors are also developers and users — every section should reduce friction for someone new to the repo.

## GFM admonition syntax

Use sparingly, only for the one or two things a reader must not miss:

```markdown
> [!NOTE]
> Useful context that doesn't block progress.

> [!TIP]
> An optional shortcut, e.g. a faster local-dev path.

> [!IMPORTANT]
> Something the reader needs to succeed, e.g. a required version pin.

> [!WARNING]
> A footgun: data loss, breaking change, irreversible action.
```

Reference: [GitHub Docs — basic writing and formatting syntax, alerts](https://github.com/orgs/community/discussions/16925).

## Section templates

### Introduction (template)

```markdown
<div align="center">
  <img src="./docs/logo.png" alt="" height="64" />

# Project Name

Short description of what this project does and who it is for.

</div>

[Optional: screenshot or GIF](./docs/images/screenshot.png)

**Requirements:** Node 20+, Docker, access to ...

**Platforms:** Linux, macOS, Windows (WSL2)
```

Keep the logo/badge block minimal — a handful of build/version/license badges is fine, but don't let it dominate the page.

### Getting the code (template)

```markdown
## Getting the code

\`\`\`bash
git clone https://github.com/org/project-name.git
cd project-name
\`\`\`

> [!TIP]
> You can also open this project directly in [GitHub Codespaces](https://codespaces.new/org/project-name) or with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension — no local toolchain needed.
```

If the remote or org name contains spaces (common with some Azure DevOps project names), say so explicitly and give the corrected command:

```markdown
> [!IMPORTANT]
> The default clone target contains spaces (`Org Name/Project Name`), which can break npm scripts and some shells. Clone into a plain folder name instead:
>
> \`\`\`bash
> git clone "https://example@dev.azure.com/example/Project%20Name/_git/repo%20name" repo-name
> \`\`\`
```

If the repo uses submodules or Git LFS, add the extra init step right after clone:

```markdown
\`\`\`bash
git submodule update --init --recursive
\`\`\`
```

### Prerequisites (template)

```markdown
## Prerequisites

- [Node.js 20+](https://nodejs.org/) — pinned via [Volta](https://volta.sh/) (see `volta` in `package.json`)
- [Docker](https://www.docker.com/products/docker-desktop) — required for the local database container

> [!IMPORTANT]
> Install Volta rather than relying on a system Node install. This repo pins an exact Node version; a mismatched version can break native modules (e.g. prebuilt binaries tied to a specific Node ABI), which shows up as obscure runtime errors in the dev server rather than an install failure.

**Install Volta:**

- **Windows**: `winget install Volta.Volta`, then restart your terminal.
- **macOS/Linux**: `curl https://get.volta.sh | bash`, then restart your terminal.

Verify: `volta --version`, then `npm install` — Volta fetches and pins the correct Node version automatically.
```

### Getting started / development server (template)

```markdown
## Getting started

\`\`\`bash
npm install
npm start
\`\`\`

Open http://localhost:3000 — you should see ...

This runs the app in **development mode** with hot reload. For a production build, see [Build and deploy](#build-and-deploy).
```

### Library/API minimal example

```markdown
## Usage

\`\`\`python
from mylib import greet

print(greet("world"))
\`\`\`

Expected output:

\`\`\`
Hello, world!
\`\`\`
```

### Build and deploy (template)

```markdown
## Build and deploy

\`\`\`bash
npm run build
npm test
\`\`\`

Detailed build notes: [docs/build.md](docs/build.md)

To deploy: `npm run deploy` (see [docs/deploy.md](docs/deploy.md) for environment setup).
```

### Contributing (template)

```markdown
## Contributing

- **Bugs and features:** [Open an issue](https://...)
- **Pull requests:** See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, tests, and review rules.
- **Questions:** ...

Released under the [MIT License](LICENSE).
```

## When to split documentation

Move content out of the README when:

- Setup has many conditional paths (OS, cloud env, secrets).
- Build or deploy instructions exceed ~15–20 lines.
- Architecture or design docs would dominate the landing page.

Keep the README as an index: one paragraph plus a link per topic.

## Azure Repos notes

- README renders from the default branch (often `main` or `develop`).
- Standard GitHub-flavored Markdown works for most content; Azure DevOps wiki has some extra Markdown features.
- For org-private repos, avoid pasting secrets; link to internal wiki pages for credential setup instead.
