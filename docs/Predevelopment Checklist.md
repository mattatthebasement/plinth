# Plinth POC — Predevelopment Checklist

> ⚠️ **This checklist is for Ubuntu 24.04 LTS servers.** If you're using a Mac Mini or macOS, see `Predevelopment Checklist - Mac.md` instead.

> Everything that must be in place before writing a line of code.
> Checked items are prerequisites. Unchecked items are tasks.
> **Test address:** 11822 E 116th St N, Collinsville, OK 74021
> **Test coordinate:** 36.32197414685, -95.842032856739

---

## 1. Hardware

### 1.1 Procure the Server

**Recommended spec (single machine, runs everything):**

| Component | Spec | Notes |
|---|---|---|
| **CPU** | 12–16 cores | AMD Ryzen 9 / Threadripper, or dual-socket Xeon (used server) |
| **RAM** | 64 GB DDR4 | 32 GB is workable for regional POC; 64 GB headroom for national |
| **Boot / OS drive** | 1 TB NVMe SSD | OS + Docker volumes + PostgreSQL data |
| **Raster storage** | 4 TB HDD (SATA) | MinIO object storage — mount separately at `/data/minio` |
| **Network** | Gigabit Ethernet | Wired only — raster downloads are large |
| **OS** | Ubuntu 24.04 LTS | Fresh install; server profile (no GUI) |

**Best value:** Used Dell PowerEdge R730 or HPE DL380 Gen9 — enterprise DDR4, hot-swap bays, dual-socket Xeon. Expect $600–900 on eBay for a 64 GB / 12-core / 4 TB config. Verify iDRAC/iLO remote management works (saves you a monitor trip for server issues).

