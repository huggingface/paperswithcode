#!/usr/bin/env python3
"""
Test script for citation-based search functionality.

This script tests the enhanced search functionality that includes citation counts
from the Semantic Scholar API.
"""

import asyncio
import sys

from backend.database.connection import get_database_session
from backend.services.paper_service import PaperService
from backend.services.semantic_scholar_service import SemanticScholarService


async def test_semantic_scholar_service():
    """Test the Semantic Scholar service."""
    print("🔍 Testing Semantic Scholar API service...")

    # Get database session
    db = next(get_database_session())

    try:
        service = SemanticScholarService(db)

        # Test searching for a well-known paper
        print("\n📄 Searching for 'Attention Is All You Need'...")
        paper_data = await service.search_paper_by_title("Attention Is All You Need")

        if paper_data:
            print(f"✅ Found paper: {paper_data.get('title', 'Unknown')}")
            print(f"📊 Citation count: {paper_data.get('citationCount', 0)}")
            print(f"🆔 Semantic Scholar ID: {paper_data.get('paperId', 'Unknown')}")
        else:
            print("❌ Paper not found")

        # Test searching by ArXiv ID
        print("\n📄 Searching by ArXiv ID '1706.03762' (Transformer paper)...")
        paper_data = await service.search_paper_by_arxiv_id("1706.03762")

        if paper_data:
            print(f"✅ Found paper: {paper_data.get('title', 'Unknown')}")
            print(f"📊 Citation count: {paper_data.get('citationCount', 0)}")
        else:
            print("❌ Paper not found")

        # Test searching for highly cited papers
        print("\n🔥 Searching for highly cited 'vision transformer' papers...")
        highly_cited = await service.get_highly_cited_papers(
            "vision transformer", limit=5
        )

        if highly_cited:
            print(f"✅ Found {len(highly_cited)} highly cited papers:")
            for i, (title, citations) in enumerate(highly_cited, 1):
                print(f"  {i}. {title[:80]}... ({citations} citations)")
        else:
            print("❌ No highly cited papers found")

    except Exception as e:
        print(f"❌ Error testing Semantic Scholar service: {e}")
    finally:
        db.close()


def test_citation_search():
    """Test the citation-based search functionality."""
    print("\n🔍 Testing citation-based search...")

    # Get database session
    db = next(get_database_session())

    try:
        service = PaperService(db)

        # Test search with different queries
        test_queries = [
            "vision transformer",
            "attention mechanism",
            "BERT",
            "neural network",
        ]

        for query in test_queries:
            print(f"\n🔎 Searching for: '{query}'")
            results = service.search_papers(query, limit=5)

            if results:
                print(f"✅ Found {len(results)} papers:")
                for i, paper in enumerate(results, 1):
                    citation_info = (
                        f" ({paper.citation_count} citations)"
                        if hasattr(paper, "citation_count")
                        else ""
                    )
                    print(f"  {i}. {paper.title[:80]}...{citation_info}")
            else:
                print("❌ No papers found")

    except Exception as e:
        print(f"❌ Error testing citation search: {e}")
    finally:
        db.close()


async def test_enhanced_search():
    """Test the enhanced search with Semantic Scholar integration."""
    print("\n🚀 Testing enhanced search with Semantic Scholar integration...")

    # Get database session
    db = next(get_database_session())

    try:
        service = PaperService(db)

        # Test enhanced search
        query = "vision transformer"
        print(f"\n🔎 Enhanced search for: '{query}'")
        results = await service.search_papers_with_semantic_scholar(query, limit=5)

        if results:
            print(f"✅ Found {len(results)} papers with enhanced search:")
            for i, paper in enumerate(results, 1):
                citation_info = (
                    f" ({paper.citation_count} citations)"
                    if hasattr(paper, "citation_count")
                    else ""
                )
                print(f"  {i}. {paper.title[:80]}...{citation_info}")
        else:
            print("❌ No papers found with enhanced search")

    except Exception as e:
        print(f"❌ Error testing enhanced search: {e}")
    finally:
        db.close()


async def main():
    """Run all tests."""
    print("🧪 Starting citation-based search tests...\n")

    # Test Semantic Scholar service
    await test_semantic_scholar_service()

    # Test basic citation search
    test_citation_search()

    # Test enhanced search
    await test_enhanced_search()

    print("\n✅ All tests completed!")


if __name__ == "__main__":
    # Check if we can import required modules
    import importlib.util

    if importlib.util.find_spec("httpx") is not None:
        print("✅ httpx is available")
    else:
        print("❌ httpx is not installed. Run: uv add httpx")
        sys.exit(1)

    # Run the tests
    asyncio.run(main())
