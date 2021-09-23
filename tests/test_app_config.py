# type: ignore

import io
import json
import socket

import boto3
import botocore
import botocore.exceptions
import botocore.session
import pydantic
import pytest
import yaml
from botocore.response import StreamingBody
from freezegun import freeze_time

from pydantic_appconfig import AppConfigHelper


def _build_request(
    app="AppConfig-App",
    env="AppConfig-Env",
    profile="AppConfig-Profile",
    client_id=None,
    version="null",
):
    if client_id is None:
        client_id = socket.gethostname()
    return {
        "Application": app,
        "ClientConfigurationVersion": str(version),
        "ClientId": client_id,
        "Configuration": profile,
        "Environment": env,
    }


def _build_response(content, version, content_type):
    if content_type == "application/json":
        content_text = json.dumps(content).encode("utf-8")
    elif content_type == "application/x-yaml":
        content_text = str(yaml.dump(content)).encode("utf-8")
    else:
        content_text = content.encode("utf-8")
    return {
        "Content": StreamingBody(io.BytesIO(bytes(content_text)), len(content_text)),
        "ConfigurationVersion": version,
        "ContentType": content_type,
    }


def test_appconfig_init(appconfig_stub, mocker):
    """Tests the helper is created fine."""
    client, stub, _ = appconfig_stub
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )

    assert isinstance(a, AppConfigHelper)
    assert a.appconfig_application == "AppConfig-App"
    assert a.appconfig_environment == "AppConfig-Env"
    assert a.appconfig_profile == "AppConfig-Profile"
    assert a.config_dict is None
    assert a.config_version == "null"
    assert a._last_update_time == 0.0
    assert a.raw_config is None
    assert a.content_type is None


def test_appconfig_update(appconfig_stub, mocker):
    """Tests the config gets updated."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.config_version == "1"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"


def test_appconfig_update_interval(appconfig_stub, mocker):
    """Tests interval based config updates."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.config_version == "1"

    result = a.update_config()
    assert not result
    assert a.config_dict == "hello"
    assert a.config_version == "1"


