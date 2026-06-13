"""
Tagger — automatic document classification.

Sends a text snippet to the LLM and returns 1–3 category tags
for browsing and filtering documents by topic.
"""

from langchain_groq import ChatGroq
import os

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.environ.get("GROQ_API_KEY"))

CATEGORIES = [
    "Engineering", "HR", "Finance", "Legal",
    "Onboarding", "Product", "Design", "Marketing", "General",
]

_TAG_PROMPT = """Classify the following document into 1 to 3 categories from this list:
{categories}

Rules:
- Return ONLY comma-separated category names from the list above.
- Do NOT add any explanation or extra text.
- If nothing fits well, return "General".

Document:
{text}"""


def auto_tag(text: str) -> list[str]:
    """Return 1–3 category tags for the given text."""
    snippet = text[:1500]
    try:
        response = llm.invoke(_TAG_PROMPT.format(
            categories=", ".join(CATEGORIES),
            text=snippet,
        ))
        raw = response.content.strip()
        tags = [t.strip() for t in raw.split(",") if t.strip() in CATEGORIES]
        return tags if tags else ["General"]
    except Exception:
        return ["General"]
