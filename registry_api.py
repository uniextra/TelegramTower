import ipaddress
import logging
import re
import socket
import urllib.parse
from typing import Any, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DIGEST_REGEX = re.compile(r"^sha256:[a-f0-9]{64}$")
ALLOWED_REALM_HOSTS = {
    "auth.docker.io",
    "registry-1.docker.io",
    "ghcr.io",
    "quay.io",
    "mcr.microsoft.com",
    "registry.k8s.io",
}


def _get_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def is_safe_ip(host: str) -> bool:
    """Verifies that an IP or hostname does not point to private/loopback/link-local ranges."""
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
        return True
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(host, 443)
        for _, _, _, _, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return False
    except Exception:
        # If resolution fails, don't allow
        return False
    return True


def is_allowed_realm(realm_url: str, expected_registry: str) -> bool:
    """Validates that authentication realm is HTTPS and on an approved registry host (SSRF protection)."""
    parsed = urllib.parse.urlparse(realm_url)
    if parsed.scheme != "https":
        return False
    host = parsed.hostname
    if not host:
        return False

    host_lower = host.lower()
    if not is_safe_ip(host_lower):
        return False

    if host_lower in ALLOWED_REALM_HOSTS:
        return True

    if host_lower.endswith(".gcr.io") or host_lower.endswith(".pkg.dev") or host_lower.endswith(".amazonaws.com"):
        return True

    exp_lower = expected_registry.split(":")[0].lower()
    if host_lower == exp_lower or host_lower.endswith(f".{exp_lower}"):
        return True

    return False


