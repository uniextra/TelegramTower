import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

logger = logging.getLogger(__name__)


class DockerManager:
    def __init__(self) -> None:
        self.client = docker.from_env()
        self._lock = threading.Lock()

    def get_containers(self, include_stopped: bool = False) -> List[Container]:
        """Returns a list of containers."""
        return self.client.containers.list(all=include_stopped)

    def _is_self_or_infra_container(self, container: Container) -> Tuple[bool, str]:
        """Checks if container is TelegramTower itself or Docker socket proxy to prevent self-destruction."""
        name = container.name.lower()
        image_name = (container.attrs.get("Config", {}).get("Image") or "").lower()
        hostname = os.environ.get("HOSTNAME", "").lower()

        # Match own hostname / container ID if running in Docker
        if hostname and (container.id.lower().startswith(hostname) or name == hostname):
            return True, "self_update_blocked"

        if name in ("telegramtower", "telegram-tower") or "telegramtower" in image_name:
            return True, "self_update_blocked"

        # Match docker socket proxy
        if "socket-proxy" in name or "docker-socket-proxy" in image_name:
            return True, "socket_proxy_blocked"

        return False, ""

    def check_for_updates(
        self, container: Container
    ) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]], bool]:
        """
        Checks if a newer image exists for the given container on the registry.
        Returns the new image tag/digest if an update is available, else None.
        Also returns whether the OCI version/revision labels are unchanged (rebuild).
        """
        labels = container.attrs.get("Config", {}).get("Labels", {}) or {}
        if (
            str(labels.get("telegramtower.enable", "")).lower() == "false"
            or str(labels.get("com.centurylinklabs.watchtower.enable", "")).lower()
            == "false"
        ):
            logger.info(f"Skipping container {container.name} due to disable label.")
            return None, None, None, False

        image = container.image
        image_name = container.attrs.get("Config", {}).get("Image", "")
        if not image_name or ":" not in image_name:
            if ":" not in image_name:
                image_name += ":latest"
        try:
            registry_data = self.client.images.get_registry_data(image_name)
            remote_digest = registry_data.id

            if image and image.attrs.get("RepoDigests"):
                local_digests = image.attrs["RepoDigests"]
                if not any(remote_digest in ld for ld in local_digests):
                    from registry_api import RegistryFetcher

                    remote_info = RegistryFetcher.get_remote_image_info(image_name)

                    is_same_version = False
                    if remote_info:
                        remote_labels = (
                            remote_info.get("labels")
                            or remote_info.get("config", {}).get("Labels", {})
                            or {}
                        )
                        local_labels = image.attrs.get("Config", {}).get("Labels", {}) or {}

                        # 1. Check opencontainers version label
                        if (
                            "org.opencontainers.image.version" in local_labels
                            and "org.opencontainers.image.version" in remote_labels
                        ):
                            if (
                                local_labels["org.opencontainers.image.version"]
                                == remote_labels["org.opencontainers.image.version"]
                            ):
                                is_same_version = True
                        # 2. Check opencontainers revision (git commit hash)
                        elif (
                            "org.opencontainers.image.revision" in local_labels
                            and "org.opencontainers.image.revision" in remote_labels
                        ):
                            if (
                                local_labels["org.opencontainers.image.revision"]
                                == remote_labels["org.opencontainers.image.revision"]
                            ):
                                is_same_version = True
                        # 3. Check linuxserver specific build version
                        elif "build_version" in local_labels and "build_version" in remote_labels:
                            if local_labels["build_version"] == remote_labels["build_version"]:
                                is_same_version = True

                    return image_name, remote_digest, remote_info, is_same_version
            return None, None, None, False
        except APIError as e:
            if e.response is not None and e.response.status_code == 403:
                logger.debug(
                    f"Skipping {container.name} ({image_name}): Access forbidden (local or private image)."
                )
            else:
                logger.error(f"API Error checking updates for {container.name}: {e}")
            return None, None, None, False
        except DockerException as e:
            logger.error(f"Docker Exception checking updates for {container.name}: {e}")
            return None, None, None, False
        except Exception as e:
            logger.error(f"Unexpected error checking updates for {container.name}: {e}")
            return None, None, None, False

    def _get_network_dependents(self, parent_container: Container) -> list:
        """Finds containers using the parent's network namespace."""
        dependents = []
        try:
            target_id_mode = f"container:{parent_container.id}"
            target_name_mode = f"container:{parent_container.name}"
            for c in self.client.containers.list(all=True):
                if c.id == parent_container.id:
                    continue
                net_mode = c.attrs.get("HostConfig", {}).get("NetworkMode", "")
                if net_mode == target_id_mode or net_mode == target_name_mode:
                    dependents.append(c)
        except Exception as e:
            logger.error(f"Error finding dependents for {parent_container.name}: {e}")
        return dependents

    def _recreate_single_container(
        self,
        container: Container,
        image_name: Optional[str] = None,
        network_mode_override: Optional[str] = None,
    ) -> Container:
        """Recreates a single container, handling backup, renaming, copying complete attributes, and verifying health."""
        if image_name is None:
            image_name = container.attrs["Config"]["Image"]
            if not image_name or ":" not in image_name:
                image_name += ":latest"

        name = container.name
        is_running = container.status == "running"
        container_config = container.attrs.get("Config", {})
        host_config = container.attrs.get("HostConfig", {})

        if is_running:
            logger.info(f"Stopping container {name}")
            container.stop()

        backup_name = f"{name}_tt_backup"
        try:
            try:
                old_backup = self.client.containers.get(backup_name)
                old_backup.remove(force=True)
            except docker.errors.NotFound:
                pass
            container.rename(backup_name)
        except Exception as rename_e:
            logger.warning(f"Could not rename {name} to {backup_name}: {rename_e}")

        logger.info(f"Recreating container {name}")
        new_container = None
        try:
            labels = container_config.get("Labels", {})
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})

            primary_network = network_mode_override
            if not primary_network:
                primary_network = (
                    next(iter(networks.keys())) if networks else host_config.get("NetworkMode")
                )

            kwargs: Dict[str, Any] = {
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

            # Preserve complete security and runtime attributes
            optional_attrs = [
                ("entrypoint", container_config.get("Entrypoint")),
                ("working_dir", container_config.get("WorkingDir")),
                ("user", container_config.get("User")),
                ("healthcheck", container_config.get("Healthcheck")),
                ("privileged", host_config.get("Privileged")),
                ("cap_add", host_config.get("CapAdd")),
                ("cap_drop", host_config.get("CapDrop")),
                ("security_opt", host_config.get("SecurityOpt")),
                ("read_only", host_config.get("ReadonlyRootfs")),
                ("tmpfs", host_config.get("Tmpfs")),
                ("ulimits", host_config.get("Ulimits")),
                ("sysctls", host_config.get("Sysctls")),
                ("devices", host_config.get("Devices")),
                ("dns", host_config.get("Dns")),
                ("extra_hosts", host_config.get("ExtraHosts")),
                ("shm_size", host_config.get("ShmSize")),
                ("mem_limit", host_config.get("Memory")),
                ("cpu_shares", host_config.get("CpuShares")),
                ("cpu_quota", host_config.get("CpuQuota")),
                ("cpu_period", host_config.get("CpuPeriod")),
                ("cpuset_cpus", host_config.get("CpusetCpus")),
                ("ipc_mode", host_config.get("IpcMode")),
                ("pid_mode", host_config.get("PidMode")),
                ("log_config", host_config.get("LogConfig")),
            ]
            for key, val in optional_attrs:
                if val is not None:
                    kwargs[key] = val

            # Preserve named volumes
            mounts = []
            for m in container.attrs.get("Mounts", []):
                if m.get("Type") == "volume" and m.get("Name"):
                    try:
                        import docker.types

                        mounts.append(
                            docker.types.Mount(
                                target=m["Destination"],
                                source=m["Name"],
                                type="volume",
                                read_only=not m.get("RW", True),
                            )
                        )
                    except Exception:
                        pass
            if mounts:
                kwargs["mounts"] = mounts

            if is_running:
                new_container = self.client.containers.run(detach=True, **kwargs)
                logger.info(
                    f"Container {name} recreated and started successfully with id {new_container.id}"
                )
                # Verify container didn't immediately crash
                time.sleep(1)
                try:
                    new_container.reload()
                    if getattr(new_container, "status", "") in ("exited", "dead"):
                        raise RuntimeError(
                            f"Container {name} exited immediately after startup (status: {new_container.status})"
                        )
                except Exception as check_e:
                    logger.error(f"Health validation failed for new container {name}: {check_e}")
                    raise check_e
            else:
                new_container = self.client.containers.create(**kwargs)
                logger.info(
                    f"Container {name} recreated (left stopped) successfully with id {new_container.id}"
                )

            # Reconnect additional networks
            if networks and len(networks) > 1 and not network_mode_override:
                for net_name in list(networks.keys())[1:]:
                    try:
                        net = self.client.networks.get(net_name)
                        net.connect(new_container)
                    except docker.errors.APIError as net_e:
                        logger.error(
                            f"Failed to connect to additional network {net_name}: {net_e}"
                        )

            # Cleanup backup container
            try:
                container.remove(force=True)
            except Exception as rm_e:
                logger.warning(f"Failed to remove backup container {backup_name}: {rm_e}")

            return new_container

        except Exception as create_e:
            logger.error(f"Failed to recreate container {name}: {create_e}")
            if new_container:
                try:
                    new_container.remove(force=True)
                except Exception:
                    pass
            try:
                container.rename(name)
                if is_running:
                    container.start()
                logger.info(f"Rollback successful: restored container {name}")
            except Exception as rb_e:
                logger.error(f"Rollback failed for container {name}: {rb_e}")
            raise create_e

    def update_container(
        self, container_id: str, cleanup_old_image: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Pulls the new image, stops the container, recreates it, and optionally cleans up the old image.
        Returns a tuple (success: bool, message_key: str, params: dict)
        """
        with self._lock:
            try:
                container = self.client.containers.get(container_id)
                name = container.name

                # Prevent self-update or socket-proxy update
                blocked, reason = self._is_self_or_infra_container(container)
                if blocked:
                    logger.warning(
                        f"Prevented update of protected infrastructure container {name}: {reason}"
                    )
                    return False, reason, {"name": name}

                image_name = container.attrs.get("Config", {}).get("Image", "")
                if not image_name or ":" not in image_name:
                    if ":" not in image_name:
                        image_name += ":latest"

                old_image_id = container.image.id if container.image else None
                is_running = container.status == "running"

                logger.info(f"Pulling latest image for {image_name}")
                new_image = self.client.images.pull(image_name)

                if new_image and old_image_id == new_image.id:
                    return True, "already_up_to_date", {"name": container.name}

                # 1. Find network dependents BEFORE stopping parent
                dependents = self._get_network_dependents(container)
                if dependents:
                    logger.info(f"Found {len(dependents)} dependent container(s) for {name}")

                # 2. Stop dependents first
                for dep in dependents:
                    if dep.status == "running":
                        logger.info(f"Stopping dependent container {dep.name}")
                        dep.stop()

                # 3. Recreate main container
                try:
                    new_parent = self._recreate_single_container(container, image_name)
                except Exception as create_e:
                    return False, "err_recreate", {"error": str(create_e)}

                # 4. Recreate dependents
                recreated_dependents = []
                for dep in dependents:
                    logger.info(f"Recreating dependent container {dep.name}")
                    new_net_mode = f"container:{new_parent.name}"
                    try:
                        self._recreate_single_container(dep, network_mode_override=new_net_mode)
                        recreated_dependents.append(dep.name)
                    except Exception as dep_e:
                        logger.error(f"Failed to recreate dependent container {dep.name}: {dep_e}")

                # Cleanup old image
                cleaned_up = False
                if cleanup_old_image and old_image_id:
                    try:
                        self.client.images.remove(image=str(old_image_id), force=True, noprune=False)
                        logger.info(f"Removed old image {old_image_id}")
                        cleaned_up = True
                    except docker.errors.APIError as clean_e:
                        if clean_e.response is not None and clean_e.response.status_code == 409:
                            logger.info(
                                f"Skipped removing old image {old_image_id} as it is in use by another container."
                            )
                        else:
                            logger.warning(f"Failed to remove old image {old_image_id}: {clean_e}")

                attrs = getattr(new_image, "attrs", None)
                new_labels = {}
                if isinstance(attrs, dict):
                    config = attrs.get("Config")
                    if isinstance(config, dict):
                        new_labels = config.get("Labels") or {}
                elif isinstance(getattr(new_image, "labels", None), dict):
                    new_labels = new_image.labels

                from registry_api import RegistryFetcher

                version = RegistryFetcher.extract_version_from_labels(new_labels)
                source = RegistryFetcher.extract_source_from_labels(new_labels)

                return (
                    True,
                    "update_success",
                    {
                        "name": name,
                        "was_running": is_running,
                        "cleaned_up": cleaned_up,
                        "dependents": recreated_dependents,
                        "version": version,
                        "source": source,
                    },
                )

            except docker.errors.NotFound as e:
                logger.error(f"Container {container_id} not found: {e}")
                return False, "not_found_msg", {"container": container_id}
            except docker.errors.DockerException as e:
                logger.error(f"Error updating container {container_id}: {e}")
                return False, "generic_error", {"error": str(e)}
