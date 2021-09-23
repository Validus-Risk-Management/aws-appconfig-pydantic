import io
import json
import socket
from typing import Dict, Tuple, Union

import boto3
import pytest
import yaml
from botocore.client import BaseClient
from botocore.response import StreamingBody
from botocore.session import Session
from botocore.stub import Stubber
from pydantic import BaseModel, ValidationError
from pytest_mock import MockerFixture

from pydantic_appconfig import AppConfigHelper


class TestConfig(BaseModel):
    """Test pydantic parsing."""

    __test__ = False

    test_field_string: str
    test_field_int: int

    class Config:
        """The config, including title for the JSON schema."""

        title = "TestConfig"


def test_config_returned_as_model(
    appconfig_stub: Tuple[BaseClient, Stubber, Session],
    mocker: MockerFixture,
) -> None:
    """Tests the config gets updated."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response(
            {
                "test_field_string": "testing_string",
                "test_field_int": 42,
            },
            "1",
            "application/json",
        ),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a: AppConfigHelper[TestConfig] = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=TestConfig,
    )
    result = a.update_config()
    assert result
    assert a.config.test_field_string == "testing_string"
    assert a.config.test_field_int == 42
    assert a.config_version == "1"


def test_yaml_config_returned_as_model(
    appconfig_stub: Tuple[BaseClient, Stubber, Session],
    mocker: MockerFixture,
) -> None:
    """Tests the config gets updated."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response(
            {
                "test_field_string": "testing_string",
                "test_field_int": 42,
            },
            "1",
            "application/x-yaml",
        ),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a: AppConfigHelper[TestConfig] = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=TestConfig,
    )
    result = a.update_config()
    assert result
    assert a.config.test_field_string == "testing_string"
    assert a.config.test_field_int == 42
    assert a.config_version == "1"


def test_config_model_parse_error(
    appconfig_stub: Tuple[BaseClient, Stubber, Session], mocker: MockerFixture
) -> None:
    """Tests the config rejected."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response(
            {
                "xxx": "testing_string",
            },
            "1",
            "application/json",
        ),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a: AppConfigHelper[TestConfig] = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=TestConfig,
    )
    result = a.update_config()
    assert result
    with pytest.raises(ValidationError):
        assert a.config.test_field_string


def _build_request(
    app: str = "AppConfig-App",
    env: str = "AppConfig-Env",
    profile: str = "AppConfig-Profile",
    client_id: str = None,
    version: str = "null",
) -> Dict[str, str]:
    if client_id is None:
        client_id = socket.gethostname()
    return {
        "Application": app,
        "ClientConfigurationVersion": str(version),
        "ClientId": client_id,
        "Configuration": profile,
        "Environment": env,
    }


def _build_response(
    content: Union[Dict, str], version: str, content_type: str
) -> Dict[str, Union[str, StreamingBody]]:
    if content_type == "application/json":
        content_text = json.dumps(content).encode("utf-8")
    elif content_type == "application/x-yaml":
        content_text = str(yaml.dump(content)).encode("utf-8")
    elif not isinstance(content, str):
        raise ValueError("Unrecognised content.")
    else:
        content_text = content.encode("utf-8")
    return {
        "Content": StreamingBody(io.BytesIO(bytes(content_text)), len(content_text)),
        "ConfigurationVersion": version,
        "ContentType": content_type,
    }