class RegistryFetcher:
    """
    Handles fetching the creation date of an image directly from the Docker Registry / OCI Registry.
    """

    @staticmethod
    def parse_image_name(image_name: str) -> Tuple[str, str, str]:
        """
        Parses an image name into registry, repository, and tag.
        Handles default Docker Hub registry and library/ prefix.
        """
        # Strip digest if present (e.g. image@sha256:...)
        if "@" in image_name:
            image_name = image_name.split("@")[0]

        registry = "registry-1.docker.io"
        tag = "latest"

        parts = image_name.split("/")

        if len(parts) == 1:
            # e.g., "ubuntu" or "ubuntu:20.04"
            repo = f"library/{parts[0]}"
        elif len(parts) == 2 and (
            "." not in parts[0] and ":" not in parts[0] and parts[0] != "localhost"
        ):
            # e.g., "linuxserver/sonarr"
            repo = f"{parts[0]}/{parts[1]}"
        else:
            # e.g., "ghcr.io/linuxserver/sonarr"
            registry = parts[0]
            repo = "/".join(parts[1:])

        if ":" in repo:
            repo_parts = repo.split(":", 1)
            repo = repo_parts[0]
            tag = repo_parts[1]

        return registry, repo, tag

    @staticmethod
    def get_auth_token(registry: str, repository: str) -> Optional[str]:
        """
        Retrieves a Bearer token for the given registry and repository by triggering a 401 challenge.
        Protects against SSRF via realm validation.
        """
        session = _get_session()
        try:
            url = f"https://{registry}/v2/"
            resp = session.get(url, timeout=10)

            if resp.status_code == 401 and "Www-Authenticate" in resp.headers:
                auth_header = resp.headers["Www-Authenticate"]

                match_realm = re.search(r'realm="([^"]+)"', auth_header)
                match_service = re.search(r'service="([^"]+)"', auth_header)

                if not match_realm:
                    return None

                realm = match_realm.group(1)
                if not is_allowed_realm(realm, registry):
                    logger.warning(
                        f"SSRF Protection: Blocked auth challenge realm '{realm}' for registry '{registry}'."
                    )
                    return None

                service = match_service.group(1) if match_service else registry

                token_params = {
                    "service": service,
                    "scope": f"repository:{repository}:pull",
                }

                token_resp = session.get(realm, params=token_params, timeout=10)
                if token_resp.status_code == 200:
                    data = token_resp.json()
                    return data.get("token") or data.get("access_token")
            elif resp.status_code == 200:
                # No auth required
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error authenticating with registry {registry}: {e}")
        return None

    @staticmethod
    def fetch_manifest(
        registry: str, repository: str, reference: str, token: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches the manifest. Handles multi-arch lists by picking linux/amd64 or linux/arm64.
        """
        headers = {
            "Accept": (
                "application/vnd.docker.distribution.manifest.v2+json, "
                "application/vnd.oci.image.manifest.v1+json, "
                "application/vnd.docker.distribution.manifest.list.v2+json, "
                "application/vnd.oci.image.index.v1+json"
            )
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # If reference is a digest, validate format
        if reference.startswith("sha256:") and not DIGEST_REGEX.match(reference):
            logger.warning(f"Invalid manifest digest reference: {reference}")
            return None

        safe_repo = urllib.parse.quote(repository, safe="/")
        safe_ref = urllib.parse.quote(reference, safe=":@")
        url = f"https://{registry}/v2/{safe_repo}/manifests/{safe_ref}"

        session = _get_session()
        try:
            resp = session.get(url, headers=headers, timeout=10)

            if resp.status_code != 200:
                logger.error(
                    f"Failed to fetch manifest for {repository}:{reference} - Status: {resp.status_code}"
                )
                return None

            manifest = resp.json()
            media_type = manifest.get("mediaType", "")

            # If it's a manifest list/index, find the linux architecture manifest and fetch it
            if "manifest.list" in media_type or "image.index" in media_type:
                manifests = manifest.get("manifests", [])
                for m in manifests:
                    platform = m.get("platform", {})
                    if (
                        platform.get("architecture") in ["amd64", "arm64"]
                        and platform.get("os") == "linux"
                    ):
                        digest = m.get("digest")
                        if digest and DIGEST_REGEX.match(digest):
                            return RegistryFetcher.fetch_manifest(
                                registry, repository, digest, token
                            )

                # Fallback to first if matching linux not found
                if manifests and manifests[0].get("digest"):
                    first_digest = manifests[0]["digest"]
                    if DIGEST_REGEX.match(first_digest):
                        return RegistryFetcher.fetch_manifest(
                            registry, repository, first_digest, token
                        )

            return manifest
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching manifest for {repository}:{reference}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing manifest for {repository}:{reference}: {e}")
            return None

    @staticmethod
    def extract_version_from_labels(labels: Optional[Dict[str, Any]]) -> Optional[str]:
        if not labels or not isinstance(labels, dict):
            return None

        for key in (
            "org.opencontainers.image.version",
            "version",
            "org.label-schema.version",
            "image.version",
        ):
            val = labels.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

        build_version = labels.get("build_version")
        if build_version and isinstance(build_version, str):
            match = re.search(r"version:-\s*([^\s]+)", build_version, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                if not val.lower().startswith("build-date"):
                    return val
            cleaned = build_version.strip()
            if cleaned and not cleaned.lower().startswith("linuxserver.io"):
                return cleaned

        return None

    @staticmethod
    def extract_source_from_labels(labels: Optional[Dict[str, Any]]) -> Optional[str]:
        if not labels or not isinstance(labels, dict):
            return None

        for key in (
            "org.opencontainers.image.source",
            "org.opencontainers.image.url",
            "org.label-schema.vcs-url",
            "org.label-schema.url",
        ):
            val = labels.get(key)
            if val and isinstance(val, str) and val.strip():
                url = val.strip()
                if url.startswith("git@github.com:"):
                    url = "https://github.com/" + url[len("git@github.com:") :].removesuffix(".git")
                elif url.startswith("git://"):
                    url = "https://" + url[len("git://") :].removesuffix(".git")
                elif url.startswith(("github.com/", "gitlab.com/")):
                    url = "https://" + url
                if url.startswith(("http://", "https://")):
                    return url

        return None

    @staticmethod
    def get_remote_image_info(image_name: str) -> Optional[Dict[str, Any]]:
        registry, repository, tag = RegistryFetcher.parse_image_name(image_name)

        try:
            token = RegistryFetcher.get_auth_token(registry, repository)
            manifest = RegistryFetcher.fetch_manifest(registry, repository, tag, token)

            if not manifest or "config" not in manifest:
                return None

            config_digest = manifest["config"].get("digest")
            if not config_digest or not DIGEST_REGEX.match(config_digest):
                logger.warning(f"Invalid or missing config digest: {config_digest}")
                return None

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            safe_repo = urllib.parse.quote(repository, safe="/")
            blob_url = f"https://{registry}/v2/{safe_repo}/blobs/{config_digest}"

            session = _get_session()
            blob_resp = session.get(blob_url, headers=headers, timeout=10)

            if blob_resp.status_code == 200:
                config_json = blob_resp.json()
                created = config_json.get("created")

                labels = config_json.get("config", {}).get("Labels") or {}
                version = RegistryFetcher.extract_version_from_labels(labels)
                source = RegistryFetcher.extract_source_from_labels(labels)

                return {
                    "created": created,
                    "version": version,
                    "source": source,
                    "labels": labels,
                    "config": config_json.get("config", {}),
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error getting remote info for {image_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to get remote info for {image_name}: {e}")

        return None
