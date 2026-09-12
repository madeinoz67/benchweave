TEST-ONLY signing material for the WP06 fixture catalogue. Never a production
trust root. Regenerating these keys invalidates every committed signature —
do not.

Only the PUBLIC halves (`*.pub.pem`) are committed. The private halves
(`main.pem`, `originb.pem`) live as GitHub repo secrets
(`BENCHWEAVE_FIXTURE_KEY_MAIN`, `BENCHWEAVE_FIXTURE_KEY_ORIGINB`) and are
materialised into this directory by CI (see `.github/workflows/ci.yml`).
Locally, keep untracked copies here — the fixture builder needs them to
re-sign; they are matched by `.gitignore` and must never be committed.
