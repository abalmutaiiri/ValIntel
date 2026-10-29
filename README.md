# ValIntel

**A desktop companion project for VALORANT.**

> [!IMPORTANT]
> **Unofficial, experimental project.** ValIntel is not affiliated with, endorsed by, or approved by Riot Games. Some prototype features use undocumented VALORANT client endpoints or involve activities restricted by Riot's policies, including automated agent locking, identifying hidden players, and pre-match scouting. **Do not assume these features are permitted or safe to use on a live account. USE AT YOUR OWN RISK** 

## Features

| Area | What it does | Current status |
| --- | --- | --- |
| **Agent browser** | Browse agent portraits, search by name, and filter by role. | Implemented; portraits require network access initially. |
| **Agent selection** | Prototype controls to select an agent and request a lock after a cancellable 3-second countdown. | Implemented against unofficial endpoints; live behavior and policy compliance are **not guaranteed**. |
| **Match overview** | Shows connection state, detected map, and agent-select/in-game status. | Depends on the running Riot Client and undocumented endpoints. |
| **Live roster** | Displays available team/player and agent information. | Depends on the game phase and API responses; hidden-player identification is policy-restricted. |
| **Match insights** | Compares available recent statistics and shows an experimental win estimate. | **Heuristic, not a trained AI model** or calibrated win probability. |
| **Pattern Check** | Counts repeated opponents in up to 10 Competitive matches for an authorized player; highlights 4+ encounters. | Manual analysis trigger; partial histories are marked as partial. Repeated opponents do **not** prove wintrading. |
| **Settings** | Saves HenrikDEV API key using the OS credential store; configures refresh and optional stats loading. | Implemented; never commit API keys to GitHub. |
| **Demo Mode** | Previews the interface with sample data, without sending VALORANT agent actions. | Available without an active game session. |

### Screenshots

Screenshots are not included in this repository snapshot. To showcase the UI on GitHub, add a screenshot to `docs/screenshots/overview.png` and then uncomment the line below:

<!-- ![ValIntel overview](docs/screenshots/overview.png) -->

For a good demo, capture **Overview**, **Agent Select**, **Match Insights**, and **Pattern Check**, preferably in Demo Mode with fictional data.

## Requirements

- **Windows 10 or 11** for live Riot Client integration.
- **Python 3.12** recommended for development and packaging.
- Internet connection for agent portraits and third-party API lookups.
- VALORANT and the Riot Client running for live match features.
- Optional: your own **HenrikDEV API key** for supported statistics/account lookups. Availability depends on the provider.

Python dependencies are listed in `requirements.txt` (`PySide6`, `requests`, and `keyring`).

## Quick start

1. Download or clone this repository and open a PowerShell window in the project folder.
2. Create and activate a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Launch ValIntel:

   ```powershell
   python ValIntelGUI.py
   ```

5. Click **Demo Mode** first to explore the interface without VALORANT. For supported live features, launch VALORANT and use **Refresh**.

> **PowerShell note:** If script execution is disabled, you can skip activation and run `\.venv\Scripts\python.exe -m pip install -r requirements.txt` followed by `\.venv\Scripts\python.exe ValIntelGUI.py`.

### Configure an API key

1. Open **Settings**.
2. Enter your own HenrikDEV API key and choose **Save Settings**.
3. Enable **Load recent Competitive stats** only if you need statistics and are authorized to access the relevant data.

On Windows, `keyring` saves the credential for your Windows user. It is not hardcoded into the distributed executable. Replacing or rebuilding the EXE should not require entering the key again on the same Windows account.

**Never put an API key, Riot token, `lockfile`, or personal match data in a GitHub commit or issue.**

## Using the interface

The left sidebar currently **scrolls to sections of one dashboard**; it does not open separate pages.

- **Overview:** connection and match state.
- **Agent Select:** agent search/filters and experimental selection/lock controls.
- **Live Roster:** available player and agent information.
- **Match Insights:** recent statistics, data coverage, and heuristic estimate.
- **Pattern Check:** manually initiated repeated-opponent analysis of authorized histories.
- **Name History:** import or record historical match observations for your own account.
- **Settings:** API key, refresh, and stats preferences.

### Understanding the match estimate

The displayed percentage is a **heuristic score** derived from the available recent Competitive statistics. It is not a trained machine-learning model, is not calibrated against held-out match outcomes, and must not be interpreted as a scientifically validated probability of winning. If data is incomplete, the app may show **Not Enough Data** instead.

### Understanding Pattern Check

Pattern Check processes up to **10 distinct, usable Competitive matches** for each selected and authorized player. It compares player identifiers and team assignments and flags an opponent seen **at least four times on the other team**.

- It is **not** a cheat detector or proof of wintrading.
- Shared matchmaking pools and rank/region/time-of-day effects can produce repeat opponents naturally.
- The current **“I confirm permission” checkbox is not verified consent**. A publicly distributed, compliant product would need appropriate authorization and Riot approval/RSO integration where required.
- A missing or partial history is shown as **unavailable/partial**, not “no suspicious activity.”



