# type: ignore

import datetime
import io
import json
import time

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


def _build_request(next_token="fake"):
    return {"ConfigurationToken": next_token}


def _build_response(content, content_type, next_token="fake", poll=30):
    if content_type == "application/json":
        content_text = json.dumps(content).encode("utf-8")
    elif content_type == "application/x-yaml":
        content_text = str(yaml.dump(content)).encode("utf-8")
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
    stub,
    app_id="AppConfig-App",
    config_id="AppConfig-Profile",
    env_id="AppConfig-Env",
    poll=15,
    next_token="fake",
):
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


def test_appconfig_init(appconfig_stub, mocker):
    """Tests the helper is created fine."""
    client, stub, _ = appconfig_stub
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )

    assert isinstance(a, AppConfigHelper)
    assert a.appconfig_application == "AppConfig-App"
    assert a.appconfig_environment == "AppConfig-Env"
    assert a.appconfig_profile == "AppConfig-Profile"
    assert a.config is None
    assert a._last_update_time == 0.0
    assert a.raw_config is None
    assert a.content_type is None
    assert a._poll_interval == 15
    assert a._next_config_token is None


def test_appconfig_update(appconfig_stub, mocker):
    """Tests the config gets updated."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "fake"
    assert a._poll_interval == 30


def test_appconfig_update_interval(appconfig_stub, mocker):
    """Tests interval based config updates."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a._next_config_token == "fake"
    assert a._poll_interval == 30

    result = a.update_config()
    assert not result
    assert a.config_dict == "hello"
    assert a._next_config_token == "fake"


