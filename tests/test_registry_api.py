import pytest
from registry_api import RegistryFetcher


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
    # If version is missing after version:- and points to Build-date
    labels = {
        "build_version": "Linuxserver.io version:- Build-date:- 2026-08-19"
    }
    assert RegistryFetcher.extract_version_from_labels(labels) is None


def test_extract_version_whitespace_only():
    assert RegistryFetcher.extract_version_from_labels({"build_version": "   "}) is None
    assert RegistryFetcher.extract_version_from_labels({"version": "   "}) is None


def test_extract_source_url_normalization():
    # git@ url
    labels_git = {"org.opencontainers.image.source": "git@github.com:linuxserver/docker-bazarr.git"}
    assert RegistryFetcher.extract_source_from_labels(labels_git) == "https://github.com/linuxserver/docker-bazarr"

    # git:// url
    labels_git_proto = {"org.opencontainers.image.source": "git://github.com/linuxserver/docker-bazarr.git"}
    assert RegistryFetcher.extract_source_from_labels(labels_git_proto) == "https://github.com/linuxserver/docker-bazarr"

    # bare domain
    labels_bare = {"org.opencontainers.image.source": "github.com/linuxserver/docker-bazarr"}
    assert RegistryFetcher.extract_source_from_labels(labels_bare) == "https://github.com/linuxserver/docker-bazarr"

    # non-http url should be ignored
    labels_invalid = {"org.opencontainers.image.source": "custom://some-path"}
    assert RegistryFetcher.extract_source_from_labels(labels_invalid) is None

