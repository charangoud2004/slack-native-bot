"""
Slack Knowledge Base Bot — main application.

Registers all slash commands, event handlers, and @mention support.
Runs via Socket Mode for development.
"""

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from storage.retriever import query_knowledge_base, summarize_text, summarize_from_kb
from ingestor import (
    ingest_text, parse_pdf, parse_docx, parse_url,
    get_target_collection, list_sources_by_tag, list_all_sources,
)
from features.memory import get_history, add_turn, clear as clear_memory
import os, tempfile, requests, re

load_dotenv()
app = App(token=os.environ["SLACK_BOT_TOKEN"])


# ── Helpers ────────────────────────────────────────────────────────────

def _update_or_say(client, say, loading_msg, text, blocks=None):
    """Update a loading message in-place, or fall back to say()."""
    try:
        kwargs = {"channel": loading_msg["channel"], "ts": loading_msg["ts"], "text": text}
        if blocks:
            kwargs["blocks"] = blocks
        client.chat_update(**kwargs)
    except Exception:
        say(text=text, blocks=blocks)


def _ask_and_respond(text, user_id, channel_id, say, client, thread_ts=None):
    """Shared Q&A logic used by /ask, @mention, and DM handlers."""
    say_kwargs = {"text": "⏳ Searching the knowledge base…"}
    if thread_ts:
        say_kwargs["thread_ts"] = thread_ts
    loading = say(**say_kwargs)

    history = get_history(user_id)
    blocks, raw_answer = query_knowledge_base(
        question=text, user_id=user_id, channel_id=channel_id,
        scope="all", history=history,
    )

    if raw_answer:
        add_turn(user_id, text, raw_answer)

    try:
        client.chat_update(
            channel=loading["channel"], ts=loading["ts"],
            text=raw_answer or "No results found.", blocks=blocks,
        )
    except Exception:
        say_kwargs = {"text": raw_answer or "No results found.", "blocks": blocks}
        if thread_ts:
            say_kwargs["thread_ts"] = thread_ts
        say(**say_kwargs)


# ── /ask — natural language Q&A ────────────────────────────────────────

@app.command("/ask")
def handle_ask(ack, command, say, client):
    ack()
    text     = command["text"].strip()
    user_id  = command["user_id"]
    channel_id = command["channel_id"]

    # Scope override: /ask --personal|--team|--org <question>
    scope = "all"
    for flag, s in (("--personal", "personal"), ("--team", "team"), ("--org", "org")):
        if text == flag or text.startswith(flag + " "):
            scope = s
            text = text[len(flag):].strip()
            break

    if not text:
        say("Usage: `/ask <question>`\nAdd `--personal`, `--team`, or `--org` to restrict scope.")
        return

    loading = say("⏳ Searching the knowledge base…")
    history = get_history(user_id)

    blocks, raw_answer = query_knowledge_base(
        question=text, user_id=user_id, channel_id=channel_id,
        scope=scope, history=history,
    )
    if raw_answer:
        add_turn(user_id, text, raw_answer)

    try:
        client.chat_update(
            channel=loading["channel"], ts=loading["ts"],
            text=raw_answer or "No results found.", blocks=blocks,
        )
    except Exception:
        say(text=raw_answer or "No results found.", blocks=blocks)


# ── /summarize — summarize a doc, URL, or thread ──────────────────────

