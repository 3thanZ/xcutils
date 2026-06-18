"""CLI-session based authentication for xcutils.

Per the project constitution, utilities authenticate by reusing the user's
existing cloud CLI session. No service account keys, connection strings, or
credential files are accepted, stored, or logged.

  - Azure -> ``AzureCliCredential`` (established by ``az login``)
  - GCP   -> Application Default Credentials (``gcloud auth application-default login``)

Cloud SDKs are imported lazily inside each function so that a utility only needs
the SDK for the clouds it actually touches, and so import errors surface as clear
guidance rather than module-load failures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # imported only for type checkers; avoids hard runtime dependency
    from azure.identity import AzureCliCredential


class AuthError(RuntimeError):
    """Raised when a required cloud CLI session is missing or expired.

    The message tells the user exactly which command to run.
    """


def azure_cli_credential() -> AzureCliCredential:
    """Return an Azure credential backed by the local ``az`` CLI session.

    Raises:
        AuthError: if ``az login`` has not been run (or the SDK is unavailable).
    """
    try:
        from azure.identity import AzureCliCredential
    except ImportError as exc:  # pragma: no cover - environment issue
        raise AuthError(
            "azure-identity is not installed. Run: uv sync"
        ) from exc

    credential = AzureCliCredential()
    try:
        # Probe the session early so failures are reported up front, not mid-stream.
        credential.get_token("https://storage.azure.com/.default")
    except Exception as exc:  # noqa: BLE001 - surface any auth failure uniformly
        raise AuthError(
            "Azure CLI session not available. Authenticate with:\n"
            "    az login\n"
            f"(underlying error: {exc})"
        ) from exc
    return credential


def gcp_credentials() -> tuple[Any, str | None]:
    """Return Google Application Default Credentials and the active project.

    Raises:
        AuthError: if ADC has not been configured (or the SDK is unavailable).
    """
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError
    except ImportError as exc:  # pragma: no cover - environment issue
        raise AuthError(
            "google-cloud-storage is not installed. Run: uv sync"
        ) from exc

    try:
        credentials, project = google.auth.default()
    except DefaultCredentialsError as exc:
        raise AuthError(
            "Google Cloud Application Default Credentials not found. Authenticate with:\n"
            "    gcloud auth application-default login\n"
            f"(underlying error: {exc})"
        ) from exc
    return credentials, project
