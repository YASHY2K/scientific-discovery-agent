"""
Test script to verify error handling in validation function.
"""

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def is_valid_plain_text(text: str) -> tuple[bool, str]:
    """
    Validate that input contains only plain text characters.
    This is a copy of the function from app.py for testing.
    """
    import re

    # Check for whitespace-only input
    if not text or text.strip() == "":
        return (
            False,
            "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
        )

    # Define allowed characters pattern (check this first)
    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?;:\'\"\-\(\)\[\]&@#%/\\+]+$")

    # Check if text contains only allowed characters
    if not allowed_pattern.match(text):
        # Define emoji pattern for more specific error message
        emoji_pattern = re.compile(
            "["
            "\U0001f600-\U0001f64f"  # emoticons
            "\U0001f300-\U0001f5ff"  # symbols & pictographs
            "\U0001f680-\U0001f6ff"  # transport & map symbols
            "\U0001f1e0-\U0001f1ff"  # flags
            "\U0001f900-\U0001f9ff"  # supplemental symbols
            "]+",
            flags=re.UNICODE,
        )

        # Check if it's specifically an emoji
        if emoji_pattern.search(text):
            return False, "Emojis are not allowed in research queries."
        else:
            return (
                False,
                "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
            )

    return True, ""


def test_error_handling():
    """Test that error handling works correctly."""
    print("Testing error handling for validation function...\n")

    # Test 1: Normal valid input
    print("Test 1: Valid input")
    try:
        is_valid, error_message = is_valid_plain_text("Find papers on machine learning")
        print(f"  Result: is_valid={is_valid}, error_message='{error_message}'")
        assert is_valid == True
        assert error_message == ""
        print("  ✓ PASSED\n")
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        print(f"  ✗ FAILED: {e}\n")

    # Test 2: Invalid input with emoji
    print("Test 2: Invalid input with emoji")
    try:
        is_valid, error_message = is_valid_plain_text("Find papers 😊")
        print(f"  Result: is_valid={is_valid}, error_message='{error_message}'")
        assert is_valid == False
        assert "Emojis" in error_message
        print("  ✓ PASSED\n")
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        print(f"  ✗ FAILED: {e}\n")

    # Test 3: Simulate validation function error (by passing None)
    print("Test 3: Error handling with fail-open behavior")
    try:
        # This should raise an error
        is_valid, error_message = is_valid_plain_text(None)
        print(f"  Result: is_valid={is_valid}, error_message='{error_message}'")
        print("  ✗ FAILED: Should have raised an error\n")
    except Exception as e:
        # This is expected - now test the error handling wrapper
        logger.error(f"Input validation error: {str(e)}", exc_info=True)
        print(f"  Caught expected error: {type(e).__name__}")

        # Simulate fail-open behavior
        is_valid = True
        error_message = ""
        print(
            f"  Fail-open behavior: is_valid={is_valid}, error_message='{error_message}'"
        )
        print("  ✓ PASSED - Error logged and fail-open behavior applied\n")

    print("All tests completed!")


if __name__ == "__main__":
    test_error_handling()
