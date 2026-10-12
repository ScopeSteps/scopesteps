import uvicorn

from scopesteps.api.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "scopesteps.api.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "local",
    )


if __name__ == "__main__":
    main()
