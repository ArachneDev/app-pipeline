"""The promote step against a real registry and real skopeo: the digest is kept exactly, for an image and for an index.

Needs skopeo, curl and a registry in $REGISTRY (host:port, plain HTTP); CI's
`registry` job provides them, and `make check` skips this. It proves what the
stub tests can't: `skopeo copy --all --preserve-digests` ends on the same
digest the registry served, whatever the manifest type.
"""

import json
import os
import subprocess
import tempfile
import unittest
import urllib.request

from stubs import Health
from workflow import run_step

REGISTRY = os.environ.get("REGISTRY", "")
BUSYBOX = "docker.io/library/busybox@sha256:5624bb6777cf469b1fb50ae3f981b15d2715ee2fffaf20b9998cfb7843726835"
REPO = f"{REGISTRY}/app"
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json", "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json", "application/vnd.docker.distribution.manifest.v2+json",
])


def served_digest(ref):
    """The digest the registry itself reports for a tag or digest, from its Docker-Content-Digest header."""
    req = urllib.request.Request(f"http://{REGISTRY}/v2/app/manifests/{ref}", method="HEAD", headers={"Accept": ACCEPT})
    with urllib.request.urlopen(req) as r:
        return r.headers["Docker-Content-Digest"]


def put_index(tag, image_digest, size, note):
    body = json.dumps({
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": image_digest, "size": size,
                       "platform": {"architecture": "amd64", "os": "linux"}}],
        "annotations": {"note": note},
    }).encode()
    req = urllib.request.Request(f"http://{REGISTRY}/v2/app/manifests/{tag}", data=body, method="PUT",
                                 headers={"Content-Type": "application/vnd.oci.image.index.v1+json"})
    with urllib.request.urlopen(req) as r:
        return r.headers["Docker-Content-Digest"]


@unittest.skipUnless(REGISTRY, "set REGISTRY=host:port (plain HTTP) to run against a real registry")
class RealRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No credentials: point skopeo at an auth file that does not exist, so it never reads /run/containers/<uid>.
        auth = tempfile.TemporaryDirectory()
        cls.addClassCleanup(auth.cleanup)
        os.environ["REGISTRY_AUTH_FILE"] = os.path.join(auth.name, "auth.json")
        subprocess.run(["skopeo", "copy", "--dest-tls-verify=false", f"docker://{BUSYBOX}", f"docker://{REPO}:image"], check=True, capture_output=True)
        cls.image = served_digest("image")
        size = int(urllib.request.urlopen(urllib.request.Request(f"http://{REGISTRY}/v2/app/manifests/image", headers={"Accept": ACCEPT})).headers["Content-Length"])
        cls.index_a = put_index("index-a", cls.image, size, "a")
        cls.index_b = put_index("index-b", cls.image, size, "b")

    def tag(self, name, digest):
        subprocess.run(["skopeo", "copy", "--all", "--preserve-digests", "--src-tls-verify=false", "--dest-tls-verify=false",
                        f"docker://{REPO}@{digest}", f"docker://{REPO}:{name}"], check=True, capture_output=True)

    def promote(self, new, behave=None, **extra):
        health = Health(lambda: None, {}, behave) if behave else None
        env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), "INSECURE_REGISTRY": "true",
               "REGISTRY_AUTH_FILE": os.environ["REGISTRY_AUTH_FILE"], "IMAGE_REPO": REPO, "VERSION": "v2.0.0", "CHANNEL": "staging", "DIGEST": new,
               "WINDOW": "4", "FAILURES": "2", "HEALTH_INTERVAL": "0.5", "PRODUCTION_URL": "",
               "STAGING_URL": health.url if health else "", "CF_ACCESS_CLIENT_ID": "", "CF_ACCESS_CLIENT_SECRET": ""} | extra
        try:
            result = run_step("promote", env)
        finally:
            if health:
                health.close()
        return result, result.stdout + result.stderr

    def check(self, old, new, kind_old):
        # The recorded digest is what the registry served, and the copy ends on it exactly.
        self.assertEqual(served_digest(old), old)
        self.tag("staging", old)
        result, out = self.promote(new)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(served_digest("staging"), new, out)
        self.tag("staging", old)
        result, out = self.promote(new, behave=lambda v, n: (500, "boom"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"Recorded :staging at {old} ({kind_old})", out)
        self.assertEqual(served_digest("staging"), old, out)

    def test_index_replaced_by_an_image_and_restored(self):
        self.check(self.index_a, self.image, "index")

    def test_image_replaced_by_an_index_and_restored(self):
        self.check(self.image, self.index_b, "image")

    def test_a_tag_that_does_not_exist_is_told_apart_from_an_error(self):
        # Nothing else in this file writes :prod, so the first release finds none.
        result, out = self.promote(self.image, CHANNEL="production", VERSION="v0.0.1")
        self.assertEqual(result.returncode, 0, out)
        self.assertIn(":prod does not exist yet", out)


if __name__ == "__main__":
    unittest.main()
