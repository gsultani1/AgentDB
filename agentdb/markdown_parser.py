"""
Markdown Authoring Layer for AgentDB.

Implements PRD Section 7:
- YAML frontmatter parsing and validation
- Four document types: memory, instruction, skill, knowledge
- Knowledge document chunking on heading boundaries
- Deduplication-aware update handling
- Reverse markdown generation from existing records
- File watcher with inbox/processed/failed directory structure
"""

import hashlib
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from agentdb import crud
from agentdb.embeddings import (
    generate_embedding,
    embedding_to_blob,
    cosine_similarity,
    semantic_search,
)


# ═══════════════════════════════════════════════════════════════════
# FRONTMATTER PARSING
# ═══════════════════════════════════════════════════════════════════

def parse_frontmatter(text):
    """
    Parse YAML frontmatter from a markdown document.

    Args:
        text: Full markdown text with --- delimited frontmatter.

    Returns:
        tuple of (frontmatter_dict, body_text)

    Raises:
        ValueError if frontmatter is missing or invalid.
    """
    text = text.strip()
    if not text.startswith("---"):
        raise ValueError("Document must begin with YAML frontmatter (---)")

    # Find the closing ---
    end_idx = text.find("---", 3)
    if end_idx == -1:
        raise ValueError("Frontmatter closing --- not found")

    frontmatter_raw = text[3:end_idx].strip()
    body = text[end_idx + 3:].strip()

    # Simple YAML parser (avoids PyYAML dependency)
    meta = _parse_simple_yaml(frontmatter_raw)

    if "type" not in meta:
        raise ValueError("Frontmatter must include 'type' field")

    valid_types = {"memory", "instruction", "skill", "knowledge"}
    if meta["type"] not in valid_types:
        raise ValueError(f"Invalid type '{meta['type']}'. Must be one of: {valid_types}")

    return meta, body


def _parse_simple_yaml(text):
    """
    Minimal YAML parser for frontmatter fields.
    Supports: key: value, key: [list, items], key: {obj}
    """
    result = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Parse lists: [item1, item2]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            result[key] = [item.strip().strip("'\"") for item in items if item.strip()]
        # Parse objects: {key: value}
        elif value.startswith("{") and value.endswith("}"):
            try:
                result[key] = json.loads(value.replace("'", '"'))
            except json.JSONDecodeError:
                result[key] = value
        # Parse booleans
        elif value.lower() in ("true", "false"):
            result[key] = value.lower() == "true"
        # Parse numbers
        elif value.isdigit():
            result[key] = int(value)
        # Parse quoted strings
        elif (value.startswith('"') and value.endswith('"')) or \
             (value.startswith("'") and value.endswith("'")):
            result[key] = value[1:-1]
        else:
            result[key] = value

    return result


def validate_frontmatter(meta):
    """
    Validate frontmatter fields based on document type.

    Args:
        meta: dict from parse_frontmatter.

    Returns:
        list of validation error strings (empty if valid).
    """
    errors = []
    doc_type = meta.get("type", "")

    if doc_type == "memory":
        valid_categories = {"fact", "relationship", "preference", "procedure"}
        cat = meta.get("category", "fact")
        if cat not in valid_categories:
            errors.append(f"Memory category must be one of: {valid_categories}")

    elif doc_type == "instruction":
        pass  # priority is optional

    elif doc_type == "skill":
        if "execution_type" not in meta:
            errors.append("Skill documents require 'execution_type' in frontmatter")
        else:
            valid_exec = {"prompt_template", "code_procedure", "tool_invocation", "composite"}
            if meta["execution_type"] not in valid_exec:
                errors.append(f"execution_type must be one of: {valid_exec}")

    elif doc_type == "knowledge":
        if "title" not in meta:
            errors.append("Knowledge documents require 'title' in frontmatter")

    return errors


# ═══════════════════════════════════════════════════════════════════
# DOCUMENT PROCESSING PIPELINE
# ═══════════════════════════════════════════════════════════════════

