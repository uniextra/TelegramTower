from unittest.mock import MagicMock, patch
from registry_api import RegistryFetcher, is_allowed_realm, DIGEST_REGEX


def test_extract_version_from_oci_label():
    labels = {"org.opencontainers.image.version": "v2.1.0"}
    assert RegistryFetcher.extract_version_from_labels(labels) == "v2.1.0"


def test_extract_version_from_linuxserver_build_version():
    labels = {
        "build_version": "Linuxserver.io version:- v1.6.2-ls368 Build-date:- 2026-08-19T04:32:10+00:00"
    }
    assert RegistryFetcher.extract_version_from_labels(labels) == "v1.6.2-ls368"


def test_extract_version_from_label_schema():
    labels = {"org.label-schema.version": "1.0.3"}
    assert RegistryFetcher.extract_version_from_labels(labels) == "1.0.3"


def test_extract_version_none_or_empty():
    assert RegistryFetcher.extract_version_from_labels(None) is None
    assert RegistryFetcher.extract_version_from_labels({}) is None
    assert RegistryFetcher.extract_version_from_labels({"other": "value"}) is None


def test_extract_source_from_labels():
    labels = {"org.opencontainers.image.source": "https://github.com/linuxserver/docker-bazarr"}
    assert RegistryFetcher.extract_source_from_labels(labels) == "https://github.com/linuxserver/docker-bazarr"

    labels_vcs = {"org.label-schema.vcs-url": "https://github.com/example/repo"}
    assert RegistryFetcher.extract_source_from_labels(labels_vcs) == "https://github.com/example/repo"

    assert RegistryFetcher.extract_source_from_labels(None) is None
    assert RegistryFetcher.extract_source_from_labels({}) is None


def test_extract_version_build_version_missing_token():
    labels = {
        "build_version": "Linuxserver.io version:- Build-date:- 2026-08-19"
    }
    assert RegistryFetcher.extract_version_from_labels(labels) is None


def test_extract_version_whitespace_only():
    assert RegistryFetcher.extract_version_from_labels({"build_version": "   "}) is None
    assert RegistryFetcher.extract_version_from_labels({"version": "   "}) is None


def test_extract_source_url_normalization():
    labels_git = {"org.opencontainers.image.source": "git@github.com:linuxserver/docker-bazarr.git"}
    assert RegistryFetcher.extract_source_from_labels(labels_git) == "https://github.com/linuxserver/docker-bazarr"

    labels_git_proto = {"org.opencontainers.image.source": "git://github.com/linuxserver/docker-bazarr.git"}
    assert RegistryFetcher.extract_source_from_labels(labels_git_proto) == "https://github.com/linuxserver/docker-bazarr"

    labels_bare = {"org.opencontainers.image.source": "github.com/linuxserver/docker-bazarr"}
    assert RegistryFetcher.extract_source_from_labels(labels_bare) == "https://github.com/linuxserver/docker-bazarr"

    labels_invalid = {"org.opencontainers.image.source": "custom://some-path"}
    assert RegistryFetcher.extract_source_from_labels(labels_invalid) is None


def test_ssrf_realm_validation():
    # Blocks HTTP and private / metadata ranges
    assert is_allowed_realm("http://169.254.169.254/token", "registry-1.docker.io") is False
    assert is_allowed_realm("http://127.0.0.1:8080/token", "registry-1.docker.io") is False
    assert is_allowed_realm("https://10.0.0.1/token", "registry-1.docker.io") is False
    assert is_allowed_realm("https://evil-hacker.com/token", "registry-1.docker.io") is False

    # Allows legitimate registry auth endpoints
    assert is_allowed_realm("https://auth.docker.io/token", "registry-1.docker.io") is True
    assert is_allowed_realm("https://ghcr.io/token", "ghcr.io") is True


def test_get_auth_token_blocks_malicious_realm():
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401
    mock_resp_401.headers = {
        "Www-Authenticate": 'Bearer realm="http://169.254.169.254/latest/meta-data",service="registry.docker.io"'
    }

    with patch("requests.Session.get", return_value=mock_resp_401) as mock_get:
        token = RegistryFetcher.get_auth_token("registry-1.docker.io", "library/ubuntu")
        assert token is None
        # Should not make a second request to the malicious realm
        assert mock_get.call_count == 1


def test_digest_regex_validation():
    valid = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    assert DIGEST_REGEX.match(valid) is not None

    invalid_chars = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcXYZ"
    assert DIGEST_REGEX.match(invalid_chars) is None

    traversal = "sha256:../../../etc/passwd"
    assert DIGEST_REGEX.match(traversal) is None
