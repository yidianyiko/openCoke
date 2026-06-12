# Disable Email Auth Production Smoke

Date: 2026-06-12

Deployed commit before script follow-up:
`33aded3b1341758c51c53fade51c082eca28a14c`

Runtime env check on `gcp-coke:/home/whoami/coke-clean/.env`:

```text
COKE_EMAIL_AUTH_ENABLED=0
```

Compose status after deploy and manual web service correction:

```text
coke-clean-coke-api-1            Up 4 minutes (healthy)
coke-clean-coke-outbox-relay-1   Up 4 minutes
coke-clean-coke-scheduler-1      Up 4 minutes
coke-clean-coke-web-1            Up 3 minutes
coke-clean-coke-worker-1         Up 4 minutes
coke-clean-postgres-1            Up 12 days (healthy)
coke-clean-redis-1               Up 12 days (healthy)
```

Server-local production API smoke against `http://127.0.0.1:8000`:

```text
email=email-auth-off-481c93a285ea@example.com
account_id=4086d0e102574f719b2ca158911bebde
POST /api/auth/register -> 201
register response included session_token=true
register response included email_verification_artifact_id=false
GET /api/account/current-user -> 200
GET /api/account/access-status -> 200
access_allowed=true
email_verification_state=verified
denial_reason=null
POST /api/auth/login -> 200
POST /api/auth/password-reset/request -> 400
password reset error code=email_auth_disabled
```

Database confirmation for the same account:

```text
email-auth-off-481c93a285ea@example.com
credential_verified=t
email_verification_state=verified
access_allowed=t
denial_reason=
email_artifacts=0
```

Public API smoke through `https://coke.keep4oforever.com` with a browser user
agent:

```text
email=email-auth-off-public-aa2ec2288c@example.com
account_id=0d41425596b14361b5a8b64851e1a3b0
POST /api/auth/register -> 201
register response included email_verification_artifact_id=false
GET /api/account/access-status -> 200
access_allowed=true
email_verification_state=verified
denial_reason=null
```

Note: a Python default HTTP client user agent was blocked at the Cloudflare edge
with error 1010 `browser_signature_banned`. Retesting the same public API path
with a browser user agent passed.

Deploy-script follow-up:

- The first clean deploy returned successful health checks and deployed backend
  commit `33aded3b`, but `coke-web` was still the old 16-hour-old container.
- `coke-web` was force-recreated manually with the documented compose project,
  then `http://127.0.0.1:4042/auth/login` returned successfully.
- `scripts/deploy-compose-to-gcp.sh` was updated afterward to use explicit
  `backend`, `web`, and `full` remote branches so full deploys run web recreate
  in the same branch as backend deploy.
