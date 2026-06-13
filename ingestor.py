"""
Ingestor — document parsing, chunking, embedding, and storage.

Handles PDF, DOCX, URL, and plain text ingestion into ChromaDB
with automatic tagging and scoped collections.
"""

from dotenv import load_dotenv
load_dotenv()

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from docx import Document
from features.tagger import auto_tag
import requests

# ── Shared resources ───────────────────────────────────────────────────

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
splitter   = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)


def get_vectorstore(collection_name="org"):
    """Get (or create) a ChromaDB collection."""
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory="./chroma_db",
    )


# ── Scope routing ──────────────────────────────────────────────────────

def get_target_collection(user_id, channel_id=None, org_wide=False):
    """
    Route content to the right collection based on context.

      org_wide=True      → "org"
      DM / no channel    → "user_{user_id}"
      channel message    → "team_{channel_id}"
    """
    if org_wide:
        return "org"
    if not channel_id or channel_id.startswith("D"):
        return f"user_{user_id}"
    return f"team_{channel_id}"


# ── Core ingestion ─────────────────────────────────────────────────────

def ingest_text(text, metadata, collection_name="org"):
    """Chunk, auto-tag, embed, and store text."""
    tags = auto_tag(text)
    metadata["tags"] = ", ".join(tags)

    chunks    = splitter.split_text(text)
    metadatas = [{**metadata} for _ in chunks]

    db = get_vectorstore(collection_name)
    db.add_texts(chunks, metadatas=metadatas)
    return len(chunks), tags


# ── Parsers ────────────────────────────────────────────────────────────

def parse_pdf(file_path):
    """Extract text from a PDF file."""
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(file_path):
    """Extract text from a DOCX file."""
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs)


def parse_url(url):
    """Scrape and extract text from a web page."""
    from bs4 import BeautifulSoup
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.get_text(separator="\n")


# ── Browse helpers ─────────────────────────────────────────────────────

def list_sources_by_tag(tag, collection_name="org"):
    """List source names matching a tag (case-insensitive substring)."""
    db = get_vectorstore(collection_name)
    try:
        results = db.get()
    except Exception:
        return []

    sources = set()
    for meta in results.get("metadatas", []):
        if meta and tag.lower() in meta.get("tags", "").lower():
            sources.add(meta.get("source", "unknown"))
    return sorted(sources)


def list_all_sources(collection_name="org"):
    """List all unique sources with their tags. Returns {source: tags}."""
    db = get_vectorstore(collection_name)
    try:
        results = db.get()
    except Exception:
        return {}

    seen = {}
    for meta in results.get("metadatas", []):
        if meta:
            src = meta.get("source", "unknown")
            if src not in seen:
                seen[src] = meta.get("tags", "Untagged")
    return seen