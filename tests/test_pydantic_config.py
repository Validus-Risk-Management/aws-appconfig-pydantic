import io
import json
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
    _add_start_stub(stub)

    stub.add_response(
        "get_latest_configuration",
        _build_response(
            {
                "test_field_string": "testing_string",
                "test_field_int": 42,
            },
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
    assert a.config
    assert a.config.test_field_string == "testing_string"
    assert a.config.test_field_int == 42


def test_yaml_config_returned_as_model(
    appconfig_stub: Tuple[BaseClient, Stubber, Session],
    mocker: MockerFixture,
) -> None:
    """Tests the config gets updated."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)

    stub.add_response(
        "get_latest_configuration",
        _build_response(
            {
                "test_field_string": "testing_string",
                "test_field_int": 42,
            },
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
    assert a.config
    assert a.config.test_field_string == "testing_string"
    assert a.config.test_field_int == 42


def test_config_model_parse_error(
    appconfig_stub: Tuple[BaseClient, Stubber, Session], mocker: MockerFixture
) -> None:
    """Tests the config rejected."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response(
            {
                "xxx": "testing_string",
            },
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
        assert a.config


def _build_request(next_token: str = "token1234") -> Dict[str, str]:
    return {"ConfigurationToken": next_token}


def _build_response(
    content: Union[Dict, str],
    content_type: str,
    next_token: str = "token5678",
    poll: int = 30,
) -> Dict[str, Union[str, int, StreamingBody]]:
    if content_type == "application/json":
        content_text = json.dumps(content).encode("utf-8")
    elif content_type == "application/x-yaml":
        content_text = str(yaml.dump(content)).encode("utf-8")
    elif not isinstance(content, str):
        raise ValueError("Unrecognised content.")
    else:
        content_text = content.encode("utf-8")
    return {
        "Configuration": StreamingBody(
            io.BytesIO(bytes(content_text)), len(content_text)
        ),
        "ContentType": content_type,
        "NextPollConfigurationToken": next_token,
        "NextPollIntervalInSeconds": poll,
    }


def _add_start_stub(
    stub: Stubber,
    app_id: str = "AppConfig-App",
    config_id: str = "AppConfig-Profile",
    env_id: str = "AppConfig-Env",
    poll: int = 15,
    next_token: str = "token1234",
) -> None:
    stub.add_response(
        "start_configuration_session",
        {"InitialConfigurationToken": next_token},
        {
            "ApplicationIdentifier": app_id,
            "ConfigurationProfileIdentifier": config_id,
            "EnvironmentIdentifier": env_id,
            "RequiredMinimumPollIntervalInSeconds": poll,
        },
    )
