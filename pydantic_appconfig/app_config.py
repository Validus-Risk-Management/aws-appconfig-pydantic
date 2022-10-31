"""AppConfig Helper class."""


import json
import time
from typing import Any, Dict, Generic, Optional, Type, TypeVar, Union

import boto3
import botocore.exceptions
import pydantic

try:
    import yaml

    yaml_available = True
except ImportError:
    yaml_available = False

ModelType = TypeVar("ModelType", bound=pydantic.BaseModel)


class AppConfigHelper(Generic[ModelType]):
    """AWS AppConfig Helper class.

    Helps you fetch configuration from AWS AppConfig easily. Parses JSON and
    YAML configurations into native Python dicts, and keeps plain text as
    str.

    `appconfig_application`, `appconfig_environment` and `appconfig_profile`
    are the names or IDs of the AWS AppConfig application, environment and
    profile (configuration) respectively.

    `max_config_age` is the minimum interval in seconds between attempts to
    update the configuration. Set it low enough that your application
    receives new configuration in good time, but not so high that you are
    unnecessarily polling the AWS AppConfig service. A minimum of 15 seconds
    is enforced to help avoid throttling. Note that the value can be updated
    internally by the response from AppConfig.
    If you need to override credentials or AWS Region, set `session` to a
    preconfigured `boto3.Session` object.

    If `fetch_on_init` is set, attempt to fetch configuration when the
    instance is created.

    If `fetch_on_read` is set, every time the `config` property is read, the
    configuration will be refreshed (if it has been at least `max_config_age`
    seconds since the last refresh).
    """

    def __init__(
        self,
        appconfig_application: str,
        appconfig_environment: str,
        appconfig_profile: str,
        max_config_age: int,
        *,
        config_schema_model: Type[ModelType],
        session: Optional[boto3.Session] = None,
        fetch_on_init: bool = False,
        fetch_on_read: bool = False,
    ) -> None:
        """Init a new helper."""
        if isinstance(session, boto3.Session):
            self._client = session.client("appconfigdata")
        else:
            self._client = boto3.client("appconfigdata")
        self._appconfig_profile = appconfig_profile
        self._appconfig_environment = appconfig_environment
        self._appconfig_application = appconfig_application
        self._config_schema_model = config_schema_model
        if max_config_age < 15:
            raise ValueError("max_config_age must be at least 15 seconds")
        self._max_config_age = max_config_age
        self._last_update_time = 0.0
        self._config: Optional[Union[Dict[Any, Any], str, bytes]] = None
        self._raw_config: Optional[bytes] = None
        self._content_type: Optional[str] = None
        self._fetch_on_read = fetch_on_read
        self._next_config_token = None  # type: Optional[str]
        self._poll_interval = max_config_age
        if fetch_on_init:
            self.update_config()

    @property
    def appconfig_profile(self) -> str:
        """The profile in use."""
        return self._appconfig_profile

    @property
    def appconfig_environment(self) -> str:
        """The environment in use."""
        return self._appconfig_environment

    @property
    def appconfig_application(self) -> str:
        """The application in use."""
        return self._appconfig_application

    @property
    def config(self) -> Optional[ModelType]:
        """The application configuration content.

        If initialised with `fetch_on_read` = True, will attempt to update the
        config before returning it to you.

        Returned as the Pydantic model specified in `config_schema_model`
        """
        return (
            self._config_schema_model.parse_obj(self.config_dict)
            if self.config_dict
            else None
        )

    @property
    def config_dict(self) -> Optional[Union[Dict[Any, Any], str, bytes]]:
        """The application configuration content.

        If initialised with `fetch_on_read` = True, will attempt to update the
        config before returning it to you.
        """
        if self._fetch_on_read:
            self.update_config()
        return self._config

    @property
    def raw_config(self) -> Optional[bytes]:
        """The application configuration content retrieved from AppConfig.

        No processing is performed on this content. Accessing this property does not
        trigger an update, even if `fetch_on_read` is True.
        """
        return self._raw_config

    @property
    def content_type(self) -> Optional[str]:
        """The content type of the configuration retrieved from AppConfig."""
        return self._content_type

    def start_session(self) -> None:
        """Start the session and receive the next config token and poll interval."""
        response = self._client.start_configuration_session(
            ApplicationIdentifier=self._appconfig_application,
            ConfigurationProfileIdentifier=self._appconfig_profile,
            EnvironmentIdentifier=self._appconfig_environment,
            RequiredMinimumPollIntervalInSeconds=self._max_config_age,
        )
        self._next_config_token = response["InitialConfigurationToken"]
        self._poll_interval = self._max_config_age

    def update_config(self, force_update: bool = False) -> bool:
        """Request the latest configuration.

        `force_update`: set to True to request configuration event if it's not time yet

        Returns True if a new version of configuration was received. False
        indicates that no attempt was made, or that no new version was found.
        """
        if (
            time.time() - self._last_update_time < self._poll_interval
        ) and not force_update:
            return False

        if self._next_config_token is None:
            self.start_session()

        response = self._safe_get_latest_configuration()

        self._next_config_token = response["NextPollConfigurationToken"]
        self._poll_interval = int(response["NextPollIntervalInSeconds"])

        content: bytes = response["Configuration"].read()
        if content == b"":
            self._last_update_time = time.time()
            return False

        if response["ContentType"] == "application/x-yaml":
            self.handle_yaml(content)
        elif response["ContentType"] == "application/json":
            self.handle_json(content)
        elif response["ContentType"] == "text/plain":
            self._config = content.decode("utf-8")
        else:
            self._config = content

        self._last_update_time = time.time()
        self._raw_config = content
        self._content_type = response["ContentType"]
        return True

    def _safe_get_latest_configuration(self) -> Dict:
        try:
            response = self._client.get_latest_configuration(
                ConfigurationToken=self._next_config_token
            )
        except botocore.exceptions.ClientError:
            self.start_session()
            response = self._client.get_latest_configuration(
                ConfigurationToken=self._next_config_token
            )
        return response

    def handle_json(self, content: Any) -> None:
        """Deals with JSON configs."""
        try:
            self._config = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(error.msg) from error

    def handle_yaml(self, content: Any) -> None:
        """Deals with yaml configs."""
        if not yaml_available:
            raise RuntimeError(
                "Configuration in YAML format received and missing yaml library;"
                " pip install pyyaml?"
            )
        try:
            self._config = yaml.safe_load(content)
        except yaml.YAMLError as error:
            message = "Unable to parse YAML configuration data"
            if hasattr(error, "problem_mark"):
                message += " at line {} column {}".format(
                    error.problem_mark.line + 1,  # type: ignore
                    error.problem_mark.column + 1,  # type: ignore
                )
            raise ValueError(message) from error
