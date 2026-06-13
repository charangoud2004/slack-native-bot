# 🧠 Slack Knowledge Base Bot

An AI-powered knowledge base layer inside Slack — upload documents, ask questions, get cited answers, and summarise content without ever leaving your workspace.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Slack](https://img.shields.io/badge/Slack-Bot-purple)
![LLM](https://img.shields.io/badge/LLM-Groq%20Llama%203.3-green)
![Hackathon](https://img.shields.io/badge/🏆%20Built%20at-Hackathon-orange)

> **🚀 Built at a Hackathon** — This project was conceived and built during a hackathon sprint.

---

## ✨ Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Document Ingestion** | Upload PDFs, DOCX, URLs, plain text, and Slack threads |
| 2 | **Natural Language Q&A** | Ask free-text questions and get grounded, cited answers |
| 3 | **Document Summarisation** | Summarise any document, URL, or thread on demand |
| 4 | **Multi-turn Conversation** | Follow-up questions work naturally with conversation memory |
| 5 | **Scoped Knowledge Layers** | Personal, team, and org-wide knowledge bases with access control |
| 6 | **Auto-tagging** | Documents are automatically categorised on upload |
| 7 | **Out-of-scope Detection** | Clearly indicates when answers aren't in the knowledge base |

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Slack API  │────▶│   app.py     │────▶│ retriever.py │
│  (Socket Mode)│     │  (Bolt)      │     │  (Q&A + LLM) │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
                            │                     │
                     ┌──────▼───────┐     ┌──────▼───────┐
                     │ ingestor.py  │     │  memory.py   │
                     │ (Parse+Embed)│     │ (Multi-turn) │
                     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────▼───────┐     ┌──────────────┐
                     │  ChromaDB    │     │  tagger.py   │
                     │ (Vector Store)│◀───│ (Auto-classify)│
                     └──────────────┘     └──────────────┘
```

| Component | Tech |
|-----------|------|
| Embeddings | `all-MiniLM-L6-v2` (local, HuggingFace) |
| Vector Store | ChromaDB (persistent, local) |
| LLM | Groq — Llama 3.3 70B |
| Framework | Slack Bolt (Python) |

---

## 🚀 Setup

### 1. Clone & install

```bash
git clone https://github.com/your-username/slack-knowledge-base.git
cd slack-knowledge-base
pip install -r requirements.txt
```

### 2. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Enable **Socket Mode** (Settings → Socket Mode → toggle ON → create an App-Level Token with `connections:write`)
3. Add **Bot Token Scopes** (OAuth & Permissions):
   - `chat:write`, `commands`, `files:read`
   - `channels:history`, `groups:history` (for thread access)
   - `app_mentions:read` (for @mention support)
   - `im:history`, `im:read`, `im:write` (for DM support)
4. Add **Event Subscriptions** (bot events):
   - `file_shared`, `app_mention`, `message.im`
5. Create **Slash Commands**:
   - `/ask`, `/upload`, `/summarize`, `/browse`, `/ingest-thread`, `/clear`
6. Enable **App Home → Messages Tab** and check "Allow users to send messages"
7. **Install to workspace** and copy the Bot Token (`xoxb-...`)

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your tokens:
#   SLACK_BOT_TOKEN=xoxb-...
#   SLACK_APP_TOKEN=xapp-...
#   GROQ_API_KEY=gsk_...
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).

### 4. Run

```bash
python app.py
```

---

## 📖 Usage

### Slash Commands

| Command | Example | Description |
|---------|---------|-------------|
| `/ask` | `/ask What's our PTO policy?` | Ask a question |
| `/ask --org` | `/ask --org company revenue` | Restrict to org-wide docs |
| `/upload` | `/upload https://example.com` | Ingest a URL |
| `/upload --org` | `/upload --org https://...` | Ingest as org-wide |
| `/summarize` | `/summarize https://...` | Summarise a URL |
| `/summarize doc:policy.pdf` | | Summarise an ingested doc |
| `/summarize thread` | | Summarise the current thread |
| `/browse` | `/browse` | List all documents |
| `/browse Engineering` | | Filter by category |
| `/ingest-thread` | | Save a thread to the KB |
| `/clear` | | Reset conversation memory |

### @Mentions & DMs

- **In channels:** `@KB Bot what is our deployment process?`
- **In DMs:** Just type your question directly — no command needed

### Knowledge Scopes

| Scope | Who can access | How to store |
|-------|---------------|--------------|
| **Personal** | Only you | Upload in a DM with the bot |
| **Team** | Channel members | Upload in a channel |
| **Org-wide** | Everyone | Use `--org` flag |

---

## 📁 Project Structure

```
slack-bot/
├── app.py            # Slack event handlers and slash commands
├── ingestor.py       # Document parsing, chunking, and embedding
├── retriever.py      # Vector search, LLM answer generation
├── memory.py         # Per-user multi-turn conversation history
├── tagger.py         # Auto-classification of documents
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── .gitignore        # Git ignore rules
```

---

## 📊 Success Metrics

| Metric | Target | Implementation |
|--------|--------|----------------|
| Answer accuracy | ≥ 80% grounded | LLM constrained to context only |
| Time to answer | < 10 seconds | Groq inference + local embeddings |
| Knowledge scope | Personal + Team + Org | ChromaDB collections per scope |
| Content types | PDF, DOCX, URL, threads, text | Multi-parser ingestion pipeline |
| Out-of-scope handling | Clear indication | Two-level detection (retrieval + LLM) |

---

## 🛡️ Constraints Met

- ✅ All answers grounded in uploaded knowledge base
- ✅ Never hallucates — clearly says when answer isn't available
- ✅ Access controls: team docs visible to team only
- ✅ Handles 50+ concurrent documents (ChromaDB scales locally)
- ✅ Technology-agnostic: swappable LLM, embeddings, and vector store

---

## 📄 License

MIT
