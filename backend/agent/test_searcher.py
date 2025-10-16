import logging
import json
from research_orchestrator import create_orchestrator, searcher_agent_tool
from searcher.searcher_agent import searcher_agent, format_search_query

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


def test_searcher_integration():
    """Test if research orchestrator properly uses the searcher agent."""
    try:
        # Create orchestrator instance
        orchestrator = create_orchestrator()

        # Set up a test subtopic
        test_subtopic = {
            "id": "test_topic",
            "description": "Recent advances in transformer architectures for NLP",
            "suggested_keywords": [
                "transformer architecture",
                "NLP advances",
                "attention mechanism",
            ],
            "search_guidance": {
                "focus_on": "Novel architectural improvements",
                "must_include": "Empirical results",
                "avoid": "Survey papers without original contributions",
            },
        }

        # Initialize orchestrator state
        orchestrator.state.set("research_plan", {"sub_topics": [test_subtopic]})
        orchestrator.state.set("current_subtopic_index", 0)

        # Test search execution
        logger.info("Testing searcher agent integration...")
        search_result = searcher_agent_tool(test_subtopic)

        # Validate search result
        try:
            search_data = json.loads(search_result)

            # Check if search_data has expected structure
            assert "selected_papers" in search_data, "No selected papers in response"
            assert isinstance(search_data["selected_papers"], list), (
                "Selected papers is not a list"
            )

            # Check if papers have required fields
            if search_data["selected_papers"]:
                paper = search_data["selected_papers"][0]
                required_fields = ["title", "abstract", "s3_text_path"]
                for field in required_fields:
                    assert field in paper, f"Paper missing required field: {field}"

            logger.info(f"Found {len(search_data['selected_papers'])} papers")
            logger.info("Sample titles:")
            for paper in search_data["selected_papers"][:3]:  # Show first 3 papers
                logger.info(f"- {paper['title']}")

            return True, search_data

        except json.JSONDecodeError:
            logger.error("Failed to parse search result as JSON")
            logger.debug(f"Raw response: {search_result}")
            return False, None

        except AssertionError as e:
            logger.error(f"Search result validation failed: {str(e)}")
            logger.debug(f"Search data: {json.dumps(search_data, indent=2)}")
            return False, search_data

    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        return False, None


def test_search_query_formatting():
    """Test if search queries are properly formatted with guidance."""
    test_input = {
        "description": "Compare transformer architectures",
        "keywords": ["transformer model", "architecture comparison"],
        "search_guidance": {
            "focus_on": "Performance differences",
            "must_include": "Benchmark results",
            "avoid": "Theoretical papers",
        },
    }

    formatted = format_search_query(test_input, include_directives=True)
    logger.info("Testing search query formatting:")
    logger.info(f"Input: {json.dumps(test_input, indent=2)}")
    logger.info(f"Formatted query: {formatted}")

    # Verify formatting includes search guidance
    return all(
        term in formatted.lower()
        for term in ["performance", "benchmark", "transformer"]
    )


if __name__ == "__main__":
    # Test search query formatting
    logger.info("=== Testing Search Query Formatting ===")
    if test_search_query_formatting():
        logger.info("✓ Search query formatting test passed")
    else:
        logger.error("✗ Search query formatting test failed")

    # Test searcher integration
    logger.info("\n=== Testing Searcher Integration ===")
    success, search_data = test_searcher_integration()

    if success:
        logger.info("✓ Searcher integration test passed")
        if search_data and search_data.get("selected_papers"):
            logger.info("Papers were successfully retrieved and processed")
    else:
        logger.error("✗ Searcher integration test failed")
