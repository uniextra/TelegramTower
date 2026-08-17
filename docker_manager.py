import docker
import logging

logger = logging.getLogger(__name__)

class DockerManager:
    def __init__(self):
        self.client = docker.from_env()

    def get_containers(self, include_stopped=False):
        """Returns a list of containers."""
        return self.client.containers.list(all=include_stopped)

    def check_for_updates(self, container):
        """
        Checks if a newer image exists for the given container on the registry.
        Returns the new image tag/digest if an update is available, else None.
        """
        labels = container.attrs.get('Config', {}).get('Labels', {}) or {}
        if str(labels.get('telegramtower.enable', '')).lower() == 'false' or \
           str(labels.get('com.centurylinklabs.watchtower.enable', '')).lower() == 'false':
            logger.info(f"Skipping container {container.name} due to disable label.")
            return None

        image = container.image
        # Get the actual image name used to start the container
        image_name = container.attrs['Config']['Image']
        if not image_name or ':' not in image_name:
            # If it's a raw hash or lacks a tag, we can't reliably check the registry by tag
            if ':' not in image_name:
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
            
            if image.attrs.get("RepoDigests"):
                local_digest = image.attrs["RepoDigests"][0]
                # local_digest is like "ubuntu@sha256:..."
                if remote_digest not in local_digest:
                    return image_name
            return None
        except docker.errors.APIError as e:
            if e.response.status_code == 403:
                # Likely a local image or private registry without auth
                logger.debug(f"Skipping {container.name} ({image_name}): Access forbidden (local or private image).")
            else:
                logger.error(f"API Error checking updates for {container.name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error checking updates for {container.name}: {e}")
            return None

    def update_container(self, container_id, cleanup_old_image=False):
        """
        Pulls the new image, stops the container, recreates it, and optionally cleans up the old image.
        Returns a tuple (success: bool, message: str)
        """
        try:
            container = self.client.containers.get(container_id)
            image_name = container.attrs['Config']['Image']
            if not image_name or ':' not in image_name:
                if ':' not in image_name:
                    image_name += ":latest"
                
            old_image_id = container.image.id
            is_running = container.status == 'running'
            
            logger.info(f"Pulling latest image for {image_name}")
            new_image = self.client.images.pull(image_name)
            
            if old_image_id == new_image.id:
                return True, f"Container {container.name} is already up to date."

            container_config = container.attrs['Config']
            host_config = container.attrs['HostConfig']
            
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
                labels = container_config.get('Labels', {})
                
                # Handle networks
                networks = container.attrs['NetworkSettings'].get('Networks', {})
                primary_network = list(networks.keys())[0] if networks else host_config.get('NetworkMode')
                
                kwargs = dict(
                    image=image_name,
                    name=name,
                    command=container_config.get('Cmd'),
                    environment=container_config.get('Env'),
                    volumes=host_config.get('Binds'),
                    ports=host_config.get('PortBindings'),
                    network=primary_network,
                    restart_policy=host_config.get('RestartPolicy'),
                    labels=labels
                )
                
                if is_running:
                    new_container = self.client.containers.run(detach=True, **kwargs)
                    logger.info(f"Container {name} recreated and started successfully with id {new_container.id}")
                else:
                    new_container = self.client.containers.create(**kwargs)
                    logger.info(f"Container {name} recreated (left stopped) successfully with id {new_container.id}")
                
                # Connect to additional networks if the container was in multiple
                if networks and len(networks) > 1:
                    for net_name in list(networks.keys())[1:]:
                        try:
                            net = self.client.networks.get(net_name)
                            net.connect(new_container)
                        except Exception as net_e:
                            logger.error(f"Failed to connect to additional network {net_name}: {net_e}")

                state_msg = "and started" if is_running else "and left stopped"
                success_msg = f"Updated {name} {state_msg} successfully."
            except Exception as create_e:
                logger.error(f"Failed to recreate container {name}: {create_e}")
                return False, f"Failed to recreate container: {create_e}"
            
            # Cleanup old image
            if cleanup_old_image:
                try:
                    # Let's check if the container is running and healthy first
                    # For simplicity, assuming it started correctly
                    self.client.images.remove(old_image_id)
                    logger.info(f"Removed old image {old_image_id}")
                    success_msg += " Old image removed."
                except Exception as clean_e:
                    logger.warning(f"Failed to remove old image {old_image_id}: {clean_e}")
                    
            return True, success_msg
            
        except Exception as e:
            logger.error(f"Error updating container {container_id}: {e}")
            return False, f"Error: {e}"
