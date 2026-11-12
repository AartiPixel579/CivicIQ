"""
CORS Security Regression Tests for CivicIQ.
Verifies via FastAPI/Starlette's CORSMiddleware that:
1. Explicitly configured staging Vercel origin is allowed.
2. Unrelated *.vercel.app subdomains are rejected.
3. Explicitly configured production origin is allowed.
4. Unconfigured and wildcard origins are rejected in production.
5. Localhost is allowed in development.
6. Localhost is NOT automatically allowed in production.
7. Valid preflight OPTIONS requests work.
"""

import unittest
from typing import List
from fastapi import FastAPI
from starlette.datastructures import Headers

from backend.app.main import app as main_app, apply_cors_middleware, resolve_cors_origins


def _make_cors_middleware(is_production: bool, allowed_origins: List[str]):
    test_app = FastAPI()
    apply_cors_middleware(test_app, is_production=is_production, allowed_origins=allowed_origins)
    mw = test_app.user_middleware[0]
    return mw.cls(None, **mw.kwargs)


class TestCorsSecurity(unittest.TestCase):
    def test_00_main_app_has_no_wildcard_vercel_regex(self):
        cors_mws = [m for m in main_app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
        self.assertEqual(len(cors_mws), 1)
        self.assertNotIn("allow_origin_regex", cors_mws[0].kwargs)

    def test_01_configured_staging_vercel_origin_allowed(self):
        staging_origin = "https://civiciq-staging.vercel.app"
        cors = _make_cors_middleware(is_production=True, allowed_origins=[staging_origin])
        self.assertTrue(cors.is_allowed_origin(staging_origin))
        self.assertIn("access-control-allow-credentials", {k.lower() for k in cors.simple_headers})

    def test_02_unrelated_vercel_subdomain_rejected(self):
        staging_origin = "https://civiciq-staging.vercel.app"
        attacker_origin = "https://malicious-clone.vercel.app"
        cors = _make_cors_middleware(is_production=True, allowed_origins=[staging_origin])
        self.assertFalse(cors.is_allowed_origin(attacker_origin))

        pre = cors.preflight_response(
            request_headers=Headers({
                "origin": attacker_origin,
                "access-control-request-method": "POST",
            })
        )
        self.assertEqual(pre.status_code, 400)
        self.assertNotIn("access-control-allow-origin", {k.lower() for k in pre.headers})

    def test_03_configured_production_origin_allowed(self):
        prod_origin = "https://civiciq.edisonnj.gov"
        cors = _make_cors_middleware(is_production=True, allowed_origins=[prod_origin])
        self.assertTrue(cors.is_allowed_origin(prod_origin))

    def test_04_unconfigured_and_wildcard_origin_rejected_in_production(self):
        origins = resolve_cors_origins(
            is_production=True,
            allowed_origins=["*", "https://*.vercel.app", "null", "invalid-origin", "https://civiciq.vercel.app/"],
        )
        self.assertEqual(origins, ["https://civiciq.vercel.app"])

        # Empty production origins fail closed
        empty_cors = _make_cors_middleware(is_production=True, allowed_origins=[])
        self.assertFalse(empty_cors.is_allowed_origin("https://civiciq.vercel.app"))
        self.assertFalse(empty_cors.is_allowed_origin("http://localhost:3000"))

        cors = _make_cors_middleware(is_production=True, allowed_origins=["https://civiciq.vercel.app"])
        self.assertFalse(cors.is_allowed_origin("https://unapproved.example.com"))

    def test_05_localhost_allowed_in_development(self):
        cors = _make_cors_middleware(is_production=False, allowed_origins=[])
        self.assertTrue(cors.is_allowed_origin("http://localhost:3000"))
        self.assertTrue(cors.is_allowed_origin("http://127.0.0.1:3000"))

    def test_06_localhost_not_automatically_allowed_in_production(self):
        cors = _make_cors_middleware(is_production=True, allowed_origins=["https://civiciq-staging.vercel.app"])
        self.assertFalse(cors.is_allowed_origin("http://localhost:3000"))
        self.assertFalse(cors.is_allowed_origin("http://127.0.0.1:3000"))

    def test_07_valid_preflight_options_request_works(self):
        staging_origin = "https://civiciq-staging.vercel.app"
        cors = _make_cors_middleware(is_production=True, allowed_origins=[staging_origin])
        pre = cors.preflight_response(
            request_headers=Headers({
                "origin": staging_origin,
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            })
        )
        self.assertEqual(pre.status_code, 200)
        self.assertEqual(pre.headers.get("access-control-allow-origin"), staging_origin)
        self.assertIn("POST", pre.headers.get("access-control-allow-methods", ""))


if __name__ == "__main__":
    unittest.main()