@app.command("/summarize")
def handle_summarize(ack, command, say, client):
    ack()
    text       = command["text"].strip()
    user_id    = command["user_id"]
    channel_id = command["channel_id"]

    if not text:
        say("Usage:\n• `/summarize https://...` — summarize a URL\n"
            "• `/summarize doc:<name>` — summarize an ingested document\n"
            "• `/summarize thread` — summarize the current thread")
        return

    loading = say("⏳ Generating summary…")
    blocks, raw_answer = None, None

    if text.lower() == "thread":
        thread_ts = command.get("thread_ts")
        if not thread_ts:
            _update_or_say(client, say, loading, "⚠️ Run `/summarize thread` inside a thread.")
            return
        try:
            msgs = client.conversations_replies(channel=channel_id, ts=thread_ts).get("messages", [])
            thread_text = "\n".join(f"<@{m.get('user','?')}>: {m.get('text','')}" for m in msgs)
            blocks, raw_answer = summarize_text(thread_text)
        except Exception as e:
            _update_or_say(client, say, loading, f"⚠️ Couldn't fetch thread: {e}")
            return

    elif text.startswith("doc:"):
        blocks, raw_answer = summarize_from_kb(text[4:].strip(), user_id, channel_id)

    elif text.startswith("http"):
        try:
            blocks, raw_answer = summarize_text(parse_url(text))
        except Exception as e:
            _update_or_say(client, say, loading, f"⚠️ Couldn't fetch URL: {e}")
            return
    else:
        _update_or_say(client, say, loading, "⚠️ Use a URL, `doc:<name>`, or `thread`.")
        return

    _update_or_say(client, say, loading, raw_answer or "No content to summarize.", blocks=blocks)


# ── /upload — ingest a URL ─────────────────────────────────────────────

@app.command("/upload")
def handle_upload(ack, command, say):
    ack()
    text       = command["text"].strip()
    user_id    = command["user_id"]
    channel_id = command["channel_id"]

    org_wide = text.startswith("--org")
    if org_wide:
        text = text[len("--org"):].strip()

    if text.startswith("http"):
        col = get_target_collection(user_id, channel_id, org_wide=org_wide)
        content = parse_url(text)
        chunks, tags = ingest_text(content, {"source": text, "type": "url"}, collection_name=col)
        say(f"✅ Ingested URL: {text}\n• *{chunks}* chunks → `{col}`\n• Tags: {', '.join(tags)}")
    else:
        say("Send a URL or upload a file. Add `--org` for org-wide access.")


# ── /ingest-thread — save a Slack thread to the KB ─────────────────────

@app.command("/ingest-thread")
def handle_ingest_thread(ack, command, say, client):
    ack()
    text       = command["text"].strip()
    user_id    = command["user_id"]
    channel_id = command["channel_id"]

    target_channel, thread_ts = channel_id, None

    if text:
        match = re.search(r'/archives/(\w+)/p(\d+)', text)
        if match:
            target_channel = match.group(1)
            raw_ts = match.group(2)
            thread_ts = raw_ts[:10] + "." + raw_ts[10:]
        else:
            say("⚠️ Couldn't parse that link. Use a Slack thread link or run inside a thread.")
            return
    else:
        thread_ts = command.get("thread_ts")
        if not thread_ts:
            say("⚠️ Run `/ingest-thread` inside a thread, or pass a thread link.")
            return

    loading = say("⏳ Ingesting thread…")
    try:
        msgs = client.conversations_replies(channel=target_channel, ts=thread_ts).get("messages", [])
        if not msgs:
            _update_or_say(client, say, loading, "⚠️ No messages found.")
            return

        thread_text = "\n".join(f"<@{m.get('user','?')}>: {m.get('text','')}" for m in msgs)
        col = get_target_collection(user_id, channel_id)
        label = f"thread-{thread_ts}"
        chunks, tags = ingest_text(thread_text, {"source": label, "type": "slack_thread"}, collection_name=col)
        _update_or_say(client, say, loading,
                       f"✅ Ingested thread (`{label}`)\n• *{chunks}* chunks → `{col}`\n• Tags: {', '.join(tags)}")
    except Exception as e:
        _update_or_say(client, say, loading, f"⚠️ Couldn't fetch thread: {e}")


# ── /browse — list documents by tag ────────────────────────────────────

