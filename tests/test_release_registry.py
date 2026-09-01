import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from release_registry import (  # noqa: E402
    ReleaseRegistryError,
    parse_ecr_digest_uri,
    protection_closure,
    validate_manifest,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def manifest(release_id: str, ami_id: str, digest: str) -> dict:
    channel = release_id.split("-", 1)[0]
    return {
        "schema_version": 1,
        "release_id": release_id,
        "channel": channel,
        "commit_sha": "1" * 40,
        "built_at": "2026-09-01T00:00:00+00:00",
        "base_ami_id": "ami-11111111",
        "ami_id": ami_id,
        "ctfd_image": f"786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/sql-2026-s2-ctfd@{digest}",
        "sql_judge_image": f"786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/sql-2026-s2-sql-judge@{digest}",
    }


class ReleaseRegistryTests(unittest.TestCase):
    def test_manifest_requires_digest_uris(self):
        candidate = manifest("dev-111111111111-20260901T000000Z", "ami-aaaaaaaa", DIGEST_A)
        validate_manifest(candidate)
        candidate["ctfd_image"] = "repository:latest"
        with self.assertRaises(ReleaseRegistryError):
            validate_manifest(candidate)

    def test_active_release_is_protected_after_two_new_builds(self):
        release_a = "dev-aaaaaaaaaaaa-20260901T000000Z"
        release_b = "dev-bbbbbbbbbbbb-20260901T010000Z"
        release_c = "dev-cccccccccccc-20260901T020000Z"
        manifests = {
            release_a: manifest(release_a, "ami-aaaaaaaa", DIGEST_A),
            release_b: manifest(release_b, "ami-bbbbbbbb", DIGEST_B),
            release_c: manifest(release_c, "ami-cccccccc", DIGEST_B),
        }

        releases, amis, images = protection_closure(
            {release_b, release_c}, {release_a}, {"ami-aaaaaaaa"}, manifests
        )

        self.assertEqual(releases, {release_a, release_b, release_c})
        self.assertIn("ami-aaaaaaaa", amis)
        self.assertIn(
            ("sql-2026-s2-ctfd", DIGEST_A),
            images,
        )

    def test_active_ami_protects_its_manifest_without_release_tag(self):
        release_a = "main-aaaaaaaaaaaa-20260901T000000Z"
        manifests = {release_a: manifest(release_a, "ami-aaaaaaaa", DIGEST_A)}
        releases, _, _ = protection_closure(set(), set(), {"ami-aaaaaaaa"}, manifests)
        self.assertEqual(releases, {release_a})

    def test_ecr_digest_parser_rejects_tags(self):
        with self.assertRaises(ReleaseRegistryError):
            parse_ecr_digest_uri(
                "786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/repository:latest"
            )


if __name__ == "__main__":
    unittest.main()
