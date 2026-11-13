# Put SeedReflections on your own domain (small Linux server)

Result: SeedReflections at `https://app.asolutiongroup.com` (or any subdomain you choose), with automatic HTTPS, nightly backups, and one command to update it from GitHub. Your existing SiteGround website stays exactly as it is.

**Why not the GrowBig plan itself:** GrowBig is shared web hosting, built for PHP and WordPress. SeedReflections is a program that must run continuously and keep its own database and uploaded files, which shared hosting is not designed to do. Ask SiteGround support if you want it confirmed. SiteGround keeps your domain and DNS; a small server runs the app.

## 1. Before you start
- Merge the pull request that holds the latest work so the server follows `main` (or pass the branch name in step 4).
- You need: your SiteGround login, a GitHub account that can open the repository settings, and a card for the server.

## 2. Get a server (about US$6 to 12 a month)
Any of DigitalOcean, Linode (Akamai), Vultr or Hetzner. Choose **Ubuntu 24.04 LTS**, **2 GB RAM**, 40 GB disk, a US region, and add your SSH key (the provider explains how). Turn on the provider's automatic backups or snapshots; they protect you if the whole server is lost, which the nightly backups below cannot. Write down the server's IP address.

## 3. Point a subdomain at it (SiteGround)
SiteGround → **Site Tools** → **Domain** → **DNS Zone Editor** → add an **A** record: Name `app`, Value = the server IP, TTL 3600. Do not change any existing records. It can take from a few minutes to an hour to take effect. (If your domain's name servers are not SiteGround's, add the record wherever the DNS is managed.)

## 4. Run the setup (once)
From your Windows PowerShell, in the `seedreflections` folder (use your server's IP):
```
scp deploy\setup-server.sh root@SERVER_IP:/root/
ssh root@SERVER_IP "bash /root/setup-server.sh app.asolutiongroup.com"
```
The first run installs Docker and the firewall, then prints a **deploy key**. In GitHub open the repository → **Settings → Deploy keys → Add deploy key**, paste it, leave write access off, and run the same `ssh` command again. It then downloads the code, creates `/opt/seedreflections/.env` with freshly generated secrets, starts the app, and sets up the nightly backup.

**Save a copy of `/opt/seedreflections/.env` somewhere safe** (for example with `scp root@SERVER_IP:/opt/seedreflections/.env .`). It holds the admin password and the encryption master key. Lose the key and stored model keys and Google tokens cannot be decrypted.

## 5. Set up the password-reset email
Users who forget a password get a reset link by email, so the server needs a mailbox to send from. In SiteGround: **Site Tools → Email → Accounts**, create `noreply@asolutiongroup.com`, then open **Mail Configuration** and note the outgoing (SMTP) server and port. On the server, edit `/opt/seedreflections/.env`: fill the `SEED_REFLECTIONS_SMTP_` lines (host, port 465 with security `ssl`, the mailbox address as user and from, its password), then run `cd /opt/seedreflections && docker compose -f docker-compose.prod.yml up -d`. Until this is filled in, the readiness check below fails on purpose.

## 6. Check it
Open `https://app.asolutiongroup.com` (the certificate is requested automatically; allow a minute after DNS works). Then:
```
curl -s https://app.asolutiongroup.com/api/v2/readiness
```
Every check should pass. Create your own account, import something small, and try Settings → Delete account on a throwaway account.

## 7. Update it whenever the code changes
```
ssh root@SERVER_IP /opt/seedreflections/deploy/update.sh
```
It backs up first, pulls the latest code from GitHub, rebuilds, checks that the app starts, and rolls back to the previous version if it does not.

## 8. Backups and restoring
- Nightly at 03:15 into `/var/backups/seedreflections` (30 days kept), and before every update. Each is a single `.tar.gz` of the databases and uploaded source files.
- Those copies sit on the same server. Keep the provider's snapshots on, and occasionally copy one off the server: `scp root@SERVER_IP:/var/backups/seedreflections/<file> .`
- To restore: stop the app (`docker compose -f docker-compose.prod.yml down` in `/opt/seedreflections`), unpack the `.tar.gz` into the data volume, and start it again. Try a restore once before you depend on it.

## Before you invite real people
- Have a Nevada attorney read the Privacy and Terms pages once. They were written from what the product does, not by a lawyer.
- Send yourself a password reset from the login page (Forgot?) and complete it, to confirm the email really arrives.
- Billing stays off until Stripe is configured. Google Drive stays off until you add the Google client id and secret to `.env` (see `docs/GOOGLE_DRIVE.md`), then run the update script.
- This is one server with one SQLite database: fine for early users, not for heavy traffic. Python's built-in web server is behind a proper HTTPS proxy, but it has not been load-tested.

## What is and is not proven
Tested here: the sign-in and reset rate limits behind the proxy (each visitor limited separately, forged headers ignored), the backup (consistent while the app writes, restores correctly), the production settings (the app reports ready with these secrets and not ready without them), and that the scripts parse. **Not run:** the Docker build, the setup script on a real server, certificate issuance, and the update and rollback script. Expect to fix a snag or two on the first real deploy; send me the output and I will.
