# Local Docker secrets

Docker Compose supplies the provider API key to the worker and Grafana's admin password to Grafana as mounted files.
The project does not need a `.env` file for passwords or API keys; `.env` remains available for ordinary settings.

1. Create the local secret files from the examples:

   ```powershell
   Copy-Item secrets/llm_api_key.example secrets/llm_api_key.txt
   Copy-Item secrets/grafana_admin_password.example secrets/grafana_admin_password.txt
   ```

2. Replace the example text in `secrets/llm_api_key.txt` with your provider key. Choose a private password in
   `secrets/grafana_admin_password.txt`.
3. Start the stack with `docker compose up --build`.

The `.txt` files are ignored by Git and excluded from the Docker build context. Compose mounts the key only into the
worker at `/run/secrets/llm_api_key` and the Grafana password at `/run/secrets/grafana_admin_password`. The app reads
the provider key from the mounted file. Grafana reads its password from its mounted file.

Compose file-backed secrets are useful for local development, but the original files still live unencrypted on your
computer. Keep them private. For a deployed Swarm, create secrets with `docker secret create`; for a cloud deployment,
use its secret manager. Do not commit real secret files.

The Compose stack publishes its web and monitoring ports on `127.0.0.1` only, so other machines on your network
cannot access the unauthenticated demo endpoints. Keep this local-only setup for trusted development; a shared
deployment needs application authentication and access controls.

For the load-test overlay, the fake LLM service does not need a real provider key, but Compose still needs both secret
files because they are declared by the base stack.
