"""The promote step: move a channel tag by digest, verify the release, move it back on failure.

Runs the real `promote` step from .github/workflows/build.yml against a stub
`skopeo` (a directory) and a stub health server, so nothing is deployed. CI's
`registry` job runs the same step against a real registry.
"""

import tempfile
import unittest
from pathlib import Path

from stubs import Health, Registry
from workflow import run_step

# A window of 4 s: failures count from 2 s on, or once the new version has shown.
FAST = {"WINDOW": "4", "FAILURES": "2", "HEALTH_INTERVAL": "0.5"}


def healthy(version, polls):
    return 200, f"ok {version}\n"


class PromoteBase(unittest.TestCase):
    def setUp(self):
        self.reg = Registry()
        self.old = self.reg.add("old", tags=["prod", "v1.0.0"])
        self.new = self.reg.add("new", tags=["v1.1.0"])
        self.versions = {self.old: "v1.0.0", self.new: "v1.1.0"}
        self.health = None
        self.addCleanup(self.reg.close)

    def serve(self, behave):
        self.health = Health(lambda: self.reg.tag_of("prod"), self.versions, behave)
        self.addCleanup(self.health.close)
        return self.health.url

    def promote(self, url="", digest=None, version="v1.1.0", channel="production", **extra):
        env = self.reg.env() | FAST | {
            "IMAGE_REPO": "ghcr.io/arachnedev/app", "VERSION": version, "CHANNEL": channel,
            "DIGEST": self.new if digest is None else digest,
            "PRODUCTION_URL": url if channel == "production" else "",
            "STAGING_URL": url if channel == "staging" else "",
            "CF_ACCESS_CLIENT_ID": "", "CF_ACCESS_CLIENT_SECRET": "",
        } | extra
        result = run_step("promote", env)
        return result, result.stdout + result.stderr


