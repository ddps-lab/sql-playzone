import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "platform" / "docker-compose.production.yml"
PROVISIONER = ROOT / "IaC" / "packer" / "provision-artifact.sh"
USER_DATA = ROOT / "IaC" / "ec2" / "userdata.sh"


class RuntimeImageTests(unittest.TestCase):
    def test_public_runtime_images_are_pinned_and_preloaded(self):
        compose = COMPOSE.read_text()
        for image in ("alpine", "nginx"):
            self.assertRegex(compose, rf"image: {image}:[^\n]+@sha256:[0-9a-f]{{64}}")

        provisioner = PROVISIONER.read_text()
        self.assertIn("docker compose", provisioner)
        self.assertRegex(provisioner, r"pull\s+permissions\s+nginx")

    def test_boot_does_not_pull_public_images(self):
        user_data = USER_DATA.read_text()
        self.assertNotRegex(user_data, r"docker compose[^\n]* pull")
        self.assertRegex(user_data, r"docker compose[^\n]* up --pull never -d")


if __name__ == "__main__":
    unittest.main()
