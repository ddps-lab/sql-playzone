import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKER = ROOT / "IaC" / "packer" / "sql-playzone.pkr.hcl"
PROVISIONER = ROOT / "IaC" / "packer" / "provision-artifact.sh"
BASE_PACKER = ROOT / "IaC" / "packer" / "base" / "builder-base.pkr.hcl"
BASE_PROVISIONER = ROOT / "IaC" / "packer" / "base" / "provision-builder-base.sh"
FOUNDATION = ROOT / "IaC" / "foundation" / "main.tf"
CTFD_DOCKERFILE = ROOT / "platform" / "Dockerfile"
JUDGE_DOCKERFILE = ROOT / "platform" / "CTFd" / "plugins" / "sql_challenges" / "Dockerfile"


class ArtifactBuildPerformanceTests(unittest.TestCase):
    def test_release_builder_uses_prepared_ami_and_right_sized_resources(self):
        packer = PACKER.read_text()
        self.assertIn('variable "builder_base_ami_id"', packer)
        self.assertIn("source_ami                  = var.builder_base_ami_id", packer)
        self.assertIn('instance_type               = "c7g.xlarge"', packer)
        self.assertIn("volume_size           = 16", packer)

        self.assertTrue(BASE_PACKER.exists())
        self.assertTrue(BASE_PROVISIONER.exists())

    def test_builds_run_concurrently_with_channel_scoped_registry_caches(self):
        provisioner = PROVISIONER.read_text()
        self.assertIn("docker buildx build", provisioner)
        self.assertIn("--cache-from", provisioner)
        self.assertIn("--cache-to", provisioner)
        self.assertIn('cache-${ARTIFACT_CHANNEL}', provisioner)
        self.assertRegex(provisioner, r'build_image\s+"ctfd"[^\n]+\s+&')
        self.assertRegex(provisioner, r'build_image\s+"sql-judge"[^\n]+\s+&')

        foundation = FOUNDATION.read_text()
        self.assertIn('resource "aws_ecr_repository" "build_cache"', foundation)
        self.assertIn('image_tag_mutability = "MUTABLE"', foundation)

    def test_dependency_layers_precede_application_sources(self):
        ctfd = CTFD_DOCKERFILE.read_text()
        self.assertLess(ctfd.index("COPY requirements.txt"), ctfd.index("COPY . /opt/CTFd"))
        self.assertLess(ctfd.index("pip install --no-cache-dir -r requirements.txt"), ctfd.index("COPY . /opt/CTFd"))

        judge = JUDGE_DOCKERFILE.read_text()
        self.assertLess(judge.index("RUN go mod download"), judge.index("COPY sql_judge_server.go"))
        self.assertNotIn("go mod tidy", judge)

    def test_build_cache_is_removed_but_runtime_images_are_retained(self):
        provisioner = PROVISIONER.read_text()
        self.assertIn("docker buildx rm", provisioner)
        self.assertIn("docker builder prune -af", provisioner)
        self.assertIn("docker image rm moby/buildkit:buildx-stable-1", provisioner)
        self.assertIn('docker pull "$ctfd_tag"', provisioner)
        self.assertIn('docker pull "$sql_judge_tag"', provisioner)


if __name__ == "__main__":
    unittest.main()
