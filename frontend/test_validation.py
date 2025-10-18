"""
Test script for is_valid_plain_text() validation function
"""

import re


def is_valid_plain_text(text: str) -> tuple[bool, str]:
    """
    Validate that input contains only plain text characters.

    Args:
        text: User input string to validate

    Returns:
        tuple: (is_valid: bool, error_message: str)
               - is_valid: True if text contains only allowed characters
               - error_message: Empty string if valid, error description if invalid
    """
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
        # Focus on common emoji ranges, excluding miscellaneous symbols
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


# Test cases
test_cases = [
    # Valid inputs
    ("Find papers on machine learning", True, ""),
    ("What are the latest developments in AI?", True, ""),
    ("Papers from 2020-2024 on NLP", True, ""),
    ("Research on C++ & Python performance", True, ""),
    ("Survey of transformer architectures (2023)", True, ""),
    # Invalid inputs - Emojis
    ("Find papers 😊", False, "Emojis are not allowed in research queries."),
    ("🔬 Research on AI 🤖", False, "Emojis are not allowed in research queries."),
    ("😊😊😊", False, "Emojis are not allowed in research queries."),
    # Invalid inputs - Special characters
    (
        "Research on AI ★ ☆",
        False,
        "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
    ),
    (
        "Papers on ∑ and ∫",
        False,
        "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
    ),
    (
        "Cost analysis € $ ¥",
        False,
        "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
    ),
    # Edge cases
    (
        "",
        False,
        "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
    ),
    (
        "   ",
        False,
        "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
    ),
]

print("Testing is_valid_plain_text() function\n")
print("=" * 80)

passed = 0
failed = 0

for text, expected_valid, expected_message in test_cases:
    is_valid, error_message = is_valid_plain_text(text)

    # Check if result matches expected
    if is_valid == expected_valid and error_message == expected_message:
        status = "✓ PASS"
        passed += 1
    else:
        status = "✗ FAIL"
        failed += 1

    print(f"\n{status}")
    print(f"Input: '{text}'")
    print(f"Expected: valid={expected_valid}, message='{expected_message}'")
    print(f"Got:      valid={is_valid}, message='{error_message}'")

print("\n" + "=" * 80)
print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")

if failed == 0:
    print("✓ All tests passed!")
else:
    print(f"✗ {failed} test(s) failed")
