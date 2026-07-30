from pathlib import Path
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

# MCP server setup
mcp = FastMCP("DocumentMCP", log_level="ERROR")

# Simple filesystem storage (./docs)
DOCS_DIR = Path("./docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)
_BASE = DOCS_DIR.resolve() 

def _doc_path(doc_id: str) -> Path:
    """Resolve a safe, absolute path within DOCS_DIR (prevents path traversal)."""
    p = (_BASE / doc_id).resolve()
    if _BASE not in p.parents and p != _BASE:
        raise ValueError("Invalid doc_id path")
    return p

def _read_text(doc_id: str) -> str:
    p = _doc_path(doc_id)
    if not p.exists():
        raise ValueError(f"Doc with id {doc_id} not found")

    ext = p.suffix.lower()

    # Plain text-like files
    if ext in {".txt", ".md", ".log", ".csv"}:
        return p.read_text(encoding="utf-8", errors="ignore")

    # PDF via pypdf
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            parts = []
            for page in reader.pages:
                t = page.extract_text() or ""
                if t:
                    parts.append(t)
            text = "\n".join(parts).strip()
            if not text:
                raise ValueError("No extractable text found in PDF (likely scanned).")
            return text
        except Exception as e:
            raise ValueError(f"Unable to extract text from PDF: {e}")

    # DOCX via python-docx
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(str(p))
            # Join paragraphs with newlines for readability
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        except Exception as e:
            raise ValueError(f"Unable to extract text from DOCX: {e}")

    # Fallback: try reading as UTF-8 text anyway
    return p.read_text(encoding="utf-8", errors="ignore")



def _write_text(doc_id: str, text: str) -> None:
    p = _doc_path(doc_id)
    p.write_text(text, encoding="utf-8")

# Tools
@mcp.tool(
    name="read_doc_contents",
    description="Read the contents of a document and return it as a string."
)
def read_document(
    doc_id: str = Field(description="Id of the document to read")
):
    return _read_text(doc_id)

@mcp.tool(
    name="edit_document",
    description="Edit a document by replacing a string in the document's content with a new string."
)
def edit_document(
    doc_id: str = Field(description="Id of the document that will be edited"),
    old_str: str = Field(description="The text to replace. Must match exactly, including whitespace."),
    new_str: str = Field(description="The new text to insert in place of the old text.")
):
    text = _read_text(doc_id)
    updated = text.replace(old_str, new_str)
    _write_text(doc_id, updated)
    return updated

# Resources
@mcp.resource("docs://documents", mime_type="application/json")
def list_docs() -> list[str]:
    """List all file names under ./docs (files only)."""
    return sorted([p.name for p in DOCS_DIR.iterdir() if p.is_file()])

@mcp.resource("docs://documents/{doc_id}", mime_type="text/plain")
def fetch_doc(doc_id: str) -> str:
    """Return the text contents of a specific document."""
    return _read_text(doc_id)

# Prompts
@mcp.prompt(
    name="format",
    description="Rewrites the contents of the document in Markdown format"
)
def format_document(
    doc_id: str = Field(description="Id of the document to format"),
) -> list[base.Message]:
    prompt = f"""
Your goal is to reformat a document to be written with markdown syntax.

The id of the document you need to reformat is:
<document_id>
{doc_id}
</document_id>

Add in headers, bullet points, tables, etc as necessary. Feel free to add in structure.
Use the 'edit_document' tool to edit the document. After the document has been reformatted...
"""
    return [base.UserMessage(prompt)]

@mcp.prompt(
    name="summarize",
    description="Summarizes a document to its key points."
)
def summarize_document(
    doc_id: str = Field(description="Id of the document to summarize")
) -> list[base.Message]:
    prompt = f"""
Your goal is to summarize the contents of a document.

The id of the document you need to summarize is:
<document_id>
{doc_id}
</document_id>

Read the document carefully, and then respond with a concise summary of its key points.
Do not include any extra commentary.
"""
    return [base.UserMessage(prompt)]

@mcp.prompt(
    name="outline",
    description="Creates a structured outline of a document."
)
def outline_document(
    doc_id: str = Field(description="Id of the document to outline")
) -> list[base.Message]:
    prompt = f"""
Your goal is to create a clear, structured outline of a document.

The id of the document you need to outline is:
<document_id>
{doc_id}
</document_id>

Steps:
1. Read the document carefully.
2. Identify the main sections or themes.
3. Produce an outline using nested bullet points.

Format your response like this:

- Title / Main topic
- Section 1: ...
  - Key idea 1
  - Key idea 2
- Section 2: ...
  - Key idea 1
  - etc.

Do not include extra commentary outside of the outline itself.
"""
    return [base.UserMessage(prompt)]

@mcp.prompt(
    name="import",
    description="Explains how to use the /import CLI command to add documents."
)
def import_help() -> list[base.Message]:
    prompt = """
You are a helper for the CLI document tool.

Explain briefly how the user can use the /import command in the CLI.
The syntax is:

/import <source_path> <doc_id>

- source_path is a full path to a local file (e.g., /Users/name/Desktop/file.docx)
- doc_id is how the file will be named inside the docs/ folder (e.g., file.docx)

Clarify that the actual import is handled by the CLI, not by this server, and
that this prompt exists mainly so /import shows up in the autocomplete list.
"""
    return [base.UserMessage(prompt)]


@mcp.prompt(
    name="docs",
    description="Explains how to list documents with the /docs CLI command."
)
def docs_help() -> list[base.Message]:
    prompt = """
You are a helper for the CLI document tool.

Explain briefly how the user can use the /docs command in the CLI
to list all documents currently stored in the docs/ folder.

Clarify that /docs is a CLI-level command and this prompt exists
mainly so it appears in the autocomplete menu.
"""
    return [base.UserMessage(prompt)]


@mcp.prompt(
    name="delete",
    description="Explains the safe delete flow using /delete in the CLI."
)
def delete_help() -> list[base.Message]:
    prompt = """
You are a helper for the CLI document tool.

Explain how the user can delete a document safely using:

/delete <doc_id>

Describe that the CLI will ask for confirmation:
- User types /delete some.docx
- CLI asks: "Are you sure you want to delete 'some.docx'? (yes/no)"
- Typing yes deletes it, typing no cancels.

Clarify that deletion is handled by the CLI, not this server.
"""
    return [base.UserMessage(prompt)]


@mcp.prompt(
    name="rename",
    description="Explains how to rename a document with /rename in the CLI."
)
def rename_help() -> list[base.Message]:
    prompt = """
You are a helper for the CLI document tool.

Explain briefly how to use:

/rename <old_doc_id> <new_doc_id>

Mention that:
- Both names must be simple filenames (no slashes or '..')
- The file is renamed inside the docs/ folder only
- This behavior is implemented in the CLI; this prompt mainly ensures
  that /rename shows up in autocomplete.
"""
    return [base.UserMessage(prompt)]

@mcp.prompt(
    name="info",
    description="Explains how to view document info using the /info CLI command."
)
def info_help() -> list[base.Message]:
    prompt = """
You are a helper for the CLI document tool.

Explain briefly how to use the /info command:

/info <doc_id>

This command displays:
- file size
- last modified date
- extension/type
- line count
- character count
- a short preview

Clarify that the actual logic is implemented in the CLI; this prompt exists so /info appears in autocomplete.
"""
    return [base.UserMessage(prompt)]


# Entry point
if __name__ == "__main__":
    mcp.run(transport="stdio")