def process_markdown_document(conn, text, source_path=None):
    """
    Full processing pipeline for a markdown document.

    Args:
        conn: sqlite3.Connection
        text: Full markdown text with frontmatter.
        source_path: Optional file path for audit logging.

    Returns:
        dict with processing summary.
    """
    meta, body = parse_frontmatter(text)
    errors = validate_frontmatter(meta)
    if errors:
        return {"status": "error", "errors": errors}

    doc_type = meta["type"]

    if doc_type == "memory":
        return _process_memory_document(conn, meta, body)
    elif doc_type == "instruction":
        return _process_instruction_document(conn, meta, body)
    elif doc_type == "skill":
        return _process_skill_document(conn, meta, body)
    elif doc_type == "knowledge":
        return _process_knowledge_document(conn, meta, body)

    return {"status": "error", "errors": [f"Unknown type: {doc_type}"]}


def _process_memory_document(conn, meta, body):
    """Process a memory-type markdown document into long_term_memory."""
    category = meta.get("category", "fact")
    tags = meta.get("tags", [])
    entities = meta.get("entities", [])

    # Check for duplicate by embedding similarity
    emb = generate_embedding(body)
    emb_blob = embedding_to_blob(emb)

    existing_id = _find_duplicate(conn, "long_term_memory", emb, threshold=0.95)

    if existing_id:
        # Update existing
        crud.update_long_term_memory(
            conn, existing_id,
            content=body, embedding=emb_blob,
            category=category, last_validated=datetime.utcnow().isoformat(),
        )
        crud.create_audit_entry(
            conn, "long_term_memory", existing_id, "update", "markdown_import",
            after_snapshot={"content": body[:200]},
        )
        mem_id = existing_id
        action = "updated"
    else:
        # Create new
        entity_ids = _resolve_entity_references(conn, entities, emb)
        mem_id = crud.create_long_term_memory(
            conn, body, embedding=emb_blob,
            confidence=1.0, provenance="user_authored",
            entity_ids=entity_ids, category=category,
        )
        crud.create_audit_entry(
            conn, "long_term_memory", mem_id, "insert", "markdown_import",
            after_snapshot={"content": body[:200]},
        )
        action = "created"

    # Apply tags
    tag_ids = _ensure_tags(conn, tags)
    for tid in tag_ids:
        try:
            crud.create_tag_assignment(conn, tid, mem_id, "long_term_memory")
        except Exception:
            pass  # Already assigned or trigger error

    # Create entity relations
    _link_entities(conn, mem_id, "long_term_memory", entities)

    return {
        "status": "ok",
        "action": action,
        "type": "memory",
        "id": mem_id,
        "tags_applied": len(tag_ids),
        "entities_linked": len(entities),
    }


def _process_instruction_document(conn, meta, body):
    """Process an instruction-type markdown document into long_term_memory with category=directive."""
    tags = meta.get("tags", [])
    priority = meta.get("priority", "normal")

    emb = generate_embedding(body)
    emb_blob = embedding_to_blob(emb)

    existing_id = _find_duplicate(conn, "long_term_memory", emb, threshold=0.95)

    if existing_id:
        crud.update_long_term_memory(
            conn, existing_id,
            content=body, embedding=emb_blob,
            category="directive", last_validated=datetime.utcnow().isoformat(),
        )
        crud.create_audit_entry(
            conn, "long_term_memory", existing_id, "update", "markdown_import",
            after_snapshot={"content": body[:200], "priority": priority},
        )
        mem_id = existing_id
        action = "updated"
    else:
        mem_id = crud.create_long_term_memory(
            conn, body, embedding=emb_blob,
            confidence=1.0, provenance="user_authored",
            category="directive",
        )
        crud.create_audit_entry(
            conn, "long_term_memory", mem_id, "insert", "markdown_import",
            after_snapshot={"content": body[:200], "priority": priority},
        )
        action = "created"

    tag_ids = _ensure_tags(conn, tags)
    for tid in tag_ids:
        try:
            crud.create_tag_assignment(conn, tid, mem_id, "long_term_memory")
        except Exception:
            pass

    return {
        "status": "ok",
        "action": action,
        "type": "instruction",
        "id": mem_id,
        "tags_applied": len(tag_ids),
    }


