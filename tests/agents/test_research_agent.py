from unittest.mock import AsyncMock, patch
import pytest

from app.agents.research_agent import (
    AgentState,
    Paper,
    _action_filter_papers,
    _action_think,
    _score_paper,
    run_research_agent,
)


def test_score_paper_healthcare() -> None:
    text = "deep learning model for medical imaging clinical diagnosis hospital"
    sector, score = _score_paper(text)
    assert sector == "Healthcare"
    assert score >= 2


def test_score_paper_agriculture() -> None:
    text = "precision agriculture satellite crop yield prediction farm soil"
    sector, score = _score_paper(text)
    assert sector == "Agriculture"
    assert score >= 2


def test_score_paper_irrelevant() -> None:
    text = "sorting algorithms bubble sort merge quicksort heap binary search tree"
    sector, score = _score_paper(text)
    assert sector is None
    assert score == 0


def test_filter_papers_removes_irrelevant() -> None:
    state = AgentState(
        papers_raw=[
            Paper(
                title="AI for medical imaging",
                abstract="clinical diagnosis hospital patient radiology",
                url="http://arxiv.org/1",
                source="arxiv",
            ),
            Paper(
                title="Quantum bubble sort",
                abstract="sorting algorithm merge quicksort heap binary tree traversal",
                url="http://arxiv.org/2",
                source="arxiv",
            ),
        ]
    )
    _action_filter_papers(state)
    assert len(state.papers_filtered) == 1
    assert state.papers_filtered[0].sector == "Healthcare"


def test_think_selects_top_4() -> None:
    state = AgentState(
        papers_filtered=[
            Paper(
                title=f"Paper {i}",
                abstract="medical clinical health patient hospital diagnosis",
                url=f"http://example.com/{i}",
                source="arxiv",
                sector="Healthcare",
                relevance_score=i,
            )
            for i in range(10)
        ]
    )
    _action_think(state)
    assert len(state.papers_selected) == 4
    scores = [p.relevance_score for p in state.papers_selected]
    assert sorted(scores, reverse=True) == scores


def test_think_handles_empty_papers() -> None:
    state = AgentState(papers_filtered=[])
    _action_think(state)
    assert state.papers_selected == []


@pytest.mark.asyncio
async def test_run_research_agent_no_papers() -> None:
    """Agent handles gracefully when no papers are fetched."""
    with (
        patch(
            "app.agents.research_agent._fetch_arxiv",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.agents.research_agent._fetch_huggingface",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await run_research_agent()
        assert result == 0


@pytest.mark.asyncio
async def test_run_research_agent_saves_drafts(db_session) -> None:
    """Agent saves drafts when relevant papers are found."""
    from contextlib import asynccontextmanager

    mock_paper = Paper(
        title="AI for medical imaging in Africa",
        abstract=(
            "clinical diagnosis hospital patient radiology medical imaging "
            "deep learning model for health outcomes"
        ),
        url="http://arxiv.org/abs/test123",
        source="arxiv",
        authors=["Test Author"],
    )

    mock_draft = {
        "title": "How AI Is Transforming Medical Imaging in Africa",
        "tag": "Research Digest",
        "excerpt": "A new study shows promising results for AI-assisted radiology.",
        "read_time": "5 min",
        "content": "## Overview\n\nTest content.\n\n## DFT Labs Take\n\nWe believe...",
    }

    @asynccontextmanager
    async def mock_session_context():
        yield db_session

    with (
        patch(
            "app.agents.research_agent._fetch_arxiv",
            new_callable=AsyncMock,
            return_value=[mock_paper],
        ),
        patch(
            "app.agents.research_agent._fetch_huggingface",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.agents.research_agent._action_write_draft",
            new_callable=AsyncMock,     
            return_value=mock_draft,
        ),
        patch(
            "app.agents.research_agent.get_session_context",
            mock_session_context,
        ),
    ):
        result = await run_research_agent()
        assert result == 1