def test_appconfig_force_update_same(appconfig_stub, mocker):
    """Tests force update."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain"),
        _build_request(),
    )
    stub.add_response(
        "get_latest_configuration",
        _build_response("", "text/plain"),
        _build_request(next_token="fake"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "fake"
    assert a._poll_interval == 30

    result = a.update_config(force_update=True)
    assert not result
    assert a.config_dict == "hello"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "fake"
    assert a._poll_interval == 30


def test_appconfig_force_update_new(appconfig_stub, mocker):
    """Tests force update."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain"),
        _build_request(),
    )
    stub.add_response(
        "get_latest_configuration",
        _build_response("world", "text/plain", next_token="token9012"),
        _build_request(next_token="fake"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "fake"
    assert a._poll_interval == 30

    result = a.update_config(force_update=True)
    assert result
    assert a.config_dict == "world"
    assert a.raw_config == b"world"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "token9012"
    assert a._poll_interval == 30


def test_appconfig_update_bad_request(appconfig_stub, mocker):
    """Tests client error."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain", next_token="fake"),
        _build_request(),
    )
    stub.add_client_error(
        "get_latest_configuration",
        service_error_code="BadRequestException",
    )
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("world", "text/plain", next_token="token9012"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    result = a.update_config()
    assert result
    assert a.config_dict == "hello"
    assert a.raw_config == b"hello"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "fake"
    assert a._poll_interval == 30

    result = a.update_config(force_update=True)
    assert result
    assert a.config_dict == "world"
    assert a.raw_config == b"world"
    assert a.content_type == "text/plain"
    assert a._next_config_token == "token9012"
    assert a._poll_interval == 30


def test_appconfig_fetch_on_init(appconfig_stub, mocker):
    """Tests fetch on init."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        fetch_on_init=True,
        config_schema_model=pydantic.BaseModel,
    )
    assert a.config_dict == "hello"


@freeze_time("2020-08-01 12:00:00", auto_tick_seconds=20)
def test_appconfig_fetch_on_read(appconfig_stub, mocker):
    """Tests fetch on read."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response("hello", "text/plain", poll=15),
        _build_request(),
    )
    stub.add_response(
        "get_latest_configuration",
        _build_response("world", "text/plain", next_token="token9012"),
        _build_request(next_token="fake"),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        fetch_on_read=True,
        config_schema_model=pydantic.BaseModel,
    )
    assert a.config_dict == "hello"
    assert a._next_config_token == "fake"
    assert a.config_dict == "world"
    assert a._next_config_token == "token9012"


def test_appconfig_fetch_interval(appconfig_stub, mocker):
    """Tests fetch interval."""
    with freeze_time("2020-08-01 12:00:00") as frozen_time:
        tick_amount = datetime.timedelta(seconds=10)
        client, stub, _ = appconfig_stub
        _add_start_stub(stub)
        stub.add_response(
            "get_latest_configuration",
            _build_response("hello", "text/plain", poll=15),
            _build_request(),
        )
        stub.add_response(
            "get_latest_configuration",
            _build_response("world", "text/plain", poll=15, next_token="fake"),
            _build_request(next_token="fake"),
        )
        mocker.patch.object(boto3, "client", return_value=client)
        a = AppConfigHelper(
            "AppConfig-App",
            "AppConfig-Env",
            "AppConfig-Profile",
            15,
            config_schema_model=pydantic.BaseModel,
        )
        result = a.update_config()
        update_time = time.time()
        assert result
        assert a.config_dict == "hello"
        assert a._last_update_time == update_time

        frozen_time.tick(tick_amount)
        result = a.update_config()
        assert not result
        assert a.config_dict == "hello"
        assert a._last_update_time == update_time

        frozen_time.tick(tick_amount)
        result = a.update_config()
        assert result
        assert a.config_dict == "world"
        assert a._next_config_token == "fake"
        assert a._last_update_time == time.time()


def test_appconfig_fetch_no_change(appconfig_stub, mocker):
    """Test nothing changes."""
    with freeze_time("2020-08-01 12:00:00") as frozen_time:
        tick_amount = datetime.timedelta(seconds=10)
        client, stub, _ = appconfig_stub
        _add_start_stub(stub)
        stub.add_response(
            "get_latest_configuration",
            _build_response("hello", "text/plain", poll=15),
            _build_request(),
        )
        stub.add_response(
            "get_latest_configuration",
            _build_response("", "text/plain", poll=15, next_token="fake"),
            _build_request(next_token="fake"),
        )
        mocker.patch.object(boto3, "client", return_value=client)
        a = AppConfigHelper(
            "AppConfig-App",
            "AppConfig-Env",
            "AppConfig-Profile",
            15,
            config_schema_model=pydantic.BaseModel,
        )
        result = a.update_config()
        update_time = time.time()
        assert result
        assert a.config_dict == "hello"
        assert a._last_update_time == update_time

        frozen_time.tick(tick_amount)
        frozen_time.tick(tick_amount)

        result = a.update_config()
        assert not result
        assert a.config_dict == "hello"
        assert a._next_config_token == "fake"
        assert a._last_update_time == time.time()


def test_appconfig_yaml(appconfig_stub, mocker):
    """Test with yaml."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response({"hello": "world"}, "application/x-yaml"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    a.update_config()
    assert a.config_dict == {"hello": "world"}
    assert a.content_type == "application/x-yaml"


def test_appconfig_json(appconfig_stub, mocker):
    """Test with json."""
    client, stub, _ = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response({"hello": "world"}, "application/json"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    a.update_config()
    assert a.config_dict == {"hello": "world"}
    assert a.content_type == "application/json"


def test_appconfig_session(appconfig_stub, mocker):
    """Test using with a Session."""
    client, stub, session = appconfig_stub
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response({"hello": "world"}, "application/json"),
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
        config_schema_model=pydantic.BaseModel,
    )
    a.update_config()


def test_bad_json(appconfig_stub, mocker):
    """Tests incorrect JSON config."""
    client, stub, session = appconfig_stub
    content_text = """{"broken": "json",}""".encode("utf-8")
    _add_start_stub(stub)
    broken_response = _build_response({}, "application/json")
    broken_response["Configuration"] = StreamingBody(
        io.BytesIO(bytes(content_text)), len(content_text)
    )
    stub.add_response(
        "get_latest_configuration",
        broken_response,
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
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
    _add_start_stub(stub)
    broken_response = _build_response({}, "application/x-yaml")
    broken_response["Configuration"] = StreamingBody(
        io.BytesIO(bytes(content_text)), len(content_text)
    )
    stub.add_response(
        "get_latest_configuration",
        broken_response,
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    with pytest.raises(
        ValueError,
        match="Unable to parse YAML configuration data at line 4 column 5",
    ):
        a.update_config()


def test_unknown_content_type(appconfig_stub, mocker):
    """Tests unknown content response."""
    client, stub, session = appconfig_stub
    content_text = "hello world"
    _add_start_stub(stub)
    stub.add_response(
        "get_latest_configuration",
        _build_response(content_text, "image/jpeg"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    a = AppConfigHelper(
        "AppConfig-App",
        "AppConfig-Env",
        "AppConfig-Profile",
        15,
        config_schema_model=pydantic.BaseModel,
    )
    a.update_config()
    assert a.config_dict == b"hello world"
    assert a.content_type == "image/jpeg"
    assert a.raw_config == content_text.encode("utf-8")


def test_bad_request(appconfig_stub_ignore_pending, mocker):
    """Tests bad request."""
    client, stub, session = appconfig_stub_ignore_pending
    content_text = "hello world"
    _add_start_stub(stub, "", "", "")
    stub.add_response(
        "get_latest_configuration",
        _build_response(content_text, "image/jpeg"),
        _build_request(),
    )
    mocker.patch.object(boto3, "client", return_value=client)
    with pytest.raises(botocore.exceptions.ParamValidationError):
        AppConfigHelper(
            "", "", "", 15, config_schema_model=pydantic.BaseModel
        ).update_config()


def test_bad_interval(appconfig_stub, mocker):
    """Tests bad interval."""
    client, stub, session = appconfig_stub
    mocker.patch.object(boto3, "client", return_value=client)
    with pytest.raises(ValueError, match="max_config_age must be at least 15 seconds"):
        _ = AppConfigHelper(
            "Any", "Any", "Any", 10, config_schema_model=pydantic.BaseModel
        )
