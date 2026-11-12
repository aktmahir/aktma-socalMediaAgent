from social_media_agent.web import create_app


def create_wsgi_app():
    app = create_app()
    required_settings = {
        "browser authentication": app.config["AUTHENTICATION_CONFIGURED"],
        "Prometheus scrape authentication": app.config["PROMETHEUS_AUTH_CONFIGURED"],
        "a stable session secret": app.config["PRODUCTION_SECRET_CONFIGURED"],
        "shared rate-limit storage": app.config["RATELIMIT_SHARED_STORAGE"],
    }
    missing_settings = [
        name for name, configured in required_settings.items() if not configured
    ]
    if missing_settings:
        raise RuntimeError(
            "WSGI deployment requires " + ", ".join(missing_settings) + "."
        )
    return app
