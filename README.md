# MCP Client-Server Framework

A command-line document assistant built with Python, Anthropic Claude, and the
Model Context Protocol (MCP). The application starts a local MCP server, exposes
documents as MCP resources, gives Claude access to document tools, and provides
an interactive terminal interface with command and document autocomplete.

## Features

- Interactive conversations with Claude
- MCP client and local stdio MCP server
- Support for connecting additional MCP server scripts
- Document references using `@filename`
- Slash-command and document-name autocomplete
- Document import, listing, metadata, rename, and confirmed deletion
- MCP prompt templates for summarizing, outlining, and formatting documents
- Text extraction from Markdown, text, CSV, PDF, and DOCX files

## Requirements

- Python 3.10 or newer
- An Anthropic API key
- [`uv`](https://docs.astral.sh/uv/) (recommended), or `pip`

## Setup

### 1. Configure environment variables

Create a `.env` file in the project root:

```dotenv
ANTHROPIC_API_KEY="your-api-key"
CLAUDE_MODEL="your-claude-model"

# Use 1 to launch the local MCP server with uv, or 0 to use python.
USE_UV="1"
```

The `.env` file is ignored by Git. Never commit API keys.

### 2. Install dependencies

Using `uv`:

```bash
uv sync
```

Using a standard virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

PDF and DOCX extraction additionally require:

```bash
pip install pypdf python-docx
```

### 3. Run the application

With `uv`:

```bash
uv run main.py
```

Without `uv`, set `USE_UV="0"` and run:

```bash
python main.py
```

The application uses paths relative to the current working directory, so run it
from the project root.

## Usage

Enter a normal question to chat with Claude:

```text
> How can you help me analyze these documents?
```

Reference one or more files in `docs/` with `@`:

```text
> What are the main risks in @spec.txt?
```

Press Tab to use command and document autocomplete.

### Commands

| Command | Description |
| --- | --- |
| `/help` | Show command help |
| `/docs` | List files in `docs/` |
| `/import <source_path> <doc_id>` | Copy a local file into `docs/` |
| `/info <doc_id>` | Show file metadata and a text preview |
| `/summarize <doc_id>` | Summarize a document using Claude |
| `/outline <doc_id>` | Produce a structured document outline |
| `/format <doc_id>` | Ask Claude to reformat a document as Markdown |
| `/rename <old_doc_id> <new_doc_id>` | Rename a document |
| `/delete <doc_id>` | Delete a document after confirmation |

Examples:

```text
> /docs
> /import /Users/you/Desktop/report.docx report.docx
> /info report.docx
> /summarize report.docx
> /outline report.docx
> /rename report.docx report-final.docx
> /delete report-final.docx
```

## Connecting Additional MCP Servers

Pass MCP server script paths after `main.py`:

```bash
uv run main.py path/to/another_server.py
```

Each additional script is started with `uv run`. Its tools are discovered and
made available to Claude alongside the local document tools.

## Architecture

```text
main.py
├── CliApp                 interactive prompt and autocomplete
├── CliChat                commands and document-reference handling
├── Claude                 Anthropic Messages API wrapper
└── MCPClient
    ├── mcp_server.py      local document resources, prompts, and tools
    └── optional servers   extra MCP tools supplied on the command line
```

Important files:

- `main.py` initializes the services and starts the CLI.
- `core/cli.py` implements the terminal interface and autocomplete.
- `core/cli_chat.py` implements local commands and document context.
- `core/chat.py` runs the Claude tool-use loop.
- `core/tools.py` discovers MCP tools and routes tool calls.
- `core/claude.py` wraps the Anthropic Messages API.
- `mcp_client.py` manages stdio MCP sessions.
- `mcp_server.py` exposes the `docs/` directory through MCP.

## MCP Capabilities

The local server provides:

- Resources:
  - `docs://documents`
  - `docs://documents/{doc_id}`
- Tools:
  - `read_doc_contents`
  - `edit_document`
- Prompts:
  - `summarize`
  - `outline`
  - `format`
  - command-help prompts used by autocomplete

## Supported Document Types

| Type | Reading |
| --- | --- |
| `.txt`, `.md`, `.log`, `.csv` | Native UTF-8 text |
| `.pdf` | Text extraction with `pypdf` |
| `.docx` | Paragraph extraction with `python-docx` |
| Other extensions | Best-effort UTF-8 decoding |

Scanned PDFs require OCR, which is not currently included.

## Current Limitations

- There is no automated test, lint, or type-check configuration.
- Conversation history remains in memory only.
- Large referenced documents are inserted directly into the Claude context.
- `edit_document` writes plain text. It should only be used with text-based
  files; using it on PDF or DOCX files does not preserve their native format.

## Development

Add documents by placing files in `docs/` or by using `/import`.

To add MCP functionality, define additional resources, tools, or prompts in
`mcp_server.py`. To integrate another server without changing the local server,
pass its Python script when starting `main.py`.
