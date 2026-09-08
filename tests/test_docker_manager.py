from unittest.mock import MagicMock

import pytest

from docker_manager import DockerManager


@pytest.fixture
def mock_docker_client(mocker):
    mock_client = MagicMock()
    mocker.patch("docker.from_env", return_value=mock_client)
    return mock_client


def test_get_containers(mock_docker_client):
    manager = DockerManager()
    manager.client.containers.list.return_value = ["container1", "container2"]

    containers = manager.get_containers()
    assert len(containers) == 2
    manager.client.containers.list.assert_called_once()


def test_check_for_updates_no_tags(mock_docker_client):
    manager = DockerManager()
    mock_container = MagicMock()
    mock_container.attrs = {"Config": {"Image": ""}}
    mock_container.image.tags = []
    mock_container.image.attrs = {}

    assert manager.check_for_updates(mock_container) == (None, None, None, False)


def test_check_for_updates_update_available(mock_docker_client, mocker):
    manager = DockerManager()

    mock_container = MagicMock()
    mock_container.attrs = {"Config": {"Image": "myimage:latest"}}
    mock_container.image.tags = ["myimage:latest"]
    mock_container.image.attrs = {"RepoDigests": ["myimage@sha256:oldhash"]}

    mock_registry_data = MagicMock()
    mock_registry_data.id = "sha256:newhash"
    manager.client.images.get_registry_data.return_value = mock_registry_data

    # Mock registry API to avoid network calls during test
    mocker.patch(
        "registry_api.RegistryFetcher.get_remote_image_info",
        return_value={
            "created": "2026-08-19T04:32:10Z",
            "version": "1.4",
            "source": "https://github.com/a",
        },
    )

    result = manager.check_for_updates(mock_container)
    assert result == (
        "myimage:latest",
        "sha256:newhash",
        {
            "created": "2026-08-19T04:32:10Z",
            "version": "1.4",
            "source": "https://github.com/a",
        },
        False,
    )


def test_check_for_updates_no_update(mock_docker_client):
    manager = DockerManager()

    mock_container = MagicMock()
    mock_container.attrs = {"Config": {"Image": "myimage:latest"}}
    mock_container.image.tags = ["myimage:latest"]
    mock_container.image.attrs = {"RepoDigests": ["myimage@sha256:samehash"]}

    mock_registry_data = MagicMock()
    mock_registry_data.id = "sha256:samehash"
    manager.client.images.get_registry_data.return_value = mock_registry_data

    result = manager.check_for_updates(mock_container)
    assert result == (None, None, None, False)


def test_check_for_updates_same_version(mock_docker_client, mocker):
    manager = DockerManager()

    mock_container = MagicMock()
    mock_container.attrs = {
        "Config": {
            "Image": "myimage:latest",
            "Labels": {"org.opencontainers.image.version": "1.4.0"},
        }
    }
    mock_container.image.tags = ["myimage:latest"]
    mock_container.image.attrs = {
        "RepoDigests": ["myimage@sha256:oldhash"],
        "Config": {"Labels": {"org.opencontainers.image.version": "1.4.0"}},
    }

    mock_registry_data = MagicMock()
    mock_registry_data.id = "sha256:newhash"
    manager.client.images.get_registry_data.return_value = mock_registry_data

    mocker.patch(
        "registry_api.RegistryFetcher.get_remote_image_info",
        return_value={
            "created": "2026-08-19T04:32:10Z",
            "version": "1.4.0",
            "labels": {"org.opencontainers.image.version": "1.4.0"},
            "config": {"Labels": {"org.opencontainers.image.version": "1.4.0"}},
        },
    )

    image_name, remote_digest, remote_info, is_same_version = manager.check_for_updates(mock_container)
    assert is_same_version is True


def test_update_container_rollback_on_failure(mock_docker_client):
    manager = DockerManager()
    mock_container = MagicMock()
    mock_container.name = "my_app"
    mock_container.status = "running"
    mock_container.attrs = {
        "Config": {"Image": "my_app:latest", "Cmd": None, "Env": None, "Labels": {}},
        "HostConfig": {"Binds": None, "PortBindings": None, "NetworkMode": "bridge", "RestartPolicy": {}},
        "NetworkSettings": {"Networks": {}},
    }
    mock_container.image.id = "sha256:old"
    manager.client.containers.get.return_value = mock_container

    new_img = MagicMock()
    new_img.id = "sha256:new"
    manager.client.images.pull.return_value = new_img

    # Simulate run failing
    from docker.errors import APIError
    manager.client.containers.run.side_effect = APIError("Port conflict")

    success, msg_key, details = manager.update_container("c_id")

    assert success is False
    assert msg_key == "err_recreate"
    mock_container.rename.assert_any_call("my_app_tt_backup")
    mock_container.rename.assert_any_call("my_app")
    mock_container.start.assert_called_once()
