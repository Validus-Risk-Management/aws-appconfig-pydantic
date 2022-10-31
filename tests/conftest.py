"""Fixtures for testing."""
from typing import Iterator, Tuple

import botocore.session
import pytest
from botocore.client import BaseClient
from botocore.session import Session
from botocore.stub import Stubber


@pytest.fixture(autouse=True)
def appconfig_stub() -> Iterator[Tuple[BaseClient, Stubber, Session]]:
    """Stubs the appconfig boto client."""
    session = botocore.session.get_session()
    client = session.create_client("appconfigdata", region_name="us-east-1")
    with Stubber(client) as stubber:
        yield client, stubber, session
        stubber.assert_no_pending_responses()


@pytest.fixture(autouse=True)
def appconfig_stub_ignore_pending() -> Iterator[Tuple[BaseClient, Stubber, Session]]:
    """Stubs the appconfig boto client without assert_no_pending_responses."""
    session = botocore.session.get_session()
    client = session.create_client("appconfigdata", region_name="us-east-1")
    with Stubber(client) as stubber:
        yield client, stubber, session
