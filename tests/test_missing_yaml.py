import sys
from importlib import reload
from typing import Any, Generator, Tuple
from unittest import mock

import boto3
import pytest
from boto3 import Session
from botocore.client import BaseClient
from botocore.stub import Stubber
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pydantic_appconfig import app_config


class TestConfig(BaseModel):
    """Test pydantic parsing."""

    __test__ = False

    test_field_string: str
    test_field_int: int

    class Config:
        """The config, including title for the JSON schema."""

        title = "TestConfig"


@pytest.fixture()
def remove_yaml() -> Generator[None, Any, None]:
    """Removes the yaml import to test error handling."""
    with mock.patch.dict(sys.modules, {"yaml": None}):
        reload(app_config)
        yield None
    reload(app_config)


def test_no_yaml_import(
    appconfig_stub: Tuple[BaseClient, Stubber, Session],
    mocker: MockerFixture,
    remove_yaml: Generator[None, Any, None],
) -> None:
    """Test the correct exception is raised when yaml can not be imported."""
    client, stub, _ = appconfig_stub
    mocker.patch.object(boto3, "client", return_value=client)

    a: app_config.AppConfigHelper[TestConfig] = app_config.AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=TestConfig,
    )
    with pytest.raises(RuntimeError) as e:
        a.handle_yaml("")
    assert e.match(
        "Configuration in YAML format received and "
        "missing yaml library; pip install pyyaml?"
    )
