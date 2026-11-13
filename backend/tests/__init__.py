"""
Test-suite initialization: isolates chat rate limiting across rapid unit test runs
without modifying production rate limits. Tests that specifically exercise rate
limiting (e.g., test_01b, test_06) override this with their own patch/limiter.
"""

from unittest.mock import patch

_test_rate_limit_patch = patch(
    "backend.app.main.rate_limiter.check_rate_limit",
    return_value=(True, 1),
)
_test_rate_limit_patch.start()
