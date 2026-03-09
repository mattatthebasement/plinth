# Plinth POC — Predevelopment Checklist (Mac Mini)

> Everything that must be in place before writing a line of code.
> Checked items are prerequisites. Unchecked items are tasks.
> **Test address:** 11822 E 116th St N, Collinsville, OK 74021
> **Test coordinate:** 36.32197414685, -95.842032856739

---

## 1. Hardware

### 1.1 Procure the Mac Mini

**Recommended spec (single machine, runs everything):**

| Component | Spec | Notes |
|---|---|---|
| **Model** | Mac Mini M4 Pro | 12-core CPU, 48 GB unified memory |
| **RAM** | 48 GB unified memory | M4 Pro max; 24 GB workable for regional POC |
| **Internal SSD** | 512 GB – 1 TB | OS + Docker volumes + PostgreSQL data |
| **External storage** | 4 TB USB4 / Thunderbolt HDD or SSD | MinIO object storage — see §2.2 |
| **Network** | Gigabit Ethernet (built-in) | Wired only — raster downloads are large |
| **OS** | macOS Sequoia (15.x) | Standard install; no special server OS needed |

> **Why Mac Mini:** Apple Silicon is power-efficient (running 24/7), macOS is stable as a server OS, and the M4 Pro's memory bandwidth handles spatial queries well. At ~$1,400 for the 48 GB / 12-core config, it beats a used Dell PowerEdge on noise, power, and thermal simplicity.
>
> **Storage note:** The Mac Mini has no internal expansion bays. MinIO raster data lives on an external drive connected via Thunderbolt 4 / USB4. A 4 TB spinning HDD (~$80) is fine for sequential raster reads; a 4 TB portable SSD is faster but more expensive.

