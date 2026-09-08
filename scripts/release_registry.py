#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


CHANNELS = {"dev", "main"}
MANIFEST_FIELDS = {
    "schema_version",
    "release_id",
    "channel",
    "commit_sha",
    "built_at",
    "base_ami_id",
    "ami_id",
    "ctfd_image",
    "sql_judge_image",
}
ECR_DIGEST_URI = re.compile(
    r"^(?P<registry>\d+\.dkr\.ecr\.[^.]+\.amazonaws\.com)/"
    r"(?P<repository>[a-zA-Z0-9._/-]+)@(?P<digest>sha256:[0-9a-f]{64})$"
)


class ReleaseRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class AwsConfig:
    profile: str
    region: str


class AwsClient:
    def __init__(self, config: AwsConfig):
        self.config = config

    def run(
        self,
        service: str,
        operation: str,
        *arguments: str,
        output_json: bool = True,
        check: bool = True,
    ) -> Any:
        command = [
            "aws",
            service,
            operation,
            "--profile",
            self.config.profile,
            "--region",
            self.config.region,
            *arguments,
        ]
        if output_json:
            command.extend(["--output", "json"])
        result = subprocess.run(command, text=True, capture_output=True)
        if check and result.returncode != 0:
            raise ReleaseRegistryError(
                f"AWS command failed: {' '.join(command[:3])}: {result.stderr.strip()}"
            )
        if result.returncode != 0:
            return {
                "__error__": result.stderr.strip(),
                "__returncode__": result.returncode,
            }
        if not output_json:
            return result
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)


class ReleaseRegistry:
    def __init__(self, aws: AwsClient, namespace: str):
        self.aws = aws
        self.namespace = namespace.rstrip("/")

    def release_path(self, release_id: str) -> str:
        return f"{self.namespace}/releases/{release_id}"

    def pointer_path(self, channel: str, pointer: str) -> str:
        validate_channel(channel)
        if pointer not in {"current", "previous"}:
            raise ReleaseRegistryError(f"Unsupported pointer: {pointer}")
        return f"{self.namespace}/channels/{channel}/{pointer}"

    def get_parameter(self, name: str) -> str | None:
        result = self.aws.run(
            "ssm", "get-parameter", "--name", name, check=False
        )
        if isinstance(result, dict) and result.get("__returncode__"):
            if "ParameterNotFound" in result["__error__"]:
                return None
            raise ReleaseRegistryError(
                f"Could not read SSM parameter {name}: {result['__error__']}"
            )
        if result is None:
            return None
        return result["Parameter"]["Value"]

    def put_parameter(self, name: str, value: str, *, overwrite: bool) -> None:
        arguments = ["--name", name, "--type", "String", "--value", value]
        arguments.append("--overwrite" if overwrite else "--no-overwrite")
        self.aws.run("ssm", "put-parameter", *arguments)

    def delete_parameter(self, name: str) -> None:
        self.aws.run("ssm", "delete-parameter", "--name", name)

    def get_manifest(self, release_id: str) -> dict[str, Any]:
        value = self.get_parameter(self.release_path(release_id))
        if value is None:
            raise ReleaseRegistryError(f"Release does not exist: {release_id}")
        try:
            manifest = json.loads(value)
        except json.JSONDecodeError as error:
            raise ReleaseRegistryError(f"Invalid release manifest: {release_id}") from error
        validate_manifest(manifest, expected_release_id=release_id)
        return manifest

    def list_manifests(self) -> dict[str, dict[str, Any]]:
        result = self.aws.run(
            "ssm",
            "get-parameters-by-path",
            "--path",
            f"{self.namespace}/releases",
            "--recursive",
        )
        manifests: dict[str, dict[str, Any]] = {}
        for parameter in (result or {}).get("Parameters", []):
            release_id = parameter["Name"].rsplit("/", 1)[-1]
            try:
                manifest = json.loads(parameter["Value"])
            except json.JSONDecodeError as error:
                raise ReleaseRegistryError(
                    f"Invalid release manifest: {parameter['Name']}"
                ) from error
            validate_manifest(manifest, expected_release_id=release_id)
            manifests[release_id] = manifest
        return manifests

    def pointer_release_ids(self) -> set[str]:
        result = self.aws.run(
            "ssm",
            "get-parameters-by-path",
            "--path",
            f"{self.namespace}/channels",
            "--recursive",
        )
        pointers = set()
        for parameter in (result or {}).get("Parameters", []):
            if parameter["Name"].rsplit("/", 1)[-1] in {"current", "previous"}:
                pointers.add(parameter["Value"])
        return pointers

    def publish_manifest(self, manifest: dict[str, Any]) -> None:
        validate_manifest(manifest)
        self.put_parameter(
            self.release_path(manifest["release_id"]),
            json.dumps(manifest, separators=(",", ":"), sort_keys=True),
            overwrite=False,
        )

    def set_channel_release(self, channel: str, release_id: str) -> None:
        validate_channel(channel)
        manifest = self.get_manifest(release_id)
        if manifest["channel"] != channel:
            raise ReleaseRegistryError(
                f"Release {release_id} belongs to {manifest['channel']}, not {channel}"
            )

        current_path = self.pointer_path(channel, "current")
        previous_path = self.pointer_path(channel, "previous")
        current = self.get_parameter(current_path)
        if current == release_id:
            return
        if current is not None:
            self.put_parameter(previous_path, current, overwrite=True)
        self.put_parameter(current_path, release_id, overwrite=True)

    def retire_channel(self, channel: str, *, apply: bool) -> list[str]:
        validate_channel(channel)
        active_releases, _, _ = discover_active_artifacts(
            self.aws, artifact_prefix=self.namespace.rsplit("/", 1)[-1]
        )
        active_manifests = [
            self.get_manifest(release_id)
            for release_id in active_releases
            if self.get_parameter(self.release_path(release_id)) is not None
        ]
        if any(manifest["channel"] == channel for manifest in active_manifests):
            raise ReleaseRegistryError(
                f"Channel {channel} is still referenced by an active runtime"
            )

        paths = [
            self.pointer_path(channel, "current"),
            self.pointer_path(channel, "previous"),
        ]
        existing = [path for path in paths if self.get_parameter(path) is not None]
        if apply:
            for path in existing:
                self.delete_parameter(path)
        return existing