@app.command("/browse")
def handle_browse(ack, command, say):
    ack()
    text       = command["text"].strip()
    user_id    = command["user_id"]
    channel_id = command["channel_id"]
    from features.tagger import CATEGORIES

    collections = ["org", f"team_{channel_id}", f"user_{user_id}"]

    if not text or text.lower() == "all":
        all_docs = []
        for col in collections:
            try:
                for src, tags in list_all_sources(col).items():
                    all_docs.append(f"• `[{col}]` *{src}* — _{tags}_")
            except Exception:
                pass

        if all_docs:
            cat_list = ", ".join(f"`{c}`" for c in CATEGORIES)
            say(f"📂 *All documents:*\n" + "\n".join(all_docs) +
                f"\n\n_Filter: `/browse <category>` | Categories: {cat_list}_")
        else:
            say("📂 Knowledge base is empty. Upload docs with `/upload` or by sharing files.")
        return

    # Case-insensitive category match
    matched = next((c for c in CATEGORIES if c.lower() == text.lower()), text)

    found = []
    for col in collections:
        try:
            for s in list_sources_by_tag(matched, col):
                found.append(f"• `[{col}]` {s}")
        except Exception:
            pass

    if found:
        say(f"📂 *Documents tagged `{matched}`:*\n" + "\n".join(found))
    else:
        cat_list = ", ".join(f"`{c}`" for c in CATEGORIES)
        say(f"No docs tagged `{text}`.\n_Categories: {cat_list} | `/browse all` for everything._")


# ── /clear — reset conversation memory ─────────────────────────────────

@app.command("/clear")
def handle_clear(ack, command, say):
    ack()
    clear_memory(command["user_id"])
    say("🧹 Conversation memory cleared!")


# ── File upload handler ────────────────────────────────────────────────

@app.event("file_shared")
def handle_file(event, client, say):
    info = client.files_info(file=event["file_id"])["file"]
    name = info["name"]
    ext  = name.rsplit(".", 1)[-1].lower()

    user_id    = event.get("user_id")
    channel_id = event.get("channel_id")

    headers = {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}
    content = requests.get(info["url_private_download"], headers=headers).content

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    if ext == "pdf":
        text = parse_pdf(tmp_path)
    elif ext == "docx":
        text = parse_docx(tmp_path)
    else:
        text = content.decode("utf-8", errors="ignore")

    col = get_target_collection(user_id, channel_id)
    chunks, tags = ingest_text(text, {"source": name, "type": ext}, collection_name=col)
    say(f"✅ Ingested *{name}*\n• *{chunks}* chunks → `{col}`\n• Tags: {', '.join(tags)}")


# ── @mention support ───────────────────────────────────────────────────

HELP_TEXT = (
    "👋 Hi! I'm your Knowledge Base assistant.\n\n"
    "• *@mention me* with a question in any channel\n"
    "• `/ask <question>` — search the KB (with scope flags)\n"
    "• `/summarize <url|doc:name|thread>` — summarize content\n"
    "• `/upload <url>` — add a URL to the KB\n"
    "• `/browse` — browse documents by category\n"
    "• `/ingest-thread` — save a thread to the KB\n"
    "• `/clear` — reset conversation memory"
)


@app.event("app_mention")
def handle_mention(event, say, client):
    """Respond to @KB Bot <question> in channels."""
    raw_text   = event.get("text", "")
    user_id    = event.get("user", "")
    channel_id = event.get("channel", "")
    thread_ts  = event.get("thread_ts") or event.get("ts")

    text = re.sub(r"<@\w+>", "", raw_text).strip()

    if not text:
        say(text=HELP_TEXT, thread_ts=thread_ts)
        return

    _ask_and_respond(text, user_id, channel_id, say, client, thread_ts=thread_ts)


# ── DM support ─────────────────────────────────────────────────────────

@app.event("message")
def handle_dm(event, say, client, logger):
    """Respond to direct messages. Only handles DM channels (D*)."""
    try:
        channel_id = event.get("channel", "")
        if not channel_id.startswith("D"):
            return
        if event.get("bot_id") or event.get("subtype"):
            return

        text    = re.sub(r"<@\w+>", "", event.get("text", "")).strip()
        user_id = event.get("user", "")
        if not text:
            return

        lower = text.lower()
        if lower in ("help", "hi", "hello", "hey"):
            say(HELP_TEXT.replace("*@mention me*", "*Just type your question*"))
            return
        if lower == "clear":
            clear_memory(user_id)
            say("🧹 Conversation memory cleared!")
            return

        _ask_and_respond(text, user_id, channel_id, say, client)

    except Exception as e:
        logger.error(f"DM handler error: {e}")


# ── Entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()