from typing import List, Tuple
from mcp.types import Prompt, PromptMessage
from anthropic.types import MessageParam

from core.chat import Chat
from core.claude import Claude
from mcp_client import MCPClient
from pathlib import Path
import shutil
import time

DOCS_DIR = Path("docs")


class CliChat(Chat):
    def __init__(
        self,
        doc_client: MCPClient,
        clients: dict[str, MCPClient],
        claude_service: Claude,
    ):
        super().__init__(clients=clients, claude_service=claude_service)
        self.doc_client: MCPClient = doc_client
        self.pending_delete: str | None = None

        # Always seed conversation with 1 message
        self.messages.append(
            {
                "role": "user",
                "content": (
                    "You are a helpful document assistant. "
                    "I will import, inspect, edit, and analyze documents using CLI commands."
                ),
            }
        )

    async def list_prompts(self) -> list[Prompt]:
        return await self.doc_client.list_prompts()

    async def list_docs_ids(self) -> list[str]:
        return await self.doc_client.read_resource("docs://documents")

    async def get_doc_content(self, doc_id: str) -> str:
        return await self.doc_client.read_resource(f"docs://documents/{doc_id}")

    async def get_prompt(self, command: str, doc_id: str) -> list[PromptMessage]:
        return await self.doc_client.get_prompt(command, {"doc_id": doc_id})

    async def _extract_resources(self, query: str) -> str:
        mentions = [word[1:] for word in query.split() if word.startswith("@")]
        doc_ids = await self.list_docs_ids()
        mentioned_docs: list[Tuple[str, str]] = []

        for doc_id in doc_ids:
            if doc_id in mentions:
                content = await self.get_doc_content(doc_id)
                mentioned_docs.append((doc_id, content))

        return "".join(
            f'\n<document id="{doc_id}">\n{content}\n</document>\n'
            for doc_id, content in mentioned_docs
        )

    async def _process_command(self, query: str) -> bool:
        if self.pending_delete:
            return False

        if not query.startswith("/"):
            return False

        words = query.strip().split()
        command = words[0][1:].lower()

        # --------------------------
        # /help
        # --------------------------
        if command == "help":
            print(
                """
Available commands:

  /help
    Show this help message.

  /docs
    List all documents currently stored in the docs/ directory.

  /import <source_path> <doc_id>
    Import a local file into docs/.
    Example:
      /import /Users/you/Desktop/report.docx report.docx

  /info <doc_id>
    Show metadata and a short text preview for the document.
    Example:
      /info report.docx

  /summarize <doc_id>
    Summarize the document's key points using the MCP server.
    Example:
      /summarize report.docx

  /outline <doc_id>
    Create a structured outline of the document.
    Example:
      /outline report.docx

  /format <doc_id>
    Reformat the document content into clean Markdown.
    Example:
      /format report.docx

  /rename <old_doc_id> <new_doc_id>
    Rename a document inside docs/.
    Example:
      /rename report.docx report_final.docx

  /delete <doc_id>
    Delete a document from docs/ (asks for confirmation).
    Example:
      /delete report_final.docx

You can also ask normal questions and mention documents using @docname,
for example:
  What are the main risks in @ss.docx?
                """.strip()
            )
            return True

        # --------------------------
        # /import
        # --------------------------
        if command == "import":
            if len(words) < 3:
                print("Usage: /import <source_path> <doc_id>")
                return True

            source_path = Path(words[1]).expanduser()
            doc_id = words[2]

            if "/" in doc_id or "\\" in doc_id or ".." in doc_id:
                print("Error: doc_id must be a simple filename.")
                return True

            if not source_path.exists():
                print(f"Error: source file not found: {source_path}")
                return True

            DOCS_DIR.mkdir(exist_ok=True)
            dest_path = DOCS_DIR / doc_id

            if dest_path.exists():
                print(f"Warning: {doc_id} exists and will be overwritten.")

            shutil.copy2(source_path, dest_path)
            print(f"Imported {source_path} → docs/{doc_id}")
            print(f"You can now run: /summarize {doc_id}")

            self.messages.append(
                {
                    "role": "user",
                    "content": f"I imported {doc_id}. Suggest next steps like summarizing or outlining it.",
                }
            )
            return True

        # --------------------------
        # /delete (safe delete)
        # --------------------------
        if command == "delete":
            if len(words) < 2:
                print("Usage: /delete <doc_id>")
                return True

            doc_id = words[1]
            path = DOCS_DIR / doc_id

            if not path.exists():
                print(f"Error: Document '{doc_id}' does not exist.")
                return True

            self.pending_delete = doc_id
            print(f"Are you sure you want to delete '{doc_id}'? (yes/no)")
            return True

        # --------------------------
        # /docs
        # --------------------------
        if command == "docs":
            try:
                docs = await self.list_docs_ids()
            except Exception as e:
                print(f"Error listing docs: {e}")
                return True

            if not docs:
                print("No documents found in docs/")
            else:
                print("Documents in docs/:")
                for d in docs:
                    print(f"- {d}")

            self.messages.append(
                {
                    "role": "user",
                    "content": "I listed the documents. Acknowledge without repeating them.",
                }
            )
            return True

        # --------------------------
        # /rename
        # --------------------------
        if command == "rename":
            if len(words) < 3:
                print("Usage: /rename <old> <new>")
                return True

            old = words[1]
            new = words[2]

            if any(x in new for x in ("/", "\\", "..")) or any(
                x in old for x in ("/", "\\", "..")
            ):
                print("Error: filenames cannot contain slashes or '..'")
                return True

            old_path = DOCS_DIR / old
            new_path = DOCS_DIR / new

            if not old_path.exists():
                print(f"Error: '{old}' does not exist.")
                return True
            if new_path.exists():
                print(f"Error: '{new}' already exists.")
                return True

            old_path.rename(new_path)
            print(f"Renamed '{old}' → '{new}'")

            self.messages.append(
                {
                    "role": "user",
                    "content": f"I renamed the document from {old} to {new}.",
                }
            )
            return True

        # --------------------------
        # /info
        # --------------------------
        if command == "info":
            if len(words) < 2:
                print("Usage: /info <doc_id>")
                return True

            doc_id = words[1]
            path = DOCS_DIR / doc_id

            if not path.exists():
                print(f"Error: '{doc_id}' does not exist.")
                return True

            stats = path.stat()
            size_kb = stats.st_size / 1024
            modified = time.ctime(stats.st_mtime)
            ext = path.suffix.lower()

            # Use MCP to get readable text (handles .docx, .pdf, etc.)
            try:
                content = await self.get_doc_content(doc_id)
            except Exception:
                content = ""

            num_lines = content.count("\n") + 1 if content else 0
            num_chars = len(content)
            preview = (
                "\n".join(content.splitlines()[:5]) if content else "(No preview available)"
            )

            print(f"\nInformation for: {doc_id}")
            print("--------------------------------------")
            print(f"Full path:       {path}")
            print(f"Size:            {size_kb:.2f} KB")
            print(f"Extension:       {ext}")
            print(f"Last modified:   {modified}")
            print(f"Lines:           {num_lines}")
            print(f"Characters:      {num_chars}")
            print("Preview:")
            print("--------------------------------------")
            print(preview)
            print("--------------------------------------\n")

            self.messages.append(
                {
                    "role": "user",
                    "content": (
                        f"I checked the metadata for {doc_id}. "
                        "Recommend the next type of analysis."
                    ),
                }
            )
            return True

        # --------------------------
        # MCP prompt commands
        # --------------------------
        if len(words) < 2:
            print("Usage: /<prompt> <doc_id>")
            return True

        doc_id = words[1]

        try:
            messages = await self.get_prompt(command, doc_id)
        except Exception as e:
            print(f"Error calling prompt: {e}")
            return True

        self.messages += convert_prompt_messages_to_message_params(messages)
        return True

    async def _process_query(self, query: str):
        # ---------- Deletion confirmation ----------
        if self.pending_delete:
            doc_id = self.pending_delete
            answer = query.strip().lower()

            if answer == "yes":
                path = DOCS_DIR / doc_id
                if path.exists():
                    path.unlink()
                    print(f"Deleted document: {doc_id}")

                self.messages.append(
                    {
                        "role": "user",
                        "content": f"I deleted the document {doc_id}.",
                    }
                )
                self.pending_delete = None
                return

            elif answer == "no":
                print("Deletion cancelled.")
                self.pending_delete = None
                return

            else:
                print("Please type 'yes' or 'no'.")
                return

        # ---------- Slash commands ----------
        if await self._process_command(query):
            return

        # ---------- Standard question -> Claude ----------
        added = await self._extract_resources(query)

        prompt = f"""
        The user has a question:
        <query>
        {query}
        </query>

        Context:
        <context>
        {added}
        </context>

        Give a direct answer.
        """

        self.messages.append({"role": "user", "content": prompt})


# -------------------------
# Helpers
# -------------------------
def convert_prompt_message_to_message_param(
    prompt_message: "PromptMessage",
) -> MessageParam:
    role = "user" if prompt_message.role == "user" else "assistant"
    content = prompt_message.content

    if isinstance(content, dict):
        if content.get("type") == "text":
            return {"role": role, "content": content.get("text", "")}

    if isinstance(content, list):
        texts = [
            {"type": "text", "text": item.get("text", "")}
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if texts:
            return {"role": role, "content": texts}

    return {"role": role, "content": ""}


def convert_prompt_messages_to_message_params(
    prompt_messages: List[PromptMessage],
) -> List[MessageParam]:
    return [convert_prompt_message_to_message_param(msg) for msg in prompt_messages]