def validate_channel(channel: str) -> None:
    if channel not in CHANNELS:
        raise ReleaseRegistryError(f"Channel must be one of: {', '.join(sorted(CHANNELS))}")


def validate_manifest(
    manifest: dict[str, Any], expected_release_id: str | None = None
) -> None:
    missing = MANIFEST_FIELDS - manifest.keys()
    if missing:
        raise ReleaseRegistryError(
            f"Manifest is missing fields: {', '.join(sorted(missing))}"
        )
    if manifest["schema_version"] != 1:
        raise ReleaseRegistryError("Unsupported manifest schema_version")
    validate_channel(manifest["channel"])
    if expected_release_id and manifest["release_id"] != expected_release_id:
        raise ReleaseRegistryError("Manifest release_id does not match its parameter name")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["commit_sha"]):
        raise ReleaseRegistryError("Manifest commit_sha must be a full Git SHA")
    if not re.fullmatch(r"ami-[0-9a-f]+", manifest["ami_id"]):
        raise ReleaseRegistryError("Manifest ami_id is invalid")
    parse_ecr_digest_uri(manifest["ctfd_image"])
    parse_ecr_digest_uri(manifest["sql_judge_image"])


def parse_ecr_digest_uri(uri: str) -> tuple[str, str]:
    match = ECR_DIGEST_URI.fullmatch(uri)
    if match is None:
        raise ReleaseRegistryError(f"Invalid ECR digest URI: {uri}")
    return match.group("repository"), match.group("digest")


def tags_to_dict(tags: Iterable[dict[str, str]]) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in tags}


def resolve_launch_template_ami(
    aws: AwsClient, launch_template_id: str, version: str
) -> str:
    result = aws.run(
        "ec2",
        "describe-launch-template-versions",
        "--launch-template-id",
        launch_template_id,
        "--versions",
        version,
    )
    versions = result.get("LaunchTemplateVersions", [])
    if len(versions) != 1:
        raise ReleaseRegistryError(
            f"Could not resolve launch template {launch_template_id} version {version}"
        )
    return versions[0]["LaunchTemplateData"]["ImageId"]


