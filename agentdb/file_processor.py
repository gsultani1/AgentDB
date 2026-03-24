"""
File attachment processing for AgentDB v1.5.

Handles file upload, content extraction, chunking, and ingestion into
short-term memory. Supports PDF, plain text, code files, and CSV.
"""

import json
import os

from agentdb import crud
from agentdb.embeddings import generate_embedding, embedding_to_blob


# Maximum characters per chunk for STM ingestion
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def process_file_attachment(conn, file_path, filename=None, session_id=None,
                            thread_id=None, agent_id="default"):
    """
    Process an uploaded file: extract content, chunk, embed, and ingest into STM.

    Args:
        conn: sqlite3.Connection
        file_path: path to the file on disk
        filename: original filename (defaults to basename of file_path)
        session_id: current session ID
        thread_id: current thread ID
        agent_id: agent performing the upload

    Returns:
        dict with attachment_id, chunk_count, stm_ids, token_estimate
    """
    if filename is None:
        filename = os.path.basename(file_path)

    # Detect MIME type and extraction method
    mime_type, extraction_method = _detect_file_type(filename)

    # Read and extract content
    extracted_text = _extract_content(file_path, extraction_method)
    size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Generate embedding for the full extracted text (truncated if too long)
    summary_text = extracted_text[:2000] if extracted_text else filename
    embedding = embedding_to_blob(generate_embedding(summary_text))

    # Chunk the content for STM ingestion
    chunks = _chunk_text(extracted_text, CHUNK_SIZE, CHUNK_OVERLAP)
    stm_ids = []

    for i, chunk in enumerate(chunks):
        chunk_emb = embedding_to_blob(generate_embedding(chunk))
        stm_id = crud.create_short_term_memory(
            conn, chunk, "file_upload",
            embedding=chunk_emb,
            session_id=session_id,
            agent_id=agent_id,
            ttl_seconds=86400,  # 24-hour TTL for file content
        )
        stm_ids.append(stm_id)

    # Create file_attachments record
    attachment_id = crud.create_file_attachment(
        conn,
        filename=filename,
        session_id=session_id,
        thread_id=thread_id,
        mime_type=mime_type,
        size_bytes=size_bytes,
        extraction_method=extraction_method,
        extracted_text=extracted_text,
        extracted_embedding=embedding,
        chunk_count=len(chunks),
        stm_ids=stm_ids,
        retained_path=file_path,
    )

    # Update STM entries with attachment_ids
    for stm_id in stm_ids:
        conn.execute(
            "UPDATE short_term_memory SET attachment_ids = ? WHERE id = ?",
            (json.dumps([attachment_id]), stm_id),
        )
    conn.commit()

    # Rough token estimate (1 token ~ 4 chars)
    token_estimate = len(extracted_text) // 4 if extracted_text else 0

    return {
        "attachment_id": attachment_id,
        "filename": filename,
        "mime_type": mime_type,
        "extraction_method": extraction_method,
        "chunk_count": len(chunks),
        "stm_ids": stm_ids,
        "token_estimate": token_estimate,
        "size_bytes": size_bytes,
    }


def process_file_from_content(conn, content_bytes, filename, session_id=None,
                               thread_id=None, agent_id="default", upload_dir=None):
    """
    Process a file from raw bytes (e.g., from a base64 upload).

    Writes to a temp file in upload_dir, then delegates to process_file_attachment.
    """
    if upload_dir is None:
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    return process_file_attachment(
        conn, file_path, filename=filename,
        session_id=session_id, thread_id=thread_id, agent_id=agent_id,
    )


def _detect_file_type(filename):
    """Detect MIME type and extraction method from filename."""
    ext = os.path.splitext(filename)[1].lower()

    type_map = {
        ".pdf": ("application/pdf", "pdf"),
        ".txt": ("text/plain", "text"),
        ".md": ("text/markdown", "text"),
        ".csv": ("text/csv", "text"),
        ".json": ("application/json", "code"),
        ".py": ("text/x-python", "code"),
        ".js": ("text/javascript", "code"),
        ".ts": ("text/typescript", "code"),
        ".html": ("text/html", "code"),
        ".css": ("text/css", "code"),
        ".xml": ("text/xml", "code"),
        ".yaml": ("text/yaml", "code"),
        ".yml": ("text/yaml", "code"),
        ".sql": ("text/x-sql", "code"),
        ".sh": ("text/x-shellscript", "code"),
        ".rs": ("text/x-rust", "code"),
        ".go": ("text/x-go", "code"),
        ".java": ("text/x-java", "code"),
        ".c": ("text/x-c", "code"),
        ".cpp": ("text/x-c++", "code"),
        ".h": ("text/x-c", "code"),
        ".rb": ("text/x-ruby", "code"),
        ".toml": ("text/toml", "code"),
        ".ini": ("text/ini", "code"),
        ".cfg": ("text/plain", "text"),
        ".log": ("text/plain", "text"),
    }

    if ext in type_map:
        return type_map[ext]
    return ("application/octet-stream", "raw")


def _extract_content(file_path, extraction_method):
    """Extract text content from a file using the appropriate method."""
    if extraction_method == "pdf":
        return _extract_pdf(file_path)
    elif extraction_method in ("text", "code"):
        return _extract_text(file_path)
    elif extraction_method == "raw":
        return _extract_text(file_path)  # Best effort
    return ""


def _extract_pdf(file_path):
    """Extract text from a PDF file using pdfminer.six."""
    try:
        from pdfminer.high_level import extract_text
        return extract_text(file_path)
    except ImportError:
        # Fallback: try to read as text
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return "[PDF extraction requires pdfminer.six: pip install pdfminer.six]"
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def _extract_text(file_path):
    """Extract text from a plain text or code file."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            last_para = chunk.rfind("\n\n")
            if last_para > chunk_size * 0.5:
                end = start + last_para + 2
                chunk = text[start:end]
            else:
                # Look for sentence break
                last_period = chunk.rfind(". ")
                if last_period > chunk_size * 0.5:
                    end = start + last_period + 2
                    chunk = text[start:end]

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if c]
