import logging
import re

import requests

logger = logging.getLogger(__name__)


class RegistryFetcher:
    """
    Handles fetching the creation date of an image directly from the Docker Registry / OCI Registry.
    """

    @staticmethod
    def parse_image_name(image_name):
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
            repo, tag = repo.split(":", 1)

        return registry, repo, tag

    @staticmethod
    def get_auth_token(registry, repository):
        """
        Retrieves a Bearer token for the given registry and repository by triggering a 401 challenge.
        """
        try:
            url = f"https://{registry}/v2/"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 401 and "Www-Authenticate" in resp.headers:
                auth_header = resp.headers["Www-Authenticate"]

                # e.g. Bearer realm="https://auth.docker.io/token",service="registry.docker.io"
                match_realm = re.search(r'realm="([^"]+)"', auth_header)
                match_service = re.search(r'service="([^"]+)"', auth_header)

                if not match_realm:
                    return None

                realm = match_realm.group(1)
                service = match_service.group(1) if match_service else registry

                # Request token
                token_params = {
                    "service": service,
                    "scope": f"repository:{repository}:pull",
                }

                token_resp = requests.get(realm, params=token_params, timeout=10)
                if token_resp.status_code == 200:
                    return token_resp.json().get("token") or token_resp.json().get(
                        "access_token"
                    )
            elif resp.status_code == 200:
                # No auth required
                return None
        except Exception as e:
            logger.error(f"Error authenticating with registry {registry}: {e}")
        return None

    @staticmethod
    def fetch_manifest(registry, repository, reference, token):
        """
        Fetches the manifest. Handles multi-arch lists by picking linux/amd64.
        """
        headers = {
            "Accept": "application/vnd.docker.distribution.manifest.v2+json, "
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.oci.image.index.v1+json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"https://{registry}/v2/{repository}/manifests/{reference}"
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code != 200:
            logger.error(
                f"Failed to fetch manifest for {repository}:{reference} - Status: {resp.status_code}"
            )
            return None

        manifest = resp.json()
        media_type = manifest.get("mediaType", "")

        # If it's a manifest list/index, find the linux/amd64 manifest and fetch it
        if "manifest.list" in media_type or "image.index" in media_type:
            manifests = manifest.get("manifests", [])
            for m in manifests:
                platform = m.get("platform", {})
                if (
                    platform.get("architecture") in ["amd64", "arm64"]
                    and platform.get("os") == "linux"
                ):
                    # Priority to the first matching linux architecture (can be enhanced to match host arch)
                    return RegistryFetcher.fetch_manifest(
                        registry, repository, m.get("digest"), token
                    )

            # Fallback to first if linux not found
            if manifests:
                return RegistryFetcher.fetch_manifest(
                    registry, repository, manifests[0].get("digest"), token
                )

        return manifest

    @staticmethod
    def get_remote_image_info(image_name):
        """
        Full flow: parse image -> auth -> manifest -> config blob.
        Returns a dict with 'created', 'version', and 'source', or None if it fails.
        """
        registry, repository, tag = RegistryFetcher.parse_image_name(image_name)

        try:
            token = RegistryFetcher.get_auth_token(registry, repository)
            manifest = RegistryFetcher.fetch_manifest(registry, repository, tag, token)

            if not manifest or "config" not in manifest:
                return None

            config_digest = manifest["config"].get("digest")
            if not config_digest:
                return None

            # Fetch config blob
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # Some registries require custom accept for blobs, but usually standard gets work
            blob_url = f"https://{registry}/v2/{repository}/blobs/{config_digest}"
            blob_resp = requests.get(blob_url, headers=headers, timeout=10)

            if blob_resp.status_code == 200:
                config_json = blob_resp.json()
                created = config_json.get("created")

                labels = config_json.get("config", {}).get("Labels") or {}
                version = labels.get("org.opencontainers.image.version") or labels.get(
                    "version"
                )
                source = (
                    labels.get("org.opencontainers.image.source")
                    or labels.get("org.opencontainers.image.url")
                    or labels.get("org.label-schema.vcs-url")
                )

                return {"created": created, "version": version, "source": source}

        except Exception as e:
            logger.error(f"Failed to get remote info for {image_name}: {e}")

        return None
