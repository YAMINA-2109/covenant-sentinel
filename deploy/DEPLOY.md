# Deploying on a Vultr VM (single process)

The backend serves both the API and the pre-built frontend (`frontend/dist`,
committed), so the server needs **Python only**.

1. In the Vultr customer portal: **Deploy → Cloud Compute → Ubuntu 24.04**,
   smallest plan is fine (1 vCPU / 1 GB). Note the public IP.
2. SSH in as root and run:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/YAMINA-2109/covenant-sentinel/main/deploy/vultr_setup.sh | bash
   ```

3. The first run stops and asks for the key:

   ```bash
   nano /opt/covenant-sentinel/backend/.env   # set VULTR_API_KEY
   bash /opt/covenant-sentinel/deploy/vultr_setup.sh
   ```

4. Open `http://<VM-IP>/` — click **Run the ACME demo case**.

Operations: `systemctl status|restart covenantsentinel` · logs:
`journalctl -u covenantsentinel -f` · redeploy after a push: re-run the script.