class Move(PromoteBase):
    def test_moves_prod_to_the_digest_by_copy_with_no_rebuild(self):
        result, out = self.promote()
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self.reg.tag_of("prod"), self.new)
        copies = [c for c in self.reg.calls() if c.startswith("copy")]
        self.assertEqual(len(copies), 1, copies)
        self.assertIn("--all --preserve-digests", copies[0])
        self.assertIn(f"@{self.new}", copies[0])

    def test_records_the_digest_prod_pointed_at(self):
        result, out = self.promote()
        self.assertIn(f"Recorded :prod at {self.old}", out)

    def test_repromote_reads_the_version_tag_and_moves_to_it(self):
        self.reg.tag("prod", self.new)
        result, out = self.promote(digest="", version="v1.0.0")
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self.reg.tag_of("prod"), self.old)

    def test_repromote_of_a_version_that_does_not_exist_moves_nothing(self):
        result, out = self.promote(digest="", version="v9.9.9")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist", out)
        self.assertEqual(self.reg.tag_of("prod"), self.old)

    def test_staging_moves_staging_not_prod(self):
        result, out = self.promote(channel="staging")
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self.reg.tag_of("staging"), self.new)
        self.assertEqual(self.reg.tag_of("prod"), self.old)

    def test_same_digest_is_not_copied_again(self):
        self.reg.tag("prod", self.new)
        result, out = self.promote()
        self.assertEqual(result.returncode, 0, out)
        self.assertFalse([c for c in self.reg.calls() if c.startswith("copy")])

    def test_no_health_url_skips_the_check(self):
        result, out = self.promote(url="")
        self.assertEqual(result.returncode, 0, out)
        self.assertIn("not verified", out)

    def test_bad_inputs_move_nothing(self):
        for key, value in (("WINDOW", "0"), ("WINDOW", "99999"), ("FAILURES", "0"), ("WINDOW", "x")):
            with self.subTest(**{key: value}):
                result, out = self.promote(**{key: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.reg.tag_of("prod"), self.old)


class RegistryFaults(PromoteBase):
    def test_a_registry_read_error_moves_nothing(self):
        result, out = self.promote(STUB_READ_ERROR="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([c for c in self.reg.calls() if c.startswith("copy")])
        self.assertEqual(self.reg.tag_of("prod"), self.old)

    def test_a_failed_copy_leaves_the_tag_and_fails(self):
        result, out = self.promote(STUB_COPY_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("prod"), self.old)

    def test_the_first_release_has_nothing_to_move_back_to(self):
        (self.reg.dir / "tags" / "prod").unlink()
        url = self.serve(lambda v, n: (503, "down"))
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no earlier digest", out)
        self.assertEqual(self.reg.tag_of("prod"), self.new)


class VerifyAndRevert(PromoteBase):
    def test_a_release_that_never_reports_the_new_version_is_moved_back_and_fails_with_the_reason(self):
        # The app keeps serving the old version, as when auto-update rolls the new image back.
        url = self.serve(lambda v, n: (200, "ok v1.0.0\n"))
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("prod"), self.old, out)
        self.assertIn("2 polls in a row", out)
        self.assertIn("never showed", out)
        self.assertIn("without v1.1.0 in the body", out)
        self.assertIn(f":prod is back at {self.old}", out)

    def test_a_release_that_answers_5xx_is_moved_back(self):
        url = self.serve(lambda v, n: (503, "unavailable"))
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("prod"), self.old)
        self.assertIn("HTTP 503", out)

    def test_a_down_app_is_moved_back(self):
        url = self.serve(healthy)
        self.health.close()
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("prod"), self.old)
        self.assertIn("no answer", out)

    def test_a_release_that_shows_and_then_fails_in_a_row_is_moved_back(self):
        url = self.serve(lambda v, n: (200, "ok v1.1.0\n") if n <= 2 else (502, "bad gateway"))
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("prod"), self.old)
        self.assertIn("had shown and then stopped", out)

    def test_a_short_blip_does_not_move_a_good_release_back(self):
        # One failed poll, fewer than N in a row, after the version showed.
        url = self.serve(lambda v, n: (502, "bad gateway") if n == 3 else (200, f"ok {v}\n"))
        result, out = self.promote(url=url)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self.reg.tag_of("prod"), self.new)

    def test_the_old_version_before_the_start_up_allowance_is_not_a_failure(self):
        # The timer has not pulled yet: the old version answers for the first half of the window.
        # It follows the tag after that, as the host would.
        self.served = 0
        def behave(v, n):
            return (200, f"ok {v}\n") if n > 3 else (200, "ok v1.0.0\n")
        url = self.serve(behave)
        result, out = self.promote(url=url)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(self.reg.tag_of("prod"), self.new)

    def test_the_version_must_be_a_whole_token(self):
        # v1.1.0 is not in v1.1.01.
        url = self.serve(lambda v, n: (200, "ok v1.1.01\n"))
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("prod"), self.old)

    def test_an_index_is_restored_by_its_exact_digest(self):
        idx = self.reg.add("old-index", kind="index", tags=["prod"])
        url = self.serve(lambda v, n: (500, "boom"))
        result, out = self.promote(url=url)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"Recorded :prod at {idx} (index)", out)
        self.assertEqual(self.reg.tag_of("prod"), idx)
        self.assertTrue(any(c.startswith("copy") and f"@{idx}" in c and "--preserve-digests" in c for c in self.reg.calls()))

    def test_staging_reverts_the_same_way(self):
        self.reg.tag("staging", self.old)
        url = self.serve(lambda v, n: (500, "boom"))
        result, out = self.promote(url=url, channel="staging")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reg.tag_of("staging"), self.old)

    def test_a_failed_move_back_is_reported(self):
        url = self.serve(lambda v, n: (500, "boom"))
        result, out = self.promote(url=url, STUB_COPY_FAIL_AFTER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("also failed", out)
        self.assertEqual(self.reg.tag_of("prod"), self.new)


class AccessToken(PromoteBase):
    def test_the_service_token_is_sent_and_never_printed(self):
        url = self.serve(healthy)
        result, out = self.promote(url=url, CF_ACCESS_CLIENT_ID="id-canary-7c1", CF_ACCESS_CLIENT_SECRET="secret-canary-9d4")
        self.assertEqual(result.returncode, 0, out)
        sent = self.health.headers_seen[0]
        self.assertEqual(sent.get("CF-Access-Client-Id"), "id-canary-7c1")
        self.assertEqual(sent.get("CF-Access-Client-Secret"), "secret-canary-9d4")
        self.assertNotIn("canary", out)

    def test_no_token_sends_no_access_headers(self):
        url = self.serve(healthy)
        self.promote(url=url)
        self.assertNotIn("CF-Access-Client-Id", self.health.headers_seen[0])


if __name__ == "__main__":
    unittest.main()