def test_appconfig_force_update_same(appconfig_stub, mocker):
    """Tests force update."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    stub.add_response(
        "get_configuration",
        _build_response("", "1", "text/plain"),
        _build_request(version="1"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.config_version == "1"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"

    result = a.update_config(force_update=True)
    assert not result
    assert a.config_dict == "hello"
    assert a.config_version == "1"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"


def test_appconfig_force_update_new(appconfig_stub, mocker):
    """Tests force update."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    stub.add_response(
        "get_configuration",
        _build_response("world", "2", "text/plain"),
        _build_request(version="1"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.config_version == "1"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"

    result = a.update_config(force_update=True)
    assert result
    assert a.config_dict == "world"
    assert a.config_version == "2"
    assert a.raw_config == b"world"
    assert a.content_type == "text/plain"


def test_appconfig_fetch_on_init(appconfig_stub, mocker):
    """Tests update on creation."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        fetch_on_init=True,
        config_schema_model=pydantic.BaseModel(),
    )
    assert a.config_dict == "hello"
    assert a.config_version == "1"


@freeze_time("2020-08-01 12:00:00", auto_tick_seconds=20)
def test_appconfig_fetch_on_read(appconfig_stub, mocker):
    """Tests fetch on read."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    stub.add_response(
        "get_configuration",
        _build_response("world", "2", "text/plain"),
        _build_request(version="1"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        fetch_on_read=True,
        config_schema_model=pydantic.BaseModel(),
    )
    assert a.config_dict == "hello"
    assert a.config_version == "1"
    assert a.config_dict == "world"
    assert a.config_version == "2"


@freeze_time("2020-08-01 12:00:00", auto_tick_seconds=10)
def test_appconfig_fetch_interval(appconfig_stub, mocker):
    """Tests fetch interval."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response("hello", "1", "text/plain"),
        _build_request(),
    )
    stub.add_response(
        "get_configuration",
        _build_response("world", "2", "text/plain"),
        _build_request(version="1"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.config_version == "1"

    result = a.update_config()
    assert not result
    assert a.config_dict == "hello"
    assert a.config_version == "1"

    result = a.update_config()
    assert result
    assert a.config_dict == "world"
    assert a.config_version == "2"


def test_appconfig_yaml(appconfig_stub, mocker):
    """Tests yaml parsing."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response({"hello": "world"}, "1", "application/x-yaml"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    a.update_config()
    assert a.config_dict == {"hello": "world"}
    assert a.config_version == "1"
    assert a.content_type == "application/x-yaml"


def test_appconfig_json(appconfig_stub, mocker):
    """Tests JSON parsing."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response({"hello": "world"}, "1", "application/json"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    a.update_config()
    assert a.config_dict == {"hello": "world"}
    assert a.config_version == "1"
    assert a.content_type == "application/json"


def test_appconfig_client(appconfig_stub, mocker):
    """Tests the client."""
    client, stub, _ = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response({"hello": "world"}, "1", "application/json"),
        _build_request(client_id="hello"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        client_id="hello",
        config_schema_model=pydantic.BaseModel(),
    )
    a.update_config()


def test_appconfig_session(appconfig_stub, mocker):
    """Tests the session."""
    client, stub, session = appconfig_stub
    stub.add_response(
        "get_configuration",
        _build_response({"hello": "world"}, "1", "application/json"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    mocker.patch.object(boto3.Session, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        session=session,
        config_schema_model=pydantic.BaseModel(),
    )
    a.update_config()


def test_bad_json(appconfig_stub, mocker):
    """Tests incorrect JSON config."""
    client, stub, session = appconfig_stub
    content_text = """{"broken": "json",}""".encode("utf-8")
    stub.add_response(
        "get_configuration",
        {
            "Content": StreamingBody(
                io.BytesIO(bytes(content_text)), len(content_text)
            ),
            "ConfigurationVersion": "1",
            "ContentType": "application/json",
        },
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    with pytest.raises(
        ValueError,
        match="Expecting property name enclosed in double quotes",
    ):
        a.update_config()


def test_bad_yaml(appconfig_stub, mocker):
    """Tests incorrect yaml config."""
    client, stub, session = appconfig_stub
    content_text = """
    broken:
        - yaml
    - content
    """.encode(
        "utf-8"
    )
    stub.add_response(
        "get_configuration",
        {
            "Content": StreamingBody(
                io.BytesIO(bytes(content_text)), len(content_text)
            ),
            "ConfigurationVersion": "1",
            "ContentType": "application/x-yaml",
        },
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    with pytest.raises(
        ValueError,
        match="Unable to parse YAML configuration data at line 4 column 5",
    ):
        a.update_config()


def test_unknown_content_type(appconfig_stub, mocker):
    """Tests unknown content response."""
    client, stub, session = appconfig_stub
    content_text = """hello world""".encode("utf-8")
    stub.add_response(
        "get_configuration",
        {
            "Content": StreamingBody(
                io.BytesIO(bytes(content_text)), len(content_text)
            ),
            "ConfigurationVersion": "1",
            "ContentType": "image/jpeg",
        },
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel(),
    )
    a.update_config()
    assert a.config_dict == b"hello world"
    assert a.content_type == "image/jpeg"
    assert a.raw_config == content_text


def test_bad_request(appconfig_stub_ignore_pending, mocker):
    """Tests bad request."""
    client, stub, session = appconfig_stub_ignore_pending
    content_text = """hello world""".encode("utf-8")
    stub.add_response(
        "get_configuration",
        {
            "Content": StreamingBody(
                io.BytesIO(bytes(content_text)), len(content_text)
            ),
            "ConfigurationVersion": "1",
            "ContentType": "image/jpeg",
        },
        _build_request("", "", ""),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    with pytest.raises(botocore.exceptions.ParamValidationError):
        AppConfigHelper(
            "", "", "", 15, config_schema_model=pydantic.BaseModel()
        ).update_config()


def test_bad_interval(appconfig_stub, mocker):
    """Tests bad interval."""
    client, stub, session = appconfig_stub
    mocker.patch.object(boto3, "client", return_value=client)
    with pytest.raises(ValueError, match="max_config_age must be at least 15 seconds"):
        _ = AppConfigHelper(
            "Any", "Any", "Any", 10, config_schema_model=pydantic.BaseModel()
        )
