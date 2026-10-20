# Deploying BizImprint on Oracle Cloud (Always Free)

One small Arm server in Sydney runs everything: the website, the check, Stripe payments, report PDFs and email.
Caddy serves it over HTTPS with a free certificate. Budget about an hour the first time.

What you need: a credit or debit card (for Oracle's identity check; nothing is charged within the free limits), your
domain (or use the free `sslip.io` address below until you have one), and your keys for IP Australia, Anthropic,
Stripe and Resend.

## 1. Create the Oracle account

1. Sign up at https://signup.cloud.oracle.com.
2. **Home region: Australia East (Sydney)** (or Australia Southeast (Melbourne)). Free servers only run in the home
   region and it can't be changed later. It also keeps customer data in Australia.
3. After sign-up, **upgrade to Pay As You Go**: menu > Billing & Cost Management > Upgrade and Manage Payment.
   Always Free resources stay free; the upgrade protects the server from being reclaimed when it looks idle (a new
   site with few visitors can).
4. Set a **budget alert**: Billing & Cost Management > Budgets > Create Budget, amount A$1, alert at 100%, your
   email. You'll hear about any charge immediately.

## 2. Create the server

Menu > Compute > Instances > **Create instance**:

| Setting | Choose |
|---|---|
| Name | `bizimprint` |
| Image | **Canonical Ubuntu 24.04** (Change image > Ubuntu) |
| Shape | Change shape > Ampere > **VM.Standard.A1.Flex**, **2 OCPUs, 12 GB memory** (shows "Always Free-eligible") |
| Networking | Create a new virtual cloud network and public subnet; **Assign a public IPv4 address: Yes** |
| SSH keys | **Generate a key pair for me** > **Save private key** (keep this file safe; it's the only way in) |
| Boot volume | Default (about 47 GB) is plenty |

Click Create. If it says **"Out of capacity"**, try again later or pick a different availability domain; free Arm
servers are popular.

When it's running, note the **Public IP address** on the instance page.

**Open the web ports in Oracle's network:** on the instance page click the subnet > the Default Security List >
Add Ingress Rules, twice:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(The setup script opens the same ports in the server's own firewall.)

## 3. Point your domain at the server

At your domain registrar, add an **A record**: name `@` (and `www` if you like), value = the public IP.

No domain yet? Use `<your IP with dashes>.sslip.io`, e.g. for 203.0.113.5 use `203-0-113-5.sslip.io`. It points at
your server without any setup and gets a proper HTTPS certificate. Switch to your own domain later by running the
setup again with it.

## 4. Connect from your PC

In Command Prompt (Windows has `ssh` built in), with the private key you saved:

```
ssh -i "C:\Users\saura\Downloads\ssh-key-2026-10-20.key" ubuntu@203.0.113.5
```

If Windows says the key is **unprotected**, fix its permissions once and try again:

```
icacls "C:\Users\saura\Downloads\ssh-key-2026-10-20.key" /inheritance:r /grant:r "%USERNAME%:R"
```

## 5. Run the setup

On the server:

```
curl -fsSL -o setup.sh https://raw.githubusercontent.com/successmeter/TM-Checker-and-advise/main/deploy/oracle/setup.sh
bash setup.sh bizimprint.com.au git@github.com:successmeter/TM-Checker-and-advise.git main
```

(The repository is private, so if the `curl` line fails, copy `deploy\oracle\setup.sh` from your PC instead:
`scp -i <key> deploy\oracle\setup.sh ubuntu@<IP>:` from the project folder.)

Part way through it prints a **deploy key** and waits. Add it in GitHub: the repository > Settings > Deploy keys >
Add deploy key, paste it, leave **Allow write access** off, save, then press Enter on the server. The server can then
read the code but never change it.

The script installs Python, the app, Chromium for PDFs and Caddy for HTTPS; opens the firewall; creates the service
(it starts on boot and restarts if it stops); and sets up daily backups. It's safe to run again.

## 6. Add your keys

```
sudo nano /etc/bizimprint.env
```

Fill in IP Australia, Anthropic, Stripe and Resend (each line is explained in the file). `TM_PUBLIC_URL` and
`TM_SECRET` are already filled in. Save with Ctrl+O, Enter, Ctrl+X, then:

```
sudo systemctl restart bizimprint
sudo journalctl -u bizimprint -n 30
```

Look for `Payments: on (Stripe test mode).` The file is readable only by root and the app; never paste keys into
chat, code or GitHub.

## 7. Copy the large data files from your PC

The full goods and services list and the Trade Marks Manual index are built on your PC and aren't in GitHub. From
the project folder on your PC:

```
scp -i <key> data\picklist.json data\register_wording.json ubuntu@<IP>:/tmp/
scp -i <key> -r data\manual ubuntu@<IP>:/tmp/
```

Then on the server:

```
sudo mv /tmp/picklist.json /tmp/register_wording.json /opt/bizimprint/app/data/
sudo rm -rf /opt/bizimprint/app/data/manual && sudo mv /tmp/manual /opt/bizimprint/app/data/
sudo chown -R bizimprint:bizimprint /opt/bizimprint/app/data
```

(Skip any file you don't have; the server downloads missing data by itself over the following hours.)

## 8. Stripe webhook

Stripe dashboard (Test mode first) > Developers > Webhooks > **Add endpoint**:

- URL: `https://<your domain>/api/stripe/webhook`
- Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `charge.refunded`

Copy its **signing secret** (`whsec_...`) into `STRIPE_WEBHOOK_SECRET` in `/etc/bizimprint.env` and restart. (The
report page also confirms payments with Stripe directly, so a missed webhook doesn't strand an order.)

## 9. Test

Open `https://<your domain>`, run a check, order a report with card `4242 4242 4242 4242`, and confirm the report
appears and the email arrives. On the server, `bizimprint orders list` shows the order (the same as
`py -m tm_advisor.orders list` on your PC).

## Day to day

| Task | Command (on the server) |
|---|---|
| Deploy the latest code from GitHub | `bash /opt/bizimprint/app/deploy/oracle/update.sh` |
| See recent log messages | `sudo journalctl -u bizimprint -n 100` |
| Follow the log live | `sudo journalctl -u bizimprint -f` |
| Restart | `sudo systemctl restart bizimprint` |
| Orders, report links, approvals | `bizimprint orders list`, `bizimprint orders link BI-…`, `bizimprint orders approve BI-…` |
| Check IP Australia access | `bizimprint register "BizImprint" --class 42` |
| Backups | `/opt/bizimprint/backups` (daily, 14 days). Copy them off the server now and then: `scp -i <key> -r ubuntu@<IP>:/opt/bizimprint/backups .` |
| Security updates | `sudo apt update && sudo apt upgrade -y` monthly |

Oracle also offers boot volume backups (Block Storage > Boot Volumes > your volume > Create backup); a few are
included in the free tier, which is a good safety net before big changes.

## Going live

1. In `/etc/bizimprint.env`, switch to Stripe **live** keys and a live webhook endpoint (step 8 in Live mode).
2. Verify your sending domain in Resend and set `TM_EMAIL_FROM` to an address on it.
3. Check the IP Australia credentials are for the production register (leave `IPA_BASE_URL` unset).
4. Consider `TM_REVIEW_REPORTS=1` for the first customers, so you see each report before it's emailed
   (`bizimprint orders approve <order>` releases it).