def discover_active_artifacts(
    aws: AwsClient, artifact_prefix: str
) -> tuple[set[str], set[str], set[str]]:
    active_releases: set[str] = set()
    active_amis: set[str] = set()
    instance_ids: set[str] = set()

    asg_result = aws.run("autoscaling", "describe-auto-scaling-groups") or {}
    for asg in asg_result.get("AutoScalingGroups", []):
        tags = tags_to_dict(asg.get("Tags", []))
        if tags.get("Project") != "sql-playzone" or tags.get("ArtifactPrefix") != artifact_prefix:
            continue
        if tags.get("ArtifactRelease"):
            active_releases.add(tags["ArtifactRelease"])
        for instance in asg.get("Instances", []):
            if instance.get("LifecycleState", "").startswith(("Pending", "InService")):
                instance_ids.add(instance["InstanceId"])

        policy = asg.get("MixedInstancesPolicy", {})
        specification = (
            policy.get("LaunchTemplate", {})
            .get("LaunchTemplateSpecification", {})
        )
        if specification.get("LaunchTemplateId"):
            active_amis.add(
                resolve_launch_template_ami(
                    aws,
                    specification["LaunchTemplateId"],
                    specification.get("Version", "$Default"),
                )
            )

    template_result = aws.run(
        "ec2",
        "describe-launch-templates",
        "--filters",
        "Name=tag:Project,Values=sql-playzone",
        f"Name=tag:ArtifactPrefix,Values={artifact_prefix}",
    ) or {"LaunchTemplates": []}
    for template in template_result.get("LaunchTemplates", []):
        active_amis.add(
            resolve_launch_template_ami(
                aws, template["LaunchTemplateId"], str(template["DefaultVersionNumber"])
            )
        )

    if instance_ids:
        instance_result = aws.run(
            "ec2", "describe-instances", "--instance-ids", *sorted(instance_ids)
        )
        for reservation in instance_result.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                if instance["State"]["Name"] not in {"pending", "running"}:
                    continue
                active_amis.add(instance["ImageId"])
                tags = tags_to_dict(instance.get("Tags", []))
                if tags.get("ArtifactRelease"):
                    active_releases.add(tags["ArtifactRelease"])

    return active_releases, active_amis, instance_ids


def protection_closure(
    pointer_releases: set[str],
    active_releases: set[str],
    active_amis: set[str],
    manifests: dict[str, dict[str, Any]],
) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    protected_releases = pointer_releases | active_releases
    for release_id, manifest in manifests.items():
        if manifest["ami_id"] in active_amis:
            protected_releases.add(release_id)

    unknown = protected_releases - manifests.keys()
    if unknown:
        raise ReleaseRegistryError(
            f"Protected releases have no manifest: {', '.join(sorted(unknown))}"
        )

    protected_amis = set(active_amis)
    protected_images: set[tuple[str, str]] = set()
    for release_id in protected_releases:
        manifest = manifests[release_id]
        protected_amis.add(manifest["ami_id"])
        protected_images.add(parse_ecr_digest_uri(manifest["ctfd_image"]))
        protected_images.add(parse_ecr_digest_uri(manifest["sql_judge_image"]))
    return protected_releases, protected_amis, protected_images


def delete_ami(aws: AwsClient, ami_id: str) -> None:
    result = aws.run("ec2", "describe-images", "--image-ids", ami_id)
    images = result.get("Images", [])
    if not images:
        return
    snapshots = {
        mapping["Ebs"]["SnapshotId"]
        for mapping in images[0].get("BlockDeviceMappings", [])
        if mapping.get("Ebs", {}).get("SnapshotId")
    }
    aws.run("ec2", "deregister-image", "--image-id", ami_id)
    for snapshot_id in sorted(snapshots):
        aws.run("ec2", "delete-snapshot", "--snapshot-id", snapshot_id)


def prune_artifacts(
    registry: ReleaseRegistry, artifact_prefix: str, *, apply: bool
) -> list[dict[str, Any]]:
    manifests = registry.list_manifests()
    pointer_releases = registry.pointer_release_ids()
    active_releases, active_amis, _ = discover_active_artifacts(
        registry.aws, artifact_prefix
    )
    protected_releases, protected_amis, protected_images = protection_closure(
        pointer_releases, active_releases, active_amis, manifests
    )

    candidates = []
    for release_id, manifest in sorted(manifests.items()):
        if release_id in protected_releases or manifest["ami_id"] in protected_amis:
            continue
        images = {
            parse_ecr_digest_uri(manifest["ctfd_image"]),
            parse_ecr_digest_uri(manifest["sql_judge_image"]),
        }
        candidates.append(
            {
                "release_id": release_id,
                "ami_id": manifest["ami_id"],
                "images": sorted(f"{repository}@{digest}" for repository, digest in images),
            }
        )
        if not apply:
            continue
        delete_ami(registry.aws, manifest["ami_id"])
        for repository, digest in images - protected_images:
            registry.aws.run(
                "ecr",
                "batch-delete-image",
                "--repository-name",
                repository,
                "--image-ids",
                f"imageDigest={digest}",
            )
        registry.delete_parameter(registry.release_path(release_id))
    return candidates


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent
