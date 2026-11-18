# Put SeedReflections on your own domain (small Linux server)

Result: SeedReflections at `https://seedreflections.com`, with automatic HTTPS, nightly backups, and one command to update it from GitHub. SiteGround keeps the domain and DNS.

**Why not the GrowBig plan itself:** GrowBig is shared web hosting, built for PHP and WordPress. SeedReflections is a program that must run continuously and keep its own database and uploaded files, which shared hosting is not designed to do. Ask SiteGround support if you want it confirmed. SiteGround keeps your domain and DNS; a small server runs the app.

## 1. Before you start
- Merge the pull request that holds the latest work so the server follows `main` (or pass the branch name in step 4).
- You need: your SiteGround login, a GitHub account that can open the repository settings, and a card for the server.

## 2. Get a server (about US$6 to 12 a month)
Any of DigitalOcean, Linode (Akamai), Vultr or Hetzner. Choose **Ubuntu 24.04 LTS**, **2 GB RAM**, 40 GB disk, a US region, and add your SSH key (the provider explains how). Turn on the provider's automatic backups or snapshots; they protect you if the whole server is lost, which the nightly backups below cannot. Write down the server's IP address.

## 3. Point seedreflections.com at it (SiteGround)
SiteGround → **Site Tools** → **Domain** → **DNS Zone Editor**. Look at the existing records first.
- Replace the **A** record for `seedreflections.com` (the `@` or blank name) so its value is the server IP, TTL 3600. If there is an A record for `www`, point it at the same IP too (or make `www` a CNAME to `seedreflections.com`).
- **Do not delete MX, SPF or other mail records.** Those keep any `@seedreflections.com` mailbox working, including the one used for password-reset email.
- If a website currently lives at `seedreflections.com` on your GrowBig plan, it stops being served once this record changes. Move or copy anything you want to keep first.
- It can take from a few minutes to an hour to take effect. Visitors who type `www.` need that record to exist; the app itself is served at `seedreflections.com`.

## 4. Run the setup (once)
From your Windows PowerShell, in the `seedreflections` folder (use your server's IP):
```
scp deploy\setup-server.sh root@SERVER_IP:/root/
ssh root@SERVER_IP "bash /root/setup-server.sh seedreflections.com"
```
The first run installs Docker and the firewall, then prints a **deploy key**. In GitHub open the repository → **Settings → Deploy keys → Add deploy key**, paste it, leave write access off, and run the same `ssh` command again. It then downloads the code, creates `/opt/seedreflections/.env` with freshly generated secrets, starts the app, and sets up the nightly backup.

**Save a copy of `/opt/seedreflections/.env` somewhere safe** (for example with `scp root@SERVER_IP:/opt/seedreflections/.env .`). It holds the admin password and the encryption master key. Lose the key and stored model keys and Google tokens cannot be decrypted.

## 5. Set up the password-reset email
Users who forget a password get a reset link by email, so the server needs a mailbox to send from. In SiteGround: **Site Tools → Email → Accounts**, create `noreply@seedreflections.com`, then open **Mail Configuration → Manual Settings** and note the outgoing (SMTP) server. On the server, run the command below, replacing the host with the one SiteGround displays. It prompts for the mailbox password without echoing it, verifies SMTP login, saves the secret only in `/opt/seedreflections/.env`, validates Docker Compose's parsed value, and restarts the app. Never put the password on the command line or in chat.
```
sudo python3 /opt/seedreflections/deploy/configure-smtp.py --host YOUR_SITEGROUND_OUTGOING_SERVER --user noreply@seedreflections.com --from-address 'SeedReflections <noreply@seedreflections.com>'
```
Until SMTP is configured, the readiness check below fails on purpose. A passing readiness check means settings are present; also complete a real password reset to prove delivery.

## 6. Check it
Open `https://seedreflections.com` (the certificate is requested automatically; allow a minute after DNS works). Then:
```
curl -s https://seedreflections.com/api/v2/readiness
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
- To restore (try it once on a throwaway copy before you ever need it): `/opt/seedreflections/deploy/restore.sh /var/backups/seedreflections/<file>.tar.gz`. It takes a safety backup, stops the app, **checks the backup first** (nothing outside the data folder, no links, every database passes SQLite's integrity check), moves the current data aside into a `.before-restore-*` folder instead of deleting it, unpacks the backup, starts the app and checks it is healthy.

## Prove it works, from outside
From any computer with Python:
```
python scripts/journey_check.py https://seedreflections.com
```
It makes a throwaway account, imports a small made-up export, searches, reads, runs the review step and accepts a finding, saves and exports a work artifact, signs out and back in, confirms everything is still there, then deletes the account. Every step must pass. Run it after every update and before you trust the site with a real archive.

## Before you invite real people
- Have a Nevada attorney read the Privacy and Terms pages once. They were written from what the product does, not by a lawyer.
- Send yourself a password reset from the login page (Forgot?) and complete it, to confirm the email really arrives.
- Billing stays off until Stripe is configured. Google Drive stays off until you add the Google client id and secret to `.env` (see `docs/GOOGLE_DRIVE.md`), then run the update script.
- This is one server with one SQLite database: fine for early users, not for heavy traffic. Python's built-in web server is behind a proper HTTPS proxy, but it has not been load-tested.

## What is and is not proven
Tested here: the restore (a real backup of a running app restored into a fresh folder, the app then starts with its accounts and archive; unsafe, damaged and wrong backups are refused and change nothing), the release journey check against a configured hosted server, the sign-in and reset rate limits behind the proxy (each visitor limited separately, forged headers ignored), the backup (consistent while the app writes, restores correctly), the production settings (the app reports ready with these secrets and not ready without them), and that the scripts parse. **Not run:** the Docker build, the setup script on a real server, certificate issuance, and the update and rollback script. Expect to fix a snag or two on the first real deploy; send me the output and I will.
