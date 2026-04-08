import os
import time
from typing import Any, Dict, Optional

from migration_engine import MigrationEngine

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:  # pragma: no cover
    service_account = None
    build = None
    HttpError = Exception


class GcpMigrationEngine(MigrationEngine):
    def __init__(self, project_id: str, credentials_file: Optional[str] = None):
        if build is None or service_account is None:
            raise ImportError(
                "GCP migration support requires google-auth and google-api-python-client. "
                "Install via `pip install google-auth google-api-python-client`."
            )
        self.project_id = project_id
        self.credentials_file = credentials_file
        if credentials_file:
            self.credentials = service_account.Credentials.from_service_account_file(credentials_file)
        else:
            self.credentials = None
        self.compute = build("compute", "v1", credentials=self.credentials)

    def execute(
        self,
        vm_id: str,
        source_zone: str,
        target_zone: str,
        downtime_seconds: float,
        vm_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if vm_metadata is None:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": "Missing GCP VM metadata for migration.",
            }

        project_id = vm_metadata.get("gcp_project_id", self.project_id)
        instance_name = vm_metadata.get("gcp_instance_name")
        if not instance_name:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": "gcp_instance_name must be provided in VM metadata.",
            }

        source_zone = vm_metadata.get("gcp_source_zone", source_zone)
        target_zone = vm_metadata.get("gcp_target_zone", target_zone)
        target_instance_name = vm_metadata.get(
            "gcp_target_instance_name", f"{instance_name}-migrated-{int(time.time())}"
        )

        try:
            source_instance = self.compute.instances().get(
                project=project_id,
                zone=source_zone,
                instance=instance_name,
            ).execute()
        except HttpError as exc:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": f"Failed to fetch source instance metadata: {exc}",
            }

        boot_disk = None
        for disk in source_instance.get("disks", []):
            if disk.get("boot"):
                boot_disk = disk["source"].split("/")[-1]
                break

        if not boot_disk:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": "Unable to determine boot disk for source instance.",
            }

        snapshot_name = f"{instance_name}-migration-snap-{int(time.time())}"
        try:
            # Create a live snapshot while the source VM remains running.
            snapshot_body = {"name": snapshot_name, "guestFlush": True}
            snapshot_operation = self.compute.disks().createSnapshot(
                project=project_id,
                zone=source_zone,
                disk=boot_disk,
                body=snapshot_body,
            ).execute()
            self._wait_for_zone_operation(project_id, source_zone, snapshot_operation["name"])
        except HttpError as exc:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": f"Failed to create snapshot: {exc}",
            }

        target_disk_name = vm_metadata.get(
            "gcp_target_disk_name", f"{instance_name}-disk-{int(time.time())}"
        )
        try:
            disk_body = {
                "name": target_disk_name,
                "sourceSnapshot": f"projects/{project_id}/global/snapshots/{snapshot_name}",
            }
            disk_operation = self.compute.disks().insert(
                project=project_id,
                zone=target_zone,
                body=disk_body,
            ).execute()
            self._wait_for_zone_operation(project_id, target_zone, disk_operation["name"])
        except HttpError as exc:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": f"Failed to create target disk from snapshot: {exc}",
            }

        machine_type = source_instance.get("machineType", "").split("/")[-1]
        source_metadata = source_instance.get("metadata", {}).get("items", [])
        metadata_items = [item for item in source_metadata if item.get("key") != "ssh-keys"]
        target_instance_body = {
            "name": target_instance_name,
            "machineType": f"zones/{target_zone}/machineTypes/{machine_type}",
            "disks": [
                {
                    "boot": True,
                    "autoDelete": True,
                    "source": f"projects/{project_id}/zones/{target_zone}/disks/{target_disk_name}",
                }
            ],
            "networkInterfaces": source_instance.get("networkInterfaces", []),
            "metadata": {"items": metadata_items},
        }

        try:
            instance_operation = self.compute.instances().insert(
                project=project_id,
                zone=target_zone,
                body=target_instance_body,
            ).execute()
            self._wait_for_zone_operation(project_id, target_zone, instance_operation["name"])
        except HttpError as exc:
            return {
                "vm_id": vm_id,
                "status": "failed",
                "reason": f"Failed to create target instance: {exc}",
            }

        return {
            "vm_id": vm_id,
            "project_id": project_id,
            "source_zone": source_zone,
            "target_zone": target_zone,
            "instance_name": target_instance_name,
            "downtime_seconds": downtime_seconds,
            "status": "migrated",
            "migration_type": "hot",
            "note": "Hot migration attempted using live disk snapshot and target instance creation.",
        }

    def _wait_for_zone_operation(self, project_id: str, zone: str, operation_name: str) -> None:
        while True:
            operation = self.compute.zoneOperations().get(
                project=project_id,
                zone=zone,
                operation=operation_name,
            ).execute()
            if operation.get("status") == "DONE":
                if operation.get("error"):
                    raise RuntimeError(operation["error"])
                return
            time.sleep(2)
