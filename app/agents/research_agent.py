"""
app/agents/research_agent.py

Research Digest Agent — ReAct Architecture
==========================================

ReAct loop:  Thought → Action → Observation → Thought → ...

Nodes:
  1. FETCH     — gather papers from ArXiv + HuggingFace
  2. FILTER    — score relevance against DFT Labs sectors
  3. THINK     — LLM decides which papers are worth writing about
  4. WRITE     — LLM writes the full blog draft
  5. SAVE      — persist draft to DB with status='draft'

Admin reviews drafts in the admin panel before publishing.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum, auto
from typing import Any

import arxiv
import httpx

from app.core.llm_client import llm_complete
from app.database import get_session_context
from app.models.blog import BlogPost

logger = logging.getLogger(__name__)


# ── Domain types ──────────────────────────────────────────────────────────────

class AgentAction(Enum):
    FETCH_ARXIV = auto()
    FETCH_HUGGINGFACE = auto()
    FILTER_PAPERS = auto()
    THINK = auto()
    WRITE_DRAFT = auto()
    SAVE_DRAFT = auto()
    DONE = auto()


@dataclass
class Paper:
    title: str
    abstract: str
    url: str
    source: str
    authors: list[str] = field(default_factory=list)
    sector: str | None = None
    relevance_score: int = 0


@dataclass
class AgentState:
    """Mutable state carried through the ReAct loop."""

    papers_raw: list[Paper] = field(default_factory=list)
    papers_filtered: list[Paper] = field(default_factory=list)
    papers_selected: list[Paper] = field(default_factory=list)
    drafts_saved: int = 0
    errors: list[str] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)


# ── Sector keyword scoring ────────────────────────────────────────────────────

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Healthcare": [
        "medical", "clinical", "health", "patient", "disease",
        "diagnosis", "imaging", "radiology", "drug", "hospital", "EHR",
        "biomedical", "therapy", "treatment", "epidemi", "genomic",
        "mental health", "wellbeing", "public health", "pathology",
        "telemedicine", "wearable", "vital signs", "cancer", "diabetes",
    ],
    "Agriculture": [
        "agriculture", "crop", "farm", "soil", "yield", "plant",
        "pest", "irrigation", "precision farming", "satellite", "agri",
        "food security", "harvest", "livestock", "drought", "climate",
        "remote sensing", "vegetation", "deforestation", "land use",
        "weather prediction", "water management", "supply chain",
    ],
    "Banking": [
        "finance", "financial", "banking", "fraud", "credit", "payment",
        "risk", "compliance", "trading", "fintech", "insurance",
        "loan", "microfinance", "mobile money", "transaction", "audit",
        "anti-money laundering", "kyc", "portfolio", "market", "economic",
        "cryptocurrency", "blockchain", "regulatory", "debt",
    ],
    "Education": [
        "education", "learning", "student", "curriculum", "teaching",
        "adaptive", "literacy", "school", "edtech", "tutoring",
        "assessment", "pedagog", "low-resource", "multilingual",
        "indigenous language", "code-switching", "reading comprehension",
        "question answering", "knowledge distillation", "e-learning",
        "classroom", "higher education", "vocational",
    ],
    "AI Research": [
        # Architectures & Models
        "transformer", "architecture", "attention mechanism", "state space",
        "mamba", "diffusion model", "generative model", "foundation model",
        "large language model", "llm", "multimodal", "vision language",
        "embedding", "tokenization", "pretraining", "fine-tuning",
        "parameter efficient", "lora", "quantization", "pruning",
        "knowledge graph", "retrieval augmented", "rag",
        # Reinforcement Learning
        "reinforcement learning", "rl", "reward model", "policy gradient",
        "proximal policy", "ppo", "dpo", "grpo", "rlhf",
        "multi-agent", "model-based rl", "offline rl", "exploration",
        "temporal dependency", "world model", "planning",
        # Detection & Mitigation
        "hallucination", "hallucination detection", "factual",
        "misinformation", "detection", "mitigation", "robustness",
        "adversarial", "out-of-distribution", "anomaly detection",
        "calibration", "uncertainty",
        # Bias, Explainability, Privacy, Safety & Security
        "bias", "fairness", "debiasing", "disparate impact",
        "explainability", "interpretability", "xai", "saliency",
        "attribution", "mechanistic interpretability",
        "privacy", "differential privacy", "federated learning",
        "data poisoning", "membership inference", "watermarking",
        "safety", "alignment", "constitutional ai", "red teaming",
        "jailbreak", "prompt injection", "guardrail", "refusal",
        "toxicity", "harmful content", "censorship",
        "security", "threat", "vulnerability", "attack", "defense",
        # Efficiency & Deployment
        "inference", "latency", "throughput", "edge deployment",
        "mobile inference", "model compression", "distillation",
        "benchmark", "evaluation", "leaderboard",
    ],
}


def _score_paper(text: str) -> tuple[str | None, int]:
    t = text.lower()
    scores = {
        sector: sum(1 for kw in kws if kw in t)
        for sector, kws in SECTOR_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)  # type: ignore
    score = scores[best]

    if best == "AI Research":
        return (best, score) if score >= 1 else (None, 0)
    else:
        # Core sectors need stronger signal to avoid false positives
        return (best, score) if score >= 2 else (None, 0)


# ── Actions ───────────────────────────────────────────────────────────────────
from datetime import datetime, timedelta, UTC

async def _fetch_arxiv(max_results: int = 5) -> list[Paper]:
    """Fetch papers from ArXiv submitted in the last 7 days."""
    # Date range: last 7 days
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    date_filter = (
        f"submittedDate:[{week_ago.strftime('%Y%m%d')}0000 "
        f"TO {now.strftime('%Y%m%d')}2359]"
    )

    queries = [
        # Healthcare
        "AI medical diagnosis clinical deep learning hospital patient",
        "machine learning radiology pathology disease detection treatment",
        # Agriculture
        "AI precision agriculture crop disease yield prediction satellite farm",
        "machine learning soil irrigation livestock food security Africa",
        # Banking/Finance
        "AI fraud detection credit scoring fintech mobile money banking Africa",
        "machine learning risk assessment loan default payment financial inclusion",
        # Education
        "AI adaptive learning education low-resource language NLP Africa",
        "machine learning student performance tutoring curriculum edtech",
        # AI Research (fallback)
        "bias detection bias mitigation bias tracing",
        "ai security ai risk management privacy guardrails",
    ]

    papers: list[Paper] = []
    for query in queries:
        try:
            search = arxiv.Search(
                query=f"({query}) AND {date_filter}",
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            for r in search.results():
                papers.append(
                    Paper(
                        title=r.title,
                        abstract=r.summary[:800],
                        url=r.entry_id,
                        source="arxiv",
                        authors=[a.name for a in r.authors[:3]],
                    )
                )
        except Exception as exc:
            logger.warning(
                "[Research Agent] ArXiv query failed for '%s': %s", query, exc
            )
    return papers

async def _fetch_huggingface() -> list[Paper]:
    """Fetch daily papers from HuggingFace. Returns list for easy mocking in tests."""
    async with httpx.AsyncClient(timeout=15) as http:
        try:
            resp = await http.get(
                "https://huggingface.co/api/daily_papers?limit=10"
            )
            resp.raise_for_status()
            return [
                Paper(
                    title=p["paper"]["title"],
                    abstract=p["paper"].get("summary", "")[:600],
                    url=f"https://huggingface.co/papers/{p['paper']['id']}",
                    source="huggingface",
                )
                for p in resp.json()
                if p.get("paper", {}).get("title")
            ]
        except Exception as exc:
            logger.warning("[Research Agent] HuggingFace fetch failed: %s", exc)
    return []


async def _action_fetch_arxiv(state: AgentState) -> None:
    thought = "Fetching ArXiv papers across sector queries"
    state.thoughts.append(thought)
    logger.info("[Research Agent] %s", thought)
    papers = await _fetch_arxiv()
    state.papers_raw.extend(papers)
    obs = f"Fetched {len(papers)} papers from ArXiv"
    state.thoughts.append(f"Observation: {obs}")
    logger.info("[Research Agent] %s", obs)


async def _action_fetch_huggingface(state: AgentState) -> None:
    thought = "Fetching HuggingFace daily papers"
    state.thoughts.append(thought)
    logger.info("[Research Agent] %s", thought)
    papers = await _fetch_huggingface()
    state.papers_raw.extend(papers)
    obs = f"Fetched {len(papers)} papers from HuggingFace"
    state.thoughts.append(f"Observation: {obs}")
    logger.info("[Research Agent] %s", obs)


def _action_filter_papers(state: AgentState) -> None:
    """ACTION: Score and filter papers by DFT Labs sector relevance."""
    thought = f"Filtering {len(state.papers_raw)} papers for sector relevance"
    state.thoughts.append(thought)
    logger.info("[Research Agent] %s", thought)

    for paper in state.papers_raw:
        text = f"{paper.title} {paper.abstract}"
        sector, score = _score_paper(text)
        if sector:
            paper.sector = sector
            paper.relevance_score = score
            state.papers_filtered.append(paper)

    obs = (
        f"{len(state.papers_filtered)} / {len(state.papers_raw)} "
        f"papers passed relevance filter"
    )
    state.thoughts.append(f"Observation: {obs}")
    logger.info("[Research Agent] %s", obs)


def _action_think(state: AgentState) -> None:
    """ACTION: Select top papers to write about (max 4 per run)."""
    if not state.papers_filtered:
        state.thoughts.append("Thought: No relevant papers found — stopping.")
        logger.info("[Research Agent] No relevant papers to process")
        state.papers_selected = []
        return

    thought = "Thinking: Selecting top papers to write about (max 4 per run)"
    state.thoughts.append(thought)
    logger.info("[Research Agent] %s", thought)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[Paper] = []
    for p in state.papers_filtered:
        if p.url not in seen:
            seen.add(p.url)
            unique.append(p)

    # Prefer core sectors — AI Research only fills remaining slots
    CORE_SECTORS = {"Healthcare", "Agriculture", "Banking", "Education"}
    MAX_PER_RUN = 4
    MAX_AI_RESEARCH = 1  # at most 1 pure AI Research paper per run

    core = sorted(
        [p for p in unique if p.sector in CORE_SECTORS],
        key=lambda p: p.relevance_score,
        reverse=True,
    )
    ai_research = sorted(
        [p for p in unique if p.sector == "AI Research"],
        key=lambda p: p.relevance_score,
        reverse=True,
    )

    # Fill up to MAX_PER_RUN: core papers first, then AI Research to fill gaps
    selected = core[:MAX_PER_RUN]
    remaining = MAX_PER_RUN - len(selected)
    if remaining > 0:
        selected += ai_research[:min(remaining, MAX_AI_RESEARCH)]

    state.papers_selected = selected

    obs = (
        f"Selected {len(state.papers_selected)} papers: "
        + ", ".join(f"'{p.title[:40]}...'" for p in state.papers_selected)
    )
    state.thoughts.append(f"Observation: {obs}")
    logger.info("[Research Agent] %s", obs)


async def _action_write_draft(paper: Paper) -> dict[str, Any]:
    """
    ACTION: LLM writes a full blog post draft using ReAct prompting.
    Uses llm_complete() which tries Anthropic → DeepSeek → Nemotron.
    """
    from app.core.llm_client import llm_complete_async

    authors_str = ", ".join(paper.authors) or "Unknown"

    prompt = f"""You are a writer for DeepFly Tech Labs (DFT Labs), an AI research lab
