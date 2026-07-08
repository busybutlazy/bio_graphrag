from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # NOTE: the `change_me` passwords below are placeholder defaults so the local
    # Docker demo starts with no config. They are NOT safe for any shared/exposed
    # deployment — override every credential via .env / environment there.
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    app_env: str = "local"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "biology_graphrag"
    postgres_user: str = "biology_app"
    postgres_password: str = "change_me"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "change_me"

    qdrant_url: str = "http://qdrant:6333"

    openai_api_key: str = ""
    llm_provider: str = "openai"

    # Named API keys guarding the /admin endpoints, as a comma-separated list of
    # "vendor:key" pairs (e.g. "acme:key1,globex:key2"). Empty = auth disabled,
    # so the local demo and tests run open. Set this in any exposed deployment.
    admin_api_keys: str = ""


settings = Settings()