- [ ] Mac Mini procured (M4 Pro, 48 GB RAM recommended)
- [ ] External 4 TB drive procured and formatted (see §2.2)
- [ ] Static IP assigned on local network (or DHCP reservation in your router — note the IP, you'll use it constantly)
- [ ] Mac Mini reachable via SSH from your workstation (see §2.1)

---

## 2. Server Configuration

### 2.1 Enable Remote Login (SSH)

macOS ships with SSH but it's disabled by default. Enable it once in System Settings — after that you SSH in like any Linux machine.

```
System Settings → General → Sharing → Remote Login → Enable
```

Restrict access to specific users only (uncheck "All users", add your admin user). Then from your workstation:

```bash
# Copy your SSH public key to the Mac Mini (first-time setup)
ssh-copy-id plinth@192.168.x.x

# Harden: disable password auth (after confirming key login works)
# Edit /etc/ssh/sshd_config on the Mac Mini:
#   PasswordAuthentication no
#   PubkeyAuthentication yes
sudo launchctl stop com.openssh.sshd
sudo launchctl start com.openssh.sshd
```

> macOS doesn't have `sshd_config` at the standard path by default. The file is at `/etc/ssh/sshd_config`. Changes take effect after restarting the SSH daemon via launchctl.

- [ ] Remote Login enabled in System Settings → Sharing
- [ ] SSH key-based auth working from workstation
- [ ] Password auth disabled in `/etc/ssh/sshd_config`
- [ ] Mac Mini reachable: `ssh plinth@192.168.x.x` succeeds without password

### 2.2 External Storage Setup

Format and configure the external drive. macOS uses APFS by default, which works fine. For maximum Linux/Docker compatibility, APFS is preferred over exFAT.

**Format the drive (macOS Disk Utility):**
1. Open **Disk Utility**
2. Select the external drive → **Erase**
3. Name: `plinth_data`, Format: **APFS**, Scheme: **GUID Partition Map**
4. Click **Erase**

The drive will automount at `/Volumes/plinth_data` when connected. However, on a headless Mac Mini, external drives don't always automount reliably at boot — the drive may enumerate after macOS finishes booting. The launchd agent in §4 handles this with an explicit `diskutil mount "plinth_data"` call (mounting by volume name is the most reliable approach — no UUID hunting needed).

Create the MinIO data directory on the drive. Then use `/etc/synthetic.conf` to create `/data` at the root level — macOS has had a read-only root filesystem since Catalina, so `mkdir /data` will fail. `synthetic.conf` is the Apple-supported way to create root-level paths that survive reboots.

```bash
# Create the directory MinIO will use on the external drive
sudo mkdir -p /Volumes/plinth_data/minio
sudo chown -R $(whoami):staff /Volumes/plinth_data/minio

# Create /etc/synthetic.conf to establish /data as a root-level firmlink
# Format: <name><TAB><target>  (must be a literal tab, not spaces)
echo -e "data\t/Volumes/plinth_data" | sudo tee /etc/synthetic.conf

# Reboot for the firmlink to take effect — macOS creates it at boot time
sudo reboot
```

After rebooting, `/data` will exist as a firmlink pointing to `/Volumes/plinth_data`. If the external drive didn't auto-mount, mount it manually by volume name:

```bash
# Mount manually if needed
diskutil mount "plinth_data"

# Verify
ls /data/minio      # should exist
df -h /data/minio   # should show the external drive
```

> **Why not a symlink:** `ln -s` from inside `/` fails for the same reason — the root volume is read-only. `synthetic.conf` is how Apple intends this to be done; Docker, Homebrew, and other tools use this same mechanism.
>
> **Why drives don't always auto-mount at boot:** External drives may enumerate after macOS finishes its boot sequence, particularly with some USB/Thunderbolt enclosures. The launchd agent in §4 handles this with an explicit `diskutil mount "plinth_data"` call before starting Docker Compose.

- [ ] External drive formatted APFS as `plinth_data`
- [ ] `/Volumes/plinth_data/minio` directory created with correct ownership
- [ ] `/etc/synthetic.conf` entry added (`data → /Volumes/plinth_data`); Mac Mini rebooted; `/data` firmlink exists at root
- [ ] Confirm: `df -h /data/minio` shows the external drive with available space

### 2.3 Firewall Configuration

macOS has two firewall layers:

1. **Application Firewall** (System Settings → Network → Firewall) — blocks inbound connections by application. Enable this and allow Docker.
2. **pf (packet filter)** — macOS's BSD packet filter, used for subnet-level port control if needed.

For a home/office LAN setup where the Mac Mini is behind a router, enabling the application firewall is usually sufficient. The services (PostgreSQL, MinIO, Prefect, FastAPI) run inside Docker and are only bound to the local interface unless you explicitly expose them.

```bash
# Verify the application firewall is on
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
# Enable if not on:
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on

# Add Docker to the allowed list (macOS may prompt automatically)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /Applications/Docker.app
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /Applications/Docker.app
```

If you want subnet-level port filtering (equivalent to UFW), use pf:

```bash
# /etc/pf.anchors/plinth — create this file with:
# pass in inet proto tcp from 192.168.1.0/24 to any port {5432, 9000, 9001, 4200, 8000}
# block in inet proto tcp to any port {5432, 9000, 9001, 4200, 8000}

# Then reference it in /etc/pf.conf and reload:
sudo pfctl -f /etc/pf.conf
sudo pfctl -e
```

- [ ] macOS Application Firewall enabled
- [ ] Docker allowed through the application firewall
- [ ] (Optional) pf rules configured for subnet-level port filtering

---

## 3. Software Installation on the Server

### 3.1 Homebrew

Homebrew is the package manager for macOS. Install it first — everything else in this section uses it.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Apple Silicon: add brew to PATH (add to ~/.zprofile)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# Verify
brew --version
```

- [ ] Homebrew installed
- [ ] `brew --version` succeeds
- [ ] `brew` is on PATH (check: `which brew` returns `/opt/homebrew/bin/brew`)

### 3.2 Docker (OrbStack)

On macOS, Docker runs inside a lightweight Linux VM. Use **OrbStack** — it starts in ~2 seconds, uses less RAM and CPU at idle than Docker Desktop, and has better bind-mount I/O performance for the PostgreSQL data directory and MinIO raster files. It's a drop-in replacement with the same `docker` and `docker compose` CLI. Free for personal/hobby use.

```bash
brew install orbstack
# Or download from orbstack.dev

# Launch OrbStack.app once to complete initial setup, then it runs in the menu bar
open -a OrbStack
```

```bash
# Verify
docker --version          # expect 25.x or later
docker compose version    # expect v2.x
```

- [ ] OrbStack installed and running (menu bar icon visible)
- [ ] `docker --version` succeeds
- [ ] `docker compose version` succeeds (expect v2.x)
- [ ] `docker run hello-world` succeeds without sudo

### 3.3 GDAL & Geospatial System Libraries

On macOS, install GDAL and spatial libraries via Homebrew. These are needed on the host for CLI use; the worker container also installs its own GDAL copy.

```bash
brew install gdal \
  geos \
  proj \
  spatialindex \
  sqlite \
  wget \
  git \
  jq \
  htop \
  ncdu \
  tmux
```

> **Apple Silicon note:** Homebrew GDAL on ARM64 compiles natively for M-series chips. This is the version your terminal uses. The Docker containers run under Rosetta 2 or arm64 depending on the base image — the worker Dockerfile handles that separately.

- [ ] `gdal` installed via Homebrew — verify: `gdalinfo --version` (expect GDAL 3.x)
- [ ] `libspatialindex` installed (required by Rtree / shapely)
- [ ] Support tools installed: `wget`, `curl`, `jq`, `tmux`

### 3.4 uv (Python Package Manager)

uv is used on the host to run CLI commands during development. It is also installed inside the worker container via the Dockerfile.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

# Restart shell or source the env:
source $HOME/.local/bin/env

# Verify
uv --version
```

- [ ] `uv` installed
- [ ] `uv --version` succeeds

### 3.5 Git & Xcode Command Line Tools

Git on macOS is provided by Xcode Command Line Tools. It may already be installed; if not, macOS will prompt you automatically the first time you run `git`.

```bash
# Trigger install if needed
git --version
# macOS will offer to install Xcode CLT if not present

# Configure identity
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

- [ ] Git installed and configured

---

## 4. Auto-Start on Boot

Unlike Linux/systemd, macOS uses **launchd** for boot-time automation. We use a **LaunchDaemon** (runs at boot as root, before any user login) rather than a LaunchAgent (runs at user login only). This means the stack starts automatically after a power cycle without requiring anyone to log in at the console — important for a headless server.

> OrbStack installs its own LaunchDaemon that starts its Linux VM at boot when "Launch at Login" is enabled. You do **not** need auto-login enabled.

### 4.1 OrbStack at Login

```
OrbStack preferences → General → Launch OrbStack at login ✓
```

### 4.2 LaunchDaemon for Drive Mount + Compose

Create `/Library/LaunchDaemons/com.plinth.stack.plist` (requires sudo — note this is `/Library`, not `~/Library`):

```bash
sudo tee /Library/LaunchDaemons/com.plinth.stack.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.plinth.stack</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>sleep 60 &amp;&amp; /usr/sbin/diskutil mount plinth_data &amp;&amp; sleep 10 &amp;&amp; cd /Users/YOUR_USERNAME/projects/plinth &amp;&amp; /opt/homebrew/bin/docker compose up -d</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/plinth-stack.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/plinth-stack-error.log</string>
</dict>
</plist>
EOF

# LaunchDaemons must be owned by root:wheel
sudo chown root:wheel /Library/LaunchDaemons/com.plinth.stack.plist
sudo chmod 644 /Library/LaunchDaemons/com.plinth.stack.plist

# Load it (takes effect immediately and on every subsequent boot)
sudo launchctl load /Library/LaunchDaemons/com.plinth.stack.plist
```

> `sleep 60` gives OrbStack's Linux VM time to fully start. Full path `/usr/sbin/diskutil` is required because LaunchDaemons run with a minimal PATH. Logs go to `/var/log/` so they persist across reboots. **Replace `YOUR_USERNAME` with your actual macOS username** (`whoami` will tell you).

**Check logs after a reboot:**
```bash
cat /var/log/plinth-stack.log
cat /var/log/plinth-stack-error.log
```

**Reload after editing the plist:**
```bash
sudo launchctl unload /Library/LaunchDaemons/com.plinth.stack.plist
sudo launchctl load /Library/LaunchDaemons/com.plinth.stack.plist
```

- [ ] OrbStack "Launch at Login" enabled
- [ ] `/Library/LaunchDaemons/com.plinth.stack.plist` created, owned `root:wheel`, loaded
- [ ] Reboot test: `docker compose ps` shows all services running after ~90 seconds (check logs if not)
- [ ] macOS System Settings → Energy → **Prevent automatic sleeping when the display is off** ✓ (critical for a server)
- [ ] macOS System Settings → Energy → **Start up automatically after a power failure** ✓

---

## 5. Repository

- [ ] GitHub repository created for `plinth` (private)
- [ ] Repository cloned to the Mac Mini at `~/projects/plinth`
- [ ] SSH deploy key or personal access token configured for Mac Mini → GitHub push/pull

**Suggested clone location:** `/Users/plinth/projects/plinth`

---

## 6. API Keys & Accounts

All free-tier. None require a credit card for POC usage volumes.

### 6.1 Mapbox

Used for: **geocoding** (address → lat/lon) and **static map images** in reports.

1. Create account at [account.mapbox.com](https://account.mapbox.com)
2. Create a new **public access token** (default scopes are sufficient for static images + geocoding)
3. Note the token — it starts with `pk.`

> **Free tier:** 100,000 static image requests/month and 100,000 geocoding requests/month. Well above POC needs.

- [ ] Mapbox account created
- [ ] Public access token created and saved securely
- [ ] Token added to `.env` as `MAPBOX_TOKEN=pk.eyJ1...`

### 6.2 US Census Bureau API Key

Used for: **ACS 5-year demographic data** (population, income, housing, age) fetched at query time.

1. Register at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)
2. Key is emailed instantly — no approval process

- [ ] Census API key obtained
- [ ] Key added to `.env` as `CENSUS_API_KEY=...`

### 6.3 EPA AQS API Key

Used for: **Air quality** — annual PM2.5 and ozone monitor data.

1. Register at [aqs.epa.gov/aqsweb/documents/data_api.html#signup](https://aqs.epa.gov/aqsweb/documents/data_api.html#signup) — email your address to `aqsdatamart@epa.gov` with subject "AQS Data Mart account"
2. Key arrives by email, typically within 1 business day

- [ ] EPA AQS API key requested
- [ ] EPA AQS API key received and added to `.env` as `EPA_AQS_KEY=...` and `EPA_AQS_EMAIL=...`

### 6.4 No Other Keys Required for Phase 1

| Source | Access Method | Credentials |
|---|---|---|
| FEMA NFHL | Direct download | None |
| USGS 3DEP | Direct download / National Map | None |
| USDA SSURGO | Direct download | None |
| NLCD | Direct download | None |
| NHDPlus HR | Direct download | None |
| IECC Climate Zones | Direct download | None |
| FEMA NRI | Direct download | None |
| USGS Seismic Hazard | Direct download | None |
| USDA Wildfire Hazard Potential | Direct download | None |
| NOAA Climate Normals | Direct download | None |
| NASA POWER | Public API | None |
| USGS Earthquake Catalog | Public API | None |
| FCC Broadband | Public API | None (key optional, rate limits relaxed with key) |

---

## 7. Developer Workstation Setup

If you're developing on a separate Mac (laptop/desktop), set it up for remote work on the Mac Mini. If the Mac Mini **is** your workstation, skip §7.1 and install the tools in §7.2 locally.

### 7.1 Remote Development (separate machine)

- [ ] SSH config entry for the Mac Mini:
  ```
  Host plinth-server
      HostName 192.168.x.x       # your Mac Mini's IP
      User plinth
      IdentityFile ~/.ssh/id_ed25519
  ```
- [ ] **VS Code** with **Remote - SSH** extension installed (develop directly on the Mac Mini over SSH)
- [ ] `git` installed locally

### 7.2 Recommended Tools (install on your workstation)

- [ ] **TablePlus** or **DBeaver** — GUI PostgreSQL client for inspecting spatial data:
  ```bash
  brew install --cask tableplus
  # or
  brew install --cask dbeaver-community
  ```
- [ ] **QGIS** — desktop GIS for visually validating loaded spatial datasets (free, invaluable for debugging flood zones, soil units, etc.):
  ```bash
  brew install --cask qgis
  ```
- [ ] **MinIO Client (`mc`)** — CLI for browsing MinIO buckets:
  ```bash
  brew install minio/stable/mc
  ```

---

## 8. Pre-Flight Verification

Run these checks after all setup is complete, before starting Phase 0 code work.

### 8.1 Mac Mini Health

```bash
# From the Mac Mini (SSH in or open Terminal)
docker compose version          # should print v2.x
docker context use orbstack     # ensure OrbStack context is active
gdalinfo --version              # should print GDAL 3.x
uv --version                    # should print uv x.x.x
ls -la /data/minio              # should resolve firmlink to /Volumes/plinth_data/minio
df -h /data/minio               # should show the external drive
sysctl -n hw.memsize | awk '{print $1/1073741824 " GB"}'   # verify RAM
sysctl -n hw.logicalcpu                                     # verify core count
```

> **OrbStack context:** OrbStack uses its own Docker context. If `docker` commands fail with "Cannot connect to Docker daemon", run `docker context use orbstack`. Add `echo 'docker context use orbstack > /dev/null 2>&1' >> ~/.zprofile` to make it permanent.

### 8.2 External Drive Persistence Check

Reboot the Mac Mini and verify:

```bash
# After reboot, mount manually if needed (the launchd agent does this automatically)
diskutil mount "plinth_data"

# Confirm drive mounted and firmlink resolves
ls /Volumes/plinth_data     # should exist
ls /data/minio              # should exist (firmlink → /Volumes/plinth_data/minio)
df -h /data/minio           # should show drive stats
```

### 8.3 Docker Stack Verification

```bash
cd ~/projects/plinth
docker compose up -d
docker compose ps -a    # all 4 containers should be healthy/running after ~60 seconds
```

Expected output:
| Container | Status |
|---|---|
| `plinth-postgres-1` | `healthy` |
| `plinth-minio-1` | `healthy` |
| `plinth-prefect-server-1` | `healthy` |
| `plinth-prefect-worker-1` | `Up` |

Then verify the UIs are reachable from your workstation browser:
- **MinIO Console:** `http://192.168.86.41:9001`
- **Prefect UI:** `http://192.168.86.41:4200`

> **ARM64 notes:**
> - `postgis/postgis:15-3.4` has no arm64 image — use `imresamu/postgis:15-3.4-alpine` instead (already set in `docker-compose.yml`)
> - `prefecthq/prefect:3-latest` has arm64 but no `curl` — the healthcheck uses Python's `urllib` instead
> - The Prefect image is amd64 emulated under Rosetta — add `start_period: 30s` to its healthcheck to allow for slower startup

### 8.3 API Key Smoke Tests

```bash
# Mapbox geocoding (replace YOUR_TOKEN)
curl "https://api.mapbox.com/geocoding/v5/mapbox.places/11822%20E%20116th%20St%20N%2C%20Collinsville%2C%20OK.json?access_token=YOUR_TOKEN" \
  | jq '.features[0].geometry.coordinates'
# Expected: [-95.842..., 36.321...]

# Census API (replace YOUR_KEY)
curl "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01001_001E&for=state:40&key=YOUR_KEY" | jq .
# Expected: Oklahoma population data

# EPA AQS (replace YOUR_EMAIL and YOUR_KEY)
curl "https://aqs.epa.gov/aqsweb/documents/data_api.html/signup?email=YOUR_EMAIL" | jq .
# Or test with: /list/states?email=...&key=...

# NASA POWER (no key required)
curl "https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=T2M&community=RE&longitude=-95.842&latitude=36.322&format=JSON" \
  | jq '.properties.parameter.T2M' | head -5
# Expected: monthly temperature values
```

### 8.4 Test Coordinate Reference

| | Value |
|---|---|
| **Address** | 11822 E 116th St N, Collinsville, OK 74021 |
| **Latitude** | 36.321538750979826 |
| **Longitude** | -95.84200527573135 |
| **County** | Tulsa County, OK |
| **State** | Oklahoma (FIPS 40) |
| **NHDPlus VPU** | 11 (Arkansas-White-Red) |
| **SSURGO** | Oklahoma state .gdb |
| **Expected IECC Zone** | 3A (Warm Humid) — verify against DOE lookup |

Keep this coordinate as the canonical test input throughout development. Every query function, ingestion validator, and end-to-end test uses it.

---

## 9. Credentials Management

For the POC, credentials live in `.env` at the project root. **`.env` is in `.gitignore` and never committed.**

`.env.example` (committed to repo) documents every required variable with placeholder values. Before first run:

```bash
cp .env.example .env
# Fill in real values in .env
```

Sensitive variables to keep in `.env`:
- `MAPBOX_TOKEN`
- `CENSUS_API_KEY`
- `EPA_AQS_KEY` / `EPA_AQS_EMAIL`
- `POSTGRES_PASSWORD`
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`

---

## 10. Summary Checklist

### Hardware
- [ ] Mac Mini M4 Pro procured (48 GB RAM recommended)
- [ ] External 4 TB drive procured and formatted APFS as `plinth_data`
- [ ] Static IP / DHCP reservation assigned on local network

### Server Setup
- [ ] Remote Login (SSH) enabled, key-based auth configured
- [ ] macOS Application Firewall enabled, Docker allowed
- [ ] External drive formatted APFS as `plinth_data`; UUID recorded; `/data` firmlink created via `/etc/synthetic.conf`
- [ ] Homebrew installed
- [ ] OrbStack installed; configured to launch at login
- [ ] GDAL + spatial libraries installed via Homebrew
- [ ] `uv` installed
- [ ] Git installed and configured
- [ ] macOS Energy settings: auto-sleep disabled, restart after power failure enabled

### Accounts & Keys
- [ ] Mapbox account + token
- [ ] Census API key
- [ ] EPA AQS API key (allow 1 business day)

### Repository
- [ ] GitHub repo created
- [ ] Repo cloned to Mac Mini

### Workstation
- [ ] SSH config entry for Mac Mini
- [ ] VS Code + Remote SSH extension (if developing remotely)
- [ ] QGIS installed (for dataset validation)
- [ ] TablePlus or DBeaver installed

### Verification
- [ ] All API smoke tests pass
- [ ] Docker, GDAL, uv all report correct versions
- [ ] `/data/minio` symlink resolves and shows external drive space
- [ ] Reboot test: drive auto-mounts, Docker starts, symlink intact
