import logging
from typing import Any, Dict, List, Optional, Tuple

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

logger = logging.getLogger(__name__)


class DockerManager:
    def __init__(self) -> None:
        self.client = docker.from_env()

    def get_containers(self, include_stopped: bool = False) -> List[Container]:
        """Returns a list of containers."""
        return self.client.containers.list(all=include_stopped)

    def check_for_updates(
        self, container: Container
    ) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        Checks if a newer image exists for the given container on the registry.
        Returns the new image tag/digest if an update is available, else None.
        """
        labels = container.attrs.get("Config", {}).get("Labels", {}) or {}
        if (
            str(labels.get("telegramtower.enable", "")).lower() == "false"
            or str(labels.get("com.centurylinklabs.watchtower.enable", "")).lower()
            == "false"
        ):
            logger.info(f"Skipping container {container.name} due to disable label.")
            return None, None, None

        image = container.image
        # Get the actual image name used to start the container
        image_name = container.attrs["Config"]["Image"]
        if not image_name or ":" not in image_name:
            # If it's a raw hash or lacks a tag, we can't reliably check the registry by tag
            if ":" not in image_name:
                image_name += ":latest"
        try:
            registry_data = self.client.images.get_registry_data(image_name)
            remote_digest = registry_data.id

            # Docker python client sometimes doesn't have the digest locally if not pulled by digest
            # A simple approach: pull the image and see if the ID changes
            # But we don't want to pull everything blindly.
            # However, comparing digest is tricky if the local image lacks RepoDigests.
            # Let's just return True for now to simulate an update if the digest doesn't match
            # For a more robust approach, we need to inspect RepoDigests.

            if image and image.attrs.get("RepoDigests"):
                local_digest = image.attrs["RepoDigests"][0]
                # local_digest is like "ubuntu@sha256:..."
                if remote_digest not in local_digest:
                    # Digest changed! Now fetch the actual creation date and info from the registry
                    from registry_api import RegistryFetcher

                    remote_info = RegistryFetcher.get_remote_image_info(image_name)
                    return image_name, remote_digest, remote_info
            return None, None, None
        except APIError as e:
            if e.response is not None and e.response.status_code == 403:
                # Likely a local image or private registry without auth
                logger.debug(
                    f"Skipping {container.name} ({image_name}): Access forbidden (local or private image)."
                )
            else:
                logger.error(f"API Error checking updates for {container.name}: {e}")
            return None, None, None
        except DockerException as e:
            logger.error(f"Docker Exception checking updates for {container.name}: {e}")
            return None, None, None

    def update_container(
        self, container_id: str, cleanup_old_image: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Pulls the new image, stops the container, recreates it, and optionally cleans up the old image.
        Returns a tuple (success: bool, message_key: str, params: dict)
        """
        try:
            container = self.client.containers.get(container_id)
            image_name = container.attrs["Config"]["Image"]
            if not image_name or ":" not in image_name:
                if ":" not in image_name:
                    image_name += ":latest"

            old_image_id = container.image.id if container.image else None
            is_running = container.status == "running"

            logger.info(f"Pulling latest image for {image_name}")
            new_image = self.client.images.pull(image_name)

            if new_image and old_image_id == new_image.id:
                return True, "already_up_to_date", {"name": container.name}

            container_config = container.attrs["Config"]
            host_config = container.attrs["HostConfig"]

            name = container.name

            if is_running:
                logger.info(f"Stopping container {name}")
                container.stop()

            logger.info(f"Removing container {name}")
            container.remove()

            logger.info(f"Recreating container {name}")

            try:
                # Basic recreation logic mapping core attributes
                # Copying labels is critical so Docker Compose doesn't lose track of the container
                labels = container_config.get("Labels", {})

                # Handle networks
                networks = container.attrs["NetworkSettings"].get("Networks", {})
                primary_network = (
                    next(iter(networks.keys()))
                    if networks
                    else host_config.get("NetworkMode")
                )

                kwargs = {
                    "image": image_name,
                    "name": name,
                    "command": container_config.get("Cmd"),
                    "environment": container_config.get("Env"),
                    "volumes": host_config.get("Binds"),
                    "ports": host_config.get("PortBindings"),
                    "network": primary_network,
                    "restart_policy": host_config.get("RestartPolicy"),
                    "labels": labels,
                }

                if is_running:
                    new_container = self.client.containers.run(detach=True, **kwargs)
                    logger.info(
                        f"Container {name} recreated and started successfully with id {new_container.id}"
                    )
                else:
                    new_container = self.client.containers.create(**kwargs)
                    logger.info(
                        f"Container {name} recreated (left stopped) successfully with id {new_container.id}"
                    )

                # Connect to additional networks if the container was in multiple
                if networks and len(networks) > 1:
                    for net_name in list(networks.keys())[1:]:
                        try:
                            net = self.client.networks.get(net_name)
                            net.connect(new_container)
                        except APIError as net_e:
                            logger.error(
                                f"Failed to connect to additional network {net_name}: {net_e}"
                            )

            except APIError as create_e:
                logger.error(f"Failed to recreate container {name}: {create_e}")
                return False, "err_recreate", {"error": str(create_e)}

            # Cleanup old image
            cleaned_up = False
            if cleanup_old_image:
                try:
                    self.client.images.remove(str(old_image_id))
                    logger.info(f"Removed old image {old_image_id}")
                    cleaned_up = True
                except APIError as clean_e:
                    logger.warning(
                        f"Failed to remove old image {old_image_id}: {clean_e}"
                    )

            return (
                True,
                "update_success",
                {"name": name, "was_running": is_running, "cleaned_up": cleaned_up},
            )

        except NotFound as e:
            logger.error(f"Container {container_id} not found: {e}")
            return False, "not_found_msg", {"container": container_id}
        except DockerException as e:
            logger.error(f"Error updating container {container_id}: {e}")
            return False, "generic_error", {"error": str(e)}
