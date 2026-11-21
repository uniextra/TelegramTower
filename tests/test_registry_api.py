from unittest.mock import MagicMock, patch
import requests
from registry_api import RegistryFetcher, is_allowed_realm, is_safe_registry_host, _safe_get, DIGEST_REGEX


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


def test_is_safe_registry_host():
    assert is_safe_registry_host("127.0.0.1:5000") is False
    assert is_safe_registry_host("localhost:5000") is False
    assert is_safe_registry_host("169.254.169.254") is False
    assert is_safe_registry_host("10.0.0.5") is False
    assert is_safe_registry_host("registry-1.docker.io") is True
    assert is_safe_registry_host("ghcr.io") is True


def test_get_auth_token_blocks_unsafe_registry_host():
    with patch("requests.Session.get") as mock_get:
        assert RegistryFetcher.get_auth_token("127.0.0.1:5000", "app") is None
        assert RegistryFetcher.get_auth_token("169.254.169.254", "app") is None
        assert RegistryFetcher.get_auth_token("localhost:5000", "app") is None
        mock_get.assert_not_called()


def test_safe_get_blocks_unsafe_redirects():
    mock_redirect_http = MagicMock()
    mock_redirect_http.status_code = 302
    mock_redirect_http.headers = {"Location": "http://169.254.169.254/latest/meta-data"}

    session = requests.Session()
    with patch.object(session, "get", return_value=mock_redirect_http) as mock_get:
        resp = _safe_get(session, "https://registry-1.docker.io/v2/test/blobs/sha256:abc")
        assert resp is None
        assert mock_get.call_count == 1
        assert mock_get.call_args[1]["allow_redirects"] is False

    mock_redirect_private_ip = MagicMock()
    mock_redirect_private_ip.status_code = 307
    mock_redirect_private_ip.headers = {"Location": "https://10.0.0.1/blob"}

    with patch.object(session, "get", return_value=mock_redirect_private_ip) as mock_get:
        resp = _safe_get(session, "https://registry-1.docker.io/v2/test/blobs/sha256:abc")
        assert resp is None
        assert mock_get.call_count == 1


def test_safe_get_strips_auth_on_cross_host_redirect():
    mock_redirect = MagicMock()
    mock_redirect.status_code = 307
    mock_redirect.headers = {"Location": "https://auth.docker.io/cdn/blob"}

    mock_ok = MagicMock()
    mock_ok.status_code = 200

    session = requests.Session()
    with patch.object(session, "get", side_effect=[mock_redirect, mock_ok]) as mock_get:
        resp = _safe_get(
            session,
            "https://registry-1.docker.io/v2/test/blobs/sha256:abc",
            headers={"Authorization": "Bearer secret-token", "Accept": "application/json"},
        )
        assert resp is mock_ok
        assert mock_get.call_count == 2
        second_headers = mock_get.call_args_list[1][1]["headers"]
        assert "Authorization" not in second_headers
        assert second_headers["Accept"] == "application/json"
