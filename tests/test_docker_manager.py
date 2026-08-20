import pytest
from unittest.mock import MagicMock
from docker_manager import DockerManager

@pytest.fixture
def mock_docker_client(mocker):
    mock_client = MagicMock()
    mocker.patch('docker.from_env', return_value=mock_client)
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
    
    assert manager.check_for_updates(mock_container) == (None, None, None)

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
    mocker.patch('registry_api.RegistryFetcher.get_remote_image_info', return_value={"created": "2026-08-19T04:32:10Z", "version": "1.4", "source": "https://github.com/a"})
    
    result = manager.check_for_updates(mock_container)
    assert result == ("myimage:latest", "sha256:newhash", {"created": "2026-08-19T04:32:10Z", "version": "1.4", "source": "https://github.com/a"})

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
    assert result == (None, None, None)