focused on Healthcare, Agriculture, Banking, and Education in Africa.

Use the ReAct format to think through this task before writing:

Thought: What is this paper actually about? What's the key contribution?
Observation: [your analysis of the abstract]
Thought: Who is the DFT Labs audience and what would they care about?
Observation: [your analysis of relevance]
Thought: What is the DFT Labs angle — how does this relate to African deployment?
Observation: [your editorial position]
Action: Write the blog post

Paper:
Title:    {paper.title}
Authors:  {authors_str}
Abstract: {paper.abstract}
Source:   {paper.url}
Sector:   {paper.sector}

After your ReAct reasoning, return a JSON object (ONLY the JSON object, no markdown fences):

{{
  "title": "Engaging, non-academic title for a technical audience",
  "tag": "Research Digest",
  "excerpt": "2-3 sentence compelling summary (max 220 characters)",
  "read_time": "X min",
  "content": "Full markdown post with:\\n## Overview\\n## Key Findings\\n## Implications for {paper.sector}\\n## DFT Labs Take"
}}

DFT Labs Take rules:
- First-person plural (we/our)
- Opinionated — take a clear stance
- Grounded in African deployment realities"""

    # raw = llm_complete(prompt=prompt, max_tokens=2500)
    raw = await llm_complete_async(prompt=prompt, max_tokens=2500)

    # Extract JSON — strip any ReAct reasoning that came before it
    json_match = re.search(r"\{[\s\S]+\}", raw)
    if not json_match:
        raise ValueError(f"No JSON found in LLM response for: {paper.title}")

    clean = json_match.group()

    # Llama outputs literal newlines inside JSON string values — escape them
    # Strategy: replace all control chars EXCEPT where they are JSON structural
    # The safest fix: replace literal newlines inside string values with \n
    def _fix_json_strings(s: str) -> str:
            result = []
            in_string = False
            escape_next = False
            for ch in s:
                if escape_next:
                    # Valid JSON escape chars: " \ / b f n r t u
                    if ch in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
                        result.append(ch)
                    else:
                        # Invalid escape (e.g. \m \c \e from LaTeX) — drop backslash
                        result.pop()
                        result.append(ch)
                    escape_next = False
                elif ch == '\\' and in_string:
                    result.append(ch)
                    escape_next = True
                elif ch == '"':
                    result.append(ch)
                    in_string = not in_string
                elif in_string and ch == '\n':
                    result.append('\\n')
                elif in_string and ch == '\r':
                    result.append('\\r')
                elif in_string and ch == '\t':
                    result.append('\\t')
                elif in_string and ord(ch) < 0x20:
                    result.append(' ')
                else:
                    result.append(ch)
            return ''.join(result)
    
    clean = _fix_json_strings(clean)
    return json.loads(clean)


def _make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    ts = int(datetime.now(UTC).timestamp())
    return f"{slug[:80]}-{ts}"


async def _action_save_draft(paper: Paper, draft_data: dict, state: AgentState) -> None:
    """ACTION: Persist the generated draft to the database."""
    async with get_session_context() as db:
        post = BlogPost(
            slug=_make_slug(draft_data["title"]),
            title=draft_data["title"],
            tag=draft_data.get("tag", "Research Digest"),
            excerpt=draft_data["excerpt"],
            content=draft_data["content"],
            read_time=draft_data.get("read_time", "5 min"),
            sources=json.dumps([paper.url]),
            status="draft",
            agent_generated=True,
            author="DFT Labs Research Agent",
        )
        db.add(post)
        await db.flush()
        await db.refresh(post)

    state.drafts_saved += 1
    obs = f"Saved draft id={post.id}: '{draft_data['title'][:60]}...'"
    state.thoughts.append(f"Observation: {obs}")
    logger.info("[Research Agent] %s", obs)


# ── Main ReAct loop ───────────────────────────────────────────────────────────

async def run_research_agent() -> int:
    """
    Main entry point for the Research Digest Agent.

    ReAct loop:
        FETCH_ARXIV → FETCH_HUGGINGFACE → FILTER → THINK
        → for each paper: WRITE_DRAFT → SAVE_DRAFT → DONE
    """
    logger.info("[Research Agent] Starting ReAct loop")
    state = AgentState()

    state.thoughts.append(
        "Thought: I need to gather recent AI papers relevant to "
        "Healthcare, Agriculture, Banking, and Education."
    )

    await _action_fetch_arxiv(state)
    await _action_fetch_huggingface(state)
    _action_filter_papers(state)
    _action_think(state)

    if not state.papers_selected:
        logger.info("[Research Agent] No papers selected — run complete")
        return 0

    for paper in state.papers_selected:
        try:
            state.thoughts.append(
                f"Thought: Writing draft for '{paper.title[:50]}...'"
            )
            #draft_data = _action_write_draft(paper)
            draft_data = await _action_write_draft(paper)
            await _action_save_draft(paper, draft_data, state)
        except Exception as exc:
            msg = f"Failed on '{paper.title[:50]}': {exc}"
            state.errors.append(msg)
            logger.exception("[Research Agent] %s", msg)

    logger.info(
        "[Research Agent] Done — %d drafts saved, %d errors, %d thought steps",
        state.drafts_saved,
        len(state.errors),
        len(state.thoughts),
    )
    if state.errors:
        logger.warning("[Research Agent] Errors: %s", state.errors)

    return state.drafts_saved