"""
Retriever — search the knowledge base, generate answers, and summarise.

Uses ChromaDB for vector search and Groq LLM for answer generation.
Returns Slack Block Kit formatted responses.
"""

from langchain_groq import ChatGroq
from ingestor import get_vectorstore
import os

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.environ.get("GROQ_API_KEY"))

# Chunks with L2 distance above this are considered irrelevant
MAX_DISTANCE = 1.5


# ── Scope resolution ───────────────────────────────────────────────────

def get_collections_for_scope(user_id, channel_id, scope="all"):
    """
    Map a scope label to ChromaDB collection names.

      "all"      → org + team + personal  (default)
      "org"      → org only
      "team"     → team_{channel_id} only
      "personal" → user_{user_id} only
    """
    scope = (scope or "all").lower()
    if scope == "org":
        return ["org"]
    if scope == "team":
        return [f"team_{channel_id}"]
    if scope == "personal":
        return [f"user_{user_id}"]
    return ["org", f"team_{channel_id}", f"user_{user_id}"]


# ── Confidence scoring ─────────────────────────────────────────────────

def _confidence_label(distances):
    """Map average L2 distance to a human-readable confidence label."""
    if not distances:
        return "🔴 Low", 0.0
    avg = sum(distances) / len(distances)
    if avg < 1.0:
        return "🟢 High", avg
    elif avg < 1.35:
        return "🟡 Medium", avg
    return "🔴 Low", avg


# ── Block Kit builders ─────────────────────────────────────────────────

def _build_answer_blocks(answer_text, sources, confidence_label, is_summary=False):
    """Rich Slack response with header, answer, sources, and confidence."""
    header = "📝 Summary" if is_summary else "💡 Answer"
    return [
        {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": answer_text}},
        {"type": "divider"},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"*Confidence:* {confidence_label}"},
            {"type": "mrkdwn", "text": f"*Sources:* {', '.join(sources)}"},
        ]},
    ]


def _build_no_results_blocks():
    """Response when no relevant documents are found."""
    return [{"type": "section", "text": {"type": "mrkdwn", "text":
        "🚫 *This question is outside the knowledge base scope.*\n\n"
        "I can only answer from uploaded documents. Try:\n"
        "• `/upload <url>` to add a document\n"
        "• `/browse` to see what's in the KB"
    }}]


def _build_out_of_scope_blocks():
    """Response when LLM determines the answer isn't in the retrieved context."""
    return [{"type": "section", "text": {"type": "mrkdwn", "text":
        "🔍 *I don't have that information in the knowledge base.*\n\n"
        "The uploaded documents don't contain an answer. Try:\n"
        "• Rephrasing your question\n"
        "• Uploading relevant documents with `/upload`\n"
        "• Checking available content with `/browse`"
    }}]


# ── Main Q&A ───────────────────────────────────────────────────────────

def query_knowledge_base(question, user_id, channel_id, scope="all", history=None):
    """Search the KB, generate a grounded answer, and return Block Kit blocks."""
    collections = get_collections_for_scope(user_id, channel_id, scope)

    all_docs, all_distances = [], []
    for col in collections:
        try:
            db = get_vectorstore(col)
            for doc, dist in db.similarity_search_with_score(question, k=3):
                if dist <= MAX_DISTANCE:
                    doc.metadata["_scope"] = col
                    all_docs.append(doc)
                    all_distances.append(dist)
        except Exception:
            pass

    if not all_docs:
        return _build_no_results_blocks(), None

    context = "\n\n".join(d.page_content for d in all_docs)
    sources = list({
        f"[{d.metadata.get('_scope', 'org')}] {d.metadata.get('source', 'unknown')}"
        for d in all_docs
    })

    # Build conversation history for multi-turn support
    history_block = ""
    if history:
        lines = [f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history]
        history_block = "Previous conversation:\n" + "\n".join(lines) + "\n\n"

    prompt = f"""You are a helpful knowledge base assistant.
Answer the question using ONLY the context below.
Do NOT use any outside knowledge. Do NOT guess or make up answers.
If the context does not contain enough information to answer the question,
you MUST respond with exactly: "OUT_OF_SCOPE"

{history_block}Context:
{context}

Question: {question}"""

    response = llm.invoke(prompt)
    answer = response.content.strip()

    # Detect out-of-scope responses
    out_of_scope_phrases = [
        "out_of_scope", "i don't have that information",
        "i don't have enough information", "not in the context",
        "cannot find", "no information available",
    ]
    if any(phrase in answer.lower() for phrase in out_of_scope_phrases):
        return _build_out_of_scope_blocks(), None

    confidence_label, _ = _confidence_label(all_distances)
    return _build_answer_blocks(answer, sources, confidence_label), answer


# ── Summarisation ──────────────────────────────────────────────────────

def summarize_text(text):
    """Summarise arbitrary text using the LLM."""
    prompt = f"""You are a concise summarisation assistant.
Provide a clear, well-structured summary of the following content.
Use bullet points for key takeaways.

Content:
{text[:6000]}"""

    response = llm.invoke(prompt)
    blocks = _build_answer_blocks(response.content, ["Provided text"], "🟢 High", is_summary=True)
    return blocks, response.content


def summarize_from_kb(source_name, user_id, channel_id, scope="all"):
    """Fetch all chunks for a source from the KB and summarise them."""
    collections = get_collections_for_scope(user_id, channel_id, scope)

    all_texts = []
    for col in collections:
        try:
            db = get_vectorstore(col)
            results = db.get(where={"source": source_name})
            all_texts.extend(results.get("documents", []))
        except Exception:
            pass

    if not all_texts:
        return _build_no_results_blocks(), None

    return summarize_text("\n\n".join(all_texts))