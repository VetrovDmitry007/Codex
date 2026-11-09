"""Проверяет безопасную конфигурацию частного Compose-развёртывания."""

from pathlib import Path
import unittest
from unittest.mock import patch

import yaml
from searx.settings_loader import load_settings


ROOT = Path(__file__).resolve().parents[3]


class PrivateDeploymentConfigTest(unittest.TestCase):
    """Проверяет параметры собственного контейнера SearXNG."""

    def test_compose_uses_private_custom_image_without_cache_service(self):
        """Compose собирает один сервис и публикует порт только на loopback."""
        compose = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))
        services = compose["services"]

        self.assertEqual(set(services), {"searxng"})
        service = services["searxng"]
        self.assertTrue(service["image"].startswith("bondnav-searxng:"))
        self.assertEqual(service["build"]["context"], "./source/SearXNG")
        self.assertEqual(service["build"]["dockerfile"], "container/Dockerfile")
        dockerfile = (ROOT / "container" / "Dockerfile").read_text(encoding="utf-8")
        self.assertEqual(dockerfile.count("@sha256:"), 2)
        self.assertEqual(service["ports"], ["127.0.0.1:8088:8080"])
        self.assertEqual(service["restart"], "unless-stopped")
        self.assertEqual(service["environment"]["SEARXNG_LIMITER"], "false")
        self.assertEqual(service["environment"]["SEARXNG_PUBLIC_INSTANCE"], "false")
        self.assertNotIn("SEARXNG_SECRET", service["environment"])
        self.assertEqual(service["secrets"], ["searxng_secret"])
        self.assertEqual(compose["secrets"]["searxng_secret"]["file"], "./secrets/searxng_secret")
        entrypoint = (ROOT / "deploy" / "private-entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("cat /run/secrets/searxng_secret", entrypoint)
        self.assertIn("export SEARXNG_SECRET", entrypoint)
        self.assertIn("exec /usr/local/searxng/entrypoint.sh", entrypoint)

    def test_settings_enable_html_and_json_without_limiter(self):
        """Настройки включают оба формата и выключают встроенный Limiter."""
        settings = yaml.safe_load((ROOT / "deploy" / "settings.yml").read_text(encoding="utf-8"))

        self.assertEqual(settings["search"]["formats"], ["html", "json"])
        self.assertIs(settings["server"]["limiter"], False)
        self.assertIs(settings["server"]["public_instance"], False)
        self.assertNotIn("secret_key", settings["server"])
        self.assertIs(settings["valkey"]["url"], False)

    def test_settings_load_with_default_configuration(self):
        """Загрузчик SearXNG объединяет частные настройки со стандартными."""
        settings_path = ROOT / "deploy" / "settings.yml"

        with patch.dict("os.environ", {"SEARXNG_SETTINGS_PATH": str(settings_path)}):
            settings, _message = load_settings()

        self.assertEqual(settings["search"]["formats"], ["html", "json"])
        self.assertIs(settings["server"]["limiter"], False)
        self.assertIs(settings["server"]["public_instance"], False)
        self.assertIs(settings["valkey"]["url"], False)
        self.assertTrue(settings["server"]["secret_key"])


if __name__ == "__main__":
    unittest.main()