- [ ] Server hardware procured
- [ ] Ubuntu 24.04 LTS Server installed (fresh, no GUI)
- [ ] Static IP assigned on local network (or DHCP reservation — note the IP, you'll use it constantly)
- [ ] Server reachable via SSH from your workstation

---

## 2. Server Configuration

### 2.1 Base OS Setup

SSH in as a non-root sudo user (or create one — don't run everything as root).

```bash
# Create a non-root user if needed
adduser plinth
usermod -aG sudo plinth

# Harden SSH — disable password auth, use key only
# Edit /etc/ssh/sshd_config:
#   PasswordAuthentication no
#   PubkeyAuthentication yes
sudo systemctl restart ssh

# Basic firewall
sudo ufw allow OpenSSH
sudo ufw enable
```

- [ ] Non-root sudo user created
- [ ] SSH key-based auth configured (password auth disabled)
- [ ] UFW firewall enabled with SSH allowed

### 2.2 Storage Setup

The HDD needs to be formatted, mounted, and set to auto-mount on boot. MinIO data lives here.

```bash
# Find the disk (replace sdX with your disk)
lsblk

# Format (WARNING: destructive — only on new/empty disk)
sudo mkfs.ext4 /dev/sdX

# Create mount point and mount
sudo mkdir -p /data/minio
sudo mount /dev/sdX /data/minio

# Make it permanent — add to /etc/fstab
# Get the UUID:
sudo blkid /dev/sdX
# Add this line to /etc/fstab:
# UUID=<your-uuid>  /data/minio  ext4  defaults  0  2

# Set permissions
sudo chown -R 1000:1000 /data/minio
```

- [ ] HDD formatted as ext4
- [ ] Mounted at `/data/minio`
- [ ] Mount added to `/etc/fstab` (survives reboot)
- [ ] Confirm disk is visible: `df -h /data/minio`

### 2.3 Open Internal Ports (UFW)

These services should be reachable from your local network only — **not** exposed to the internet.

```bash
# Allow from your local subnet only (e.g., 192.168.1.0/24 — adjust to your network)
sudo ufw allow from 192.168.1.0/24 to any port 5432   # PostgreSQL
sudo ufw allow from 192.168.1.0/24 to any port 9000   # MinIO API
sudo ufw allow from 192.168.1.0/24 to any port 9001   # MinIO Console UI
sudo ufw allow from 192.168.1.0/24 to any port 4200   # Prefect UI
sudo ufw allow from 192.168.1.0/24 to any port 8000   # FastAPI (later)
```

- [ ] Internal ports opened for local subnet

---

## 3. Software Installation on the Server

### 3.1 Docker Engine

Do **not** install Docker Desktop. Install Docker Engine (CE) directly.

```bash
# Add Docker's official GPG key and repo
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group (no sudo for docker commands)
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

- [ ] Docker Engine installed
- [ ] Docker Compose plugin installed (`docker compose` — v2, not `docker-compose`)
- [ ] Current user in `docker` group
- [ ] `docker run hello-world` succeeds without sudo

### 3.2 GDAL & Geospatial System Libraries

GDAL is required by rasterio and must be installed at the system level. Install before building the Python container.

```bash
sudo apt-get install -y \
  gdal-bin \
  libgdal-dev \
  python3-gdal \
  libgeos-dev \
  libproj-dev \
  libspatialindex-dev \
  libsqlite3-dev \
  unzip \
  wget \
  curl \
  git \
  jq \
  htop \
  ncdu \
  tmux \
  screen
```

- [ ] `gdal-bin` installed — verify: `gdalinfo --version`
- [ ] `libgdal-dev` installed (needed to build rasterio in the container)
- [ ] Support tools installed: `git`, `wget`, `curl`, `unzip`, `jq`, `tmux`

### 3.3 uv (Python Package Manager)

uv is used on the host for running CLI commands outside Docker during development. It will also be installed inside the worker container via the Dockerfile.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # or restart shell

# Verify
uv --version
```

- [ ] `uv` installed on the server
- [ ] `uv --version` succeeds

### 3.4 Git

```bash
# Should already be installed; if not:
sudo apt-get install -y git

# Configure identity (for commits from the server if needed)
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

- [ ] Git installed and configured

---

## 4. Repository

- [ ] GitHub repository created for `plinth` (private)
- [ ] Repository cloned to the server at a location like `~/projects/plinth`
- [ ] SSH deploy key or personal access token configured for server → GitHub push/pull

**Suggested clone location:** `/home/plinth/projects/plinth`

---

## 5. API Keys & Accounts

All free-tier. None require a credit card for POC usage volumes.

### 5.1 Mapbox

Used for: **geocoding** (address → lat/lon) and **static map images** in reports.

1. Create account at [account.mapbox.com](https://account.mapbox.com)
2. Create a new **public access token** (default scopes are sufficient for static images + geocoding)
3. Note the token — it starts with `pk.`

> **Free tier:** 100,000 static image requests/month and 100,000 geocoding requests/month. Well above POC needs.

- [ ] Mapbox account created
- [ ] Public access token created and saved securely
- [ ] Token added to `.env` as `MAPBOX_TOKEN=pk.eyJ1...`

### 5.2 US Census Bureau API Key

Used for: **ACS 5-year demographic data** (population, income, housing, age) fetched at query time.

1. Register at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)
2. Key is emailed instantly — no approval process

- [ ] Census API key obtained
- [ ] Key added to `.env` as `CENSUS_API_KEY=...`

### 5.3 EPA AQS API Key

Used for: **Air quality** — annual PM2.5 and ozone monitor data.

1. Register at [aqs.epa.gov/aqsweb/documents/data_api.html#signup](https://aqs.epa.gov/aqsweb/documents/data_api.html#signup) — email your address to `aqsdatamart@epa.gov` with subject "AQS Data Mart account"
2. Key arrives by email, typically within 1 business day

- [ ] EPA AQS API key requested
- [ ] EPA AQS API key received and added to `.env` as `EPA_AQS_KEY=...` and `EPA_AQS_EMAIL=...`

### 5.4 No Other Keys Required for Phase 1

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

## 6. Developer Workstation Setup

Your laptop/desktop needs these to develop and operate the server.

### 6.1 Required

- [ ] SSH client configured — `~/.ssh/config` entry for the server:
  ```
  Host plinth-server
      HostName 192.168.x.x       # your server's IP
      User plinth
      IdentityFile ~/.ssh/id_ed25519
  ```
- [ ] **VS Code** with **Remote - SSH** extension installed (develop directly on the server over SSH)
- [ ] `git` installed locally

### 6.2 Recommended

- [ ] **TablePlus** or **DBeaver** — GUI PostgreSQL client for inspecting spatial data
- [ ] **QGIS** — desktop GIS for visually validating loaded spatial datasets (free, invaluable for debugging flood zones, soil units, etc.)
- [ ] **MinIO Client (`mc`)** — CLI for browsing MinIO buckets:
  ```bash
  # macOS
  brew install minio/stable/mc
  # or download from min.io/docs/minio/linux/reference/minio-mc.html
  ```

---

## 7. Pre-Flight Verification

Run these checks after all setup is complete, before starting Phase 0 code work.

### 7.1 Server Health

```bash
# From the server
docker compose version          # should print v2.x
gdalinfo --version              # should print GDAL 3.x
uv --version                    # should print uv x.x.x
df -h /data/minio               # should show the mounted HDD
free -h                         # verify RAM visible
nproc                           # verify core count
```

### 7.2 API Key Smoke Tests

```bash
# Mapbox geocoding (replace YOUR_TOKEN)
curl "https://api.mapbox.com/geocoding/v5/mapbox.places/11822%20E%20116th%20St%20N%2C%20Collinsville%2C%20OK.json?access_token=YOUR_TOKEN" \
  | jq '.features[0].geometry.coordinates'
# Expected: [-95.842..., 36.321...]

# Census API (replace YOUR_KEY)
curl "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01001_001E&for=state:40&key=YOUR_KEY" | jq .
# Expected: Oklahoma population data

# EPA AQS (replace YOUR_EMAIL and YOUR_KEY)
curl "https://aqs.epa.gov/aqsweb/documents/data_api/signup?email=YOUR_EMAIL" | jq .
# Or test with: /list/states?email=...&key=...

# NASA POWER (no key required)
curl "https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=T2M&community=RE&longitude=-95.842&latitude=36.322&format=JSON" \
  | jq '.properties.parameter.T2M' | head -5
# Expected: monthly temperature values
```

### 7.3 Test Coordinate Reference

| | Value |
|---|---|
| **Address** | 11822 E 116th St N, Collinsville, OK 74021 |
| **Latitude** | 36.32197414685 |
| **Longitude** | -95.842032856739 |
| **County** | Tulsa County, OK (FIPS 40143) |
| **State** | Oklahoma (FIPS 40) |
| **NHDPlus VPU** | 11 (Arkansas-White-Red) |
| **SSURGO** | Oklahoma state .gdb |
| **Expected IECC Zone** | 3A (Warm Humid) — verify against DOE lookup |

Keep this coordinate as the canonical test input throughout development. Every query function, ingestion validator, and end-to-end test uses it.

---

## 8. Credentials Management

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

## 9. Summary Checklist

### Hardware
- [ ] Server procured (64 GB RAM, 12+ core, 1 TB NVMe, 4 TB HDD)
- [ ] Ubuntu 24.04 LTS installed
- [ ] Static IP assigned

### Server Setup
- [ ] Non-root sudo user created, SSH key auth configured
- [ ] UFW firewall configured
- [ ] 4 TB HDD mounted at `/data/minio`, fstab entry added
- [ ] Docker Engine + Compose plugin installed
- [ ] GDAL system libraries installed
- [ ] `uv` installed
- [ ] Git installed and configured

### Accounts & Keys
- [ ] Mapbox account + token
- [ ] Census API key
- [ ] EPA AQS API key (allow 1 business day)

### Repository
- [ ] GitHub repo created
- [ ] Repo cloned to server

### Workstation
- [ ] SSH config entry for server
- [ ] VS Code + Remote SSH extension
- [ ] QGIS installed (for dataset validation)
- [ ] TablePlus or DBeaver installed

### Verification
- [ ] All API smoke tests pass
- [ ] Docker, GDAL, uv all report correct versions
- [ ] `/data/minio` mounted and visible