def _process_skill_document(conn, meta, body):
    """Process a skill-type markdown document into skills + skill_implementations."""
    # Extract title from first heading or first line
    title_match = re.match(r"^#\s+(.+)", body)
    if title_match:
        skill_name = title_match.group(1).strip()
        body_after_title = body[title_match.end():].strip()
    else:
        lines = body.split("\n")
        skill_name = lines[0].strip() if lines else "Unnamed Skill"
        body_after_title = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    execution_type = meta.get("execution_type", "code_procedure")
    language = meta.get("language", "python")
    dependencies = meta.get("dependencies", [])
    input_schema = meta.get("input_schema")
    output_schema = meta.get("output_schema")
    tags = meta.get("tags", [])

    # Extract description (text before first code block)
    desc_match = re.split(r"```", body_after_title, maxsplit=1)
    description = desc_match[0].strip() if desc_match else body_after_title

    # Extract code blocks
    code_blocks = re.findall(r"```(\w*)\n(.*?)```", body, re.DOTALL)

    emb = generate_embedding(description if description else skill_name)
    emb_blob = embedding_to_blob(emb)

    # Check for existing skill by name or embedding similarity
    existing_skill = _find_skill_by_name(conn, skill_name)

    if existing_skill:
        skill_id = existing_skill["id"]
        new_version = existing_skill["version"] + 1
        crud.update_skill(
            conn, skill_id,
            description=description, embedding=emb_blob,
            version=new_version,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        action = "updated"
    else:
        skill_id = crud.create_skill(
            conn, skill_name, description or skill_name, execution_type,
            embedding=emb_blob, input_schema=input_schema,
            output_schema=output_schema,
        )
        new_version = 1
        action = "created"

    # Create implementations from code blocks
    impl_ids = []
    for order, (lang, code) in enumerate(code_blocks):
        lang = lang.strip() or language
        content_hash = hashlib.sha256(code.encode()).hexdigest()
        impl_id = crud.create_skill_implementation(
            conn, skill_id, new_version, lang, code.strip(),
            content_hash, dependencies=dependencies,
            is_active=(order == 0), execution_order=order,
        )
        impl_ids.append(impl_id)

    # If no code blocks, create a single implementation from the body
    if not code_blocks and body_after_title:
        content_hash = hashlib.sha256(body_after_title.encode()).hexdigest()
        impl_id = crud.create_skill_implementation(
            conn, skill_id, new_version, language, body_after_title,
            content_hash, dependencies=dependencies, is_active=True,
        )
        impl_ids.append(impl_id)

    crud.create_audit_entry(
        conn, "skills", skill_id, "insert" if action == "created" else "update",
        "markdown_import",
        after_snapshot={"name": skill_name, "version": new_version},
    )

    tag_ids = _ensure_tags(conn, tags)
    for tid in tag_ids:
        try:
            crud.create_tag_assignment(conn, tid, skill_id, "skills")
        except Exception:
            pass

    return {
        "status": "ok",
        "action": action,
        "type": "skill",
        "skill_id": skill_id,
        "skill_name": skill_name,
        "version": new_version,
        "implementations_created": len(impl_ids),
        "tags_applied": len(tag_ids),
    }


def _process_knowledge_document(conn, meta, body):
    """
    Process a knowledge-type markdown document.
    Chunk on heading boundaries, create parent entity, link chunks.
    """
    title = meta.get("title", "Untitled Document")
    tags = meta.get("tags", [])
    entities_list = meta.get("entities", [])

    # Create or find parent document entity
    parent_entity_id = _find_or_create_document_entity(conn, title)

    # Chunk the document on h2/h3 headings
    chunks = _chunk_on_headings(body, title)

    chunk_ids = []
    for chunk in chunks:
        emb = generate_embedding(chunk["content"])
        emb_blob = embedding_to_blob(emb)

        # Check for existing chunk by similarity
        existing_id = _find_duplicate(conn, "long_term_memory", emb, threshold=0.95)

        if existing_id:
            crud.update_long_term_memory(
                conn, existing_id,
                content=chunk["content"], embedding=emb_blob,
                last_validated=datetime.utcnow().isoformat(),
            )
            mem_id = existing_id
        else:
            mem_id = crud.create_long_term_memory(
                conn, chunk["content"], embedding=emb_blob,
                confidence=1.0, provenance="user_authored",
                category="fact",
            )

        chunk_ids.append(mem_id)

        # Link chunk to parent document entity
        try:
            crud.create_relation(
                conn, mem_id, "long_term_memory",
                parent_entity_id, "entities",
                "chunk_of", weight=1.0,
                context=f"Section: {chunk.get('heading', 'body')}",
            )
        except Exception:
            pass  # Relation may already exist

    # Link entities mentioned in frontmatter
    for entity_name in entities_list:
        _link_entity_by_name(conn, parent_entity_id, "entities", entity_name)

    # Apply tags to parent entity
    tag_ids = _ensure_tags(conn, tags)
    for tid in tag_ids:
        try:
            crud.create_tag_assignment(conn, tid, parent_entity_id, "entities")
        except Exception:
            pass

    # Also apply tags to each chunk
    for cid in chunk_ids:
        for tid in tag_ids:
            try:
                crud.create_tag_assignment(conn, tid, cid, "long_term_memory")
            except Exception:
                pass

    crud.create_audit_entry(
        conn, "entities", parent_entity_id, "insert", "markdown_import",
        after_snapshot={"title": title, "chunks": len(chunk_ids)},
    )

    return {
        "status": "ok",
        "action": "created",
        "type": "knowledge",
        "document_entity_id": parent_entity_id,
        "title": title,
        "chunks_created": len(chunk_ids),
        "chunk_ids": chunk_ids,
        "tags_applied": len(tag_ids),
        "entities_linked": len(entities_list),
    }


# ═══════════════════════════════════════════════════════════════════
# REVERSE MARKDOWN GENERATION
# ═══════════════════════════════════════════════════════════════════

def reverse_generate_markdown(conn, table, record_id):
    """
    Generate a markdown document from an existing database record.

    Args:
        conn: sqlite3.Connection
        table: str table name
        record_id: str record ID

    Returns:
        str markdown text with frontmatter, or None if not found.
    """
    if table == "long_term_memory":
        return _reverse_ltm(conn, record_id)
    elif table == "skills":
        return _reverse_skill(conn, record_id)
    return None


def _reverse_ltm(conn, record_id):
    """Reverse-generate markdown from a long-term memory."""
    mem = crud.get_long_term_memory(conn, record_id)
    if not mem:
        return None

    category = mem["category"]
    tags = crud.list_tag_assignments_for_target(conn, record_id, "long_term_memory")
    tag_names = [t["tag_name"] for t in tags]

    if category == "directive":
        doc_type = "instruction"
        lines = ["---"]
        lines.append("type: instruction")
        if tag_names:
            lines.append(f"tags: [{', '.join(tag_names)}]")
        lines.append("---")
        lines.append("")
        lines.append(mem["content"])
    else:
        doc_type = "memory"
        lines = ["---"]
        lines.append("type: memory")
        lines.append(f"category: {category}")
        if tag_names:
            lines.append(f"tags: [{', '.join(tag_names)}]")
        lines.append("---")
        lines.append("")
        lines.append(mem["content"])

    return "\n".join(lines)


def _reverse_skill(conn, record_id):
    """Reverse-generate markdown from a skill."""
    skill = crud.get_skill(conn, record_id)
    if not skill:
        return None

    tags = crud.list_tag_assignments_for_target(conn, record_id, "skills")
    tag_names = [t["tag_name"] for t in tags]
    impls = crud.list_skill_implementations(conn, record_id)
    active_impl = next((i for i in impls if i["is_active"]), None)

    lines = ["---"]
    lines.append("type: skill")
    lines.append(f"execution_type: {skill['execution_type']}")
    if active_impl:
        lines.append(f"language: {active_impl['language']}")
        deps = active_impl.get("dependencies")
        if deps:
            if isinstance(deps, str):
                deps = json.loads(deps)
            lines.append(f"dependencies: [{', '.join(deps)}]")
    if skill.get("input_schema"):
        schema = skill["input_schema"]
        if isinstance(schema, str):
            schema = json.loads(schema)
        lines.append(f"input_schema: {json.dumps(schema)}")
    if skill.get("output_schema"):
        schema = skill["output_schema"]
        if isinstance(schema, str):
            schema = json.loads(schema)
        lines.append(f"output_schema: {json.dumps(schema)}")
    if tag_names:
        lines.append(f"tags: [{', '.join(tag_names)}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {skill['name']}")
    lines.append("")
    lines.append(skill["description"])
    lines.append("")

    if active_impl:
        lines.append(f"```{active_impl['language']}")
        lines.append(active_impl["code"])
        lines.append("```")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# FILE WATCHER
# ═══════════════════════════════════════════════════════════════════

class MarkdownFileWatcher:
    """
    Watches a directory for new .md files and processes them through the pipeline.
    Uses polling for cross-platform compatibility.
    """

    def __init__(self, db_path):
        self._db_path = db_path
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        """Start the file watcher in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the file watcher."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _watch_loop(self):
        """Main polling loop."""
        from agentdb.database import get_connection

        while not self._stop_event.is_set():
            try:
                conn = get_connection(self._db_path)
                enabled = crud.get_config_value(conn, "markdown_watch_enabled", "false")

                if enabled != "true":
                    conn.close()
                    self._stop_event.wait(10)
                    continue

                inbox_path = crud.get_config_value(conn, "markdown_inbox_path", "")
                interval = int(crud.get_config_value(
                    conn, "markdown_watch_interval_seconds", "5"
                ))

                if not inbox_path or not os.path.isdir(inbox_path):
                    conn.close()
                    self._stop_event.wait(interval)
                    continue

                inbox = Path(inbox_path)
                processed_dir = inbox / "processed"
                failed_dir = inbox / "failed"
                processed_dir.mkdir(exist_ok=True)
                failed_dir.mkdir(exist_ok=True)

                # Find new .md files
                md_files = sorted(inbox.glob("*.md"))
                for md_file in md_files:
                    self._process_file(conn, md_file, processed_dir, failed_dir)

                conn.close()
                self._stop_event.wait(interval)

            except Exception:
                self._stop_event.wait(10)

    def _process_file(self, conn, md_file, processed_dir, failed_dir):
        """Process a single markdown file."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        try:
            text = md_file.read_text(encoding="utf-8")
            result = process_markdown_document(conn, text, source_path=str(md_file))

            if result.get("status") == "error":
                # Move to failed
                dest = failed_dir / f"{timestamp}_{md_file.name}"
                shutil.move(str(md_file), str(dest))
                # Write error log
                error_log = failed_dir / f"{timestamp}_{md_file.stem}.error.txt"
                error_log.write_text(
                    json.dumps(result, indent=2), encoding="utf-8"
                )
            else:
                # Move to processed
                dest = processed_dir / f"{timestamp}_{md_file.name}"
                shutil.move(str(md_file), str(dest))

        except Exception as e:
            dest = failed_dir / f"{timestamp}_{md_file.name}"
            try:
                shutil.move(str(md_file), str(dest))
            except Exception:
                pass
            error_log = failed_dir / f"{timestamp}_{md_file.stem}.error.txt"
            try:
                error_log.write_text(str(e), encoding="utf-8")
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def _find_duplicate(conn, table, embedding, threshold=0.95):
    """Find an existing record by embedding similarity above threshold."""
    rows = conn.execute(
        f"SELECT id, embedding FROM {table} WHERE embedding IS NOT NULL"
    ).fetchall()
    if not rows:
        return None

    candidates = [(r["id"], r["embedding"]) for r in rows]
    results = semantic_search(embedding, candidates, top_k=1)
    if results and results[0][1] >= threshold:
        return results[0][0]
    return None


def _find_skill_by_name(conn, name):
    """Find a skill by exact name match."""
    row = conn.execute(
        "SELECT * FROM skills WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        return dict(row)
    return None


def _ensure_tags(conn, tag_names):
    """Ensure tags exist and return their IDs."""
    tag_ids = []
    for name in tag_names:
        existing = crud.find_tag_by_name(conn, name)
        if existing:
            tag_ids.append(existing["id"])
        else:
            tid = crud.create_tag(conn, name)
            tag_ids.append(tid)
    return tag_ids


def _resolve_entity_references(conn, entity_names, content_embedding):
    """Resolve entity names to IDs, creating new entities as needed."""
    entity_ids = []
    for name in entity_names:
        found = crud.find_entity_by_name(conn, name)
        if found:
            entity_ids.append(found[0]["id"])
            # Update last_seen
            crud.update_entity(conn, found[0]["id"],
                               last_seen=datetime.utcnow().isoformat())
        else:
            emb = embedding_to_blob(generate_embedding(name))
            eid = crud.create_entity(conn, name, "concept", embedding=emb)
            entity_ids.append(eid)
    return entity_ids


def _link_entities(conn, source_id, source_table, entity_names):
    """Create relations between a source record and entities by name."""
    for name in entity_names:
        found = crud.find_entity_by_name(conn, name)
        if found:
            try:
                crud.create_relation(
                    conn, source_id, source_table,
                    found[0]["id"], "entities",
                    "related_to", weight=0.8,
                    context=f"Mentioned in {source_table}",
                )
            except Exception:
                pass


def _link_entity_by_name(conn, source_id, source_table, entity_name):
    """Link a single entity by name to a source record."""
    found = crud.find_entity_by_name(conn, entity_name)
    if found:
        try:
            crud.create_relation(
                conn, source_id, source_table,
                found[0]["id"], "entities",
                "related_to", weight=0.8,
            )
        except Exception:
            pass
    else:
        emb = embedding_to_blob(generate_embedding(entity_name))
        eid = crud.create_entity(conn, entity_name, "concept", embedding=emb)
        try:
            crud.create_relation(
                conn, source_id, source_table,
                eid, "entities",
                "related_to", weight=0.8,
            )
        except Exception:
            pass


def _find_or_create_document_entity(conn, title):
    """Find or create a document entity."""
    found = crud.find_entity_by_name(conn, title)
    if found:
        for e in found:
            if e.get("entity_type") == "concept":
                return e["id"]

    emb = embedding_to_blob(generate_embedding(title))
    eid = crud.create_entity(conn, title, "concept", embedding=emb)
    return eid


def _chunk_on_headings(body, document_title):
    """
    Split markdown body into chunks on h2/h3 boundaries.

    Returns list of dicts with 'heading' and 'content' keys.
    """
    lines = body.split("\n")
    chunks = []
    current_heading = document_title
    current_lines = []

    for line in lines:
        if re.match(r"^#{2,3}\s+", line):
            # Save previous chunk
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append({
                    "heading": current_heading,
                    "content": f"{current_heading}\n\n{content}",
                })
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Save final chunk
    content = "\n".join(current_lines).strip()
    if content:
        chunks.append({
            "heading": current_heading,
            "content": f"{current_heading}\n\n{content}",
        })

    # If no headings were found, return the whole body as one chunk
    if not chunks:
        chunks.append({
            "heading": document_title,
            "content": body.strip(),
        })

    return chunks
