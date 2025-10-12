#!/usr/bin/env python3
"""
Local Workflow Test for Scientific Discovery Agent

This script tests the full, multi-agent workflow using local tool functions
instead of deployed AWS Lambda functions. This allows for rapid, cost-free
-testing of the core agent reasoning and collaboration logic.

- Agents (Orchestrator, Searcher, Analyzer) use the real Bedrock/Qwen model.
- Tools (`search_arxiv`, `acquire_paper`, etc.) are called as local Python functions.
"""

import asyncio
import logging
import time
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"


# Add project root to path to allow direct tool imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from agent.research_orchestrator import create_research_orchestrator


# --- Test Configuration ---
SESSION_ID = f"local_test_{int(time.time())}"
QUERY = "deep learning for satellite image analysis"


async def test_local_workflow():
    """Tests the complete agent workflow using local tool functions."""
    logger = logging.getLogger("TestLocalWorkflow")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
    )

    logger.info("### Scientific Discovery Agent - AWS MVP Test ###")
    logger.info(f"SESSION ID: {SESSION_ID}")
    logger.info(f"QUERY: '{QUERY}'")
    logger.info("MODE: AWS Lambda Tools")
    logger.info("=" * 60)

    # Step 1: Create the ResearchOrchestrator in AWS mode
    logger.info("1. Initializing agents in AWS mode...")
    try:
        orchestrator = create_research_orchestrator(
            session_id=SESSION_ID,
            use_local_tools=True,  # This is the key flag
            log_level=logging.DEBUG,  # Use DEBUG to see detailed agent thoughts
        )
        logger.info("Orchestrator and specialist agents initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to create orchestrator: {e}", exc_info=True)
        return False

    # Step 2: Run the full research workflow
    logger.info("2. Starting model-driven research workflow...")
    start_time = time.time()
    try:
        # First turn: User query -> search_literature
        logger.info("--- Turn 1: User Query -> Search ---")
        response = await orchestrator.process_message(QUERY)
        logger.info(f"Orchestrator response: {response}")

        # Second turn: Search results -> analyze_papers
        logger.info("--- Turn 2: Search Results -> Analysis ---")
        response = await orchestrator.process_message(response)
        logger.info(f"Orchestrator response: {response}")

        # Third turn: Analysis results -> final report
        logger.info("--- Turn 3: Analysis Results -> Final Report ---")
        final_report = await orchestrator.process_message(response)
        logger.info(f"Orchestrator response: {final_report}")

        final_report_text = final_report.message['content'][0]['reasoningContent']['reasoningText']['text']
        duration = time.time() - start_time

        logger.info("3. Workflow Complete!")
        logger.info(f"Total execution time: {duration:.2f} seconds")
        logger.info("=" * 60)
        logger.info("\nFinal Report:\n")
        print(final_report_text)
        logger.info("=" * 60)

        if "error" in final_report_text.lower() or "failed" in final_report_text.lower():
            logger.error(
                "The final report indicates a failure occurred during the workflow."
            )
            return False

    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"The research workflow failed after {duration:.2f}s: {e}", exc_info=True
        )
        return False

    logger.info("✅ Local workflow test completed successfully!")
    return True


async def main():
    try:
        success = await test_local_workflow()
        if success:
            print("\n🎉 MVP workflow test passed.")
        else:
            print("\n❌ MVP workflow test failed. Check logs for details.")
        return success
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        return False


if __name__ == "__main__":
    # This allows the script to find the tool modules
    # by adding the backend directory to the python path.
    backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, backend_path)

    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1)
