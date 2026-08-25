"""
Douyin browser automation service.
Provides the automation interface and a Mock implementation for dev/test.
"""
import asyncio
import random
import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)


class DouyinAutomation:
    """Abstract automation interface for Douyin operations."""

    async def login_with_cookie(self, cookie_data: str) -> bool:
        raise NotImplementedError

    async def send_private_message(self, target_uid: str, content: str) -> bool:
        raise NotImplementedError

    async def fetch_new_messages(self, target_uid: str) -> List[dict]:
        raise NotImplementedError

    async def check_session_valid(self, cookie_data: str) -> bool:
        raise NotImplementedError


class MockDouyinAutomation(DouyinAutomation):
    """Mock implementation for development and testing."""

    async def login_with_cookie(self, cookie_data: str) -> bool:
        """Simulate cookie login – always succeeds after a short delay."""
        await asyncio.sleep(random.uniform(0.5, 1.0))
        logger.info("[Mock] login_with_cookie: success")
        return True

    async def send_private_message(self, target_uid: str, content: str) -> bool:
        """Simulate sending a private message with realistic delay."""
        await asyncio.sleep(random.uniform(2.0, 5.0))
        logger.info(f"[Mock] send_private_message to {target_uid}: success")
        return True

    async def fetch_new_messages(self, target_uid: str) -> List[dict]:
        """Simulate fetching new messages – returns empty list."""
        await asyncio.sleep(random.uniform(0.3, 0.8))
        return []

    async def check_session_valid(self, cookie_data: str) -> bool:
        """Simulate session validity check – always valid."""
        await asyncio.sleep(random.uniform(0.2, 0.5))
        return True


# Singleton instance
automation = MockDouyinAutomation()
