Pydantic AWS AppConfig
=======================

.. image:: https://badge.fury.io/py/pydantic-appconfig.svg
    :target: https://badge.fury.io/py/pydantic-appconfig


.. image:: https://img.shields.io/pypi/pyversions/pydantic-appconfig
    :target: https://img.shields.io/pypi/pyversions/pydantic-appconfig


Ever wanted to use
`AWS AppConfig <https://aws.amazon.com/systems-manager/features/appconfig>`_
for your Python app, but can't bear configs without
`pydantic <https://pydantic-docs.helpmanual.io/>`_?

Well, your days of using evil `.env` or `.ini` files, `ENVIRONMENT` variables or even custom providers is over!

With just a simple

.. code-block:: shell

    pip install pydantic-appconfig

With a lot of inspiration from this AWS `sample <https://github.com/aws-samples/sample-python-helper-aws-appconfig>`_.


Introducing `pydantic_appconfig`.

#. Set yourself up with your favourite `pydantic.BaseModel`:

    .. code-block:: python

        class MyAppConfig(pydantic.BaseModel):
            """My app config."""

            test_field_string: str
            test_field_int: int

            class Config:
                """The pydantic config, including title for the JSON schema."""

                title = "MyAppConfig"

#. Set up the config helper using your shiny config class:

    .. code-block:: python

        my_config: AppConfigHelper[MyAppConfig] = AppConfigHelper(
            appconfig_application="AppConfig-App",
            appconfig_environment="AppConfig-Env",
            appconfig_profile="AppConfig-Profile",
            max_config_age=15,
            fetch_on_init=True,
            config_schema_model=MyAppConfig,
        )


#. Use it:

    .. code-block:: python

        my_val = my_config.config.test_field_string


AWS AppConfig also has support for `validators <https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-creating-configuration-and-profile-validators.html>`_.

Pydantic is able to generate a JSON schema for you to upload:

   .. code-block:: python

       print(MyAppConfig.schema_json(indent=2))

   .. code-block:: JSON

       {
         "title": "MyAppConfig",
         "description": "My app config.",
         "type": "object",
         "properties": {
           "test_field_string": {
             "title": "Test Field String",
             "type": "string"
           },
           "test_field_int": {
             "title": "Test Field Int",
             "type": "integer"
           }
         },
         "required": [
           "test_field_string",
           "test_field_int"
         ]
       }
