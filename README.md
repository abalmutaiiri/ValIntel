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

 ![ValIntel overview](docs/screenshots/image.png) 


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

## License

**Copyright © 2026 ValIntel. All Rights Reserved.**

ValIntel is proprietary software. The source code is publicly available for viewing and portfolio evaluation purposes only.

Unauthorized copying, modification, redistribution, commercialization, or creation of derivative works is prohibited without prior written permission from the copyright holder.

See the [LICENSE](LICENSE) file for the full terms.

**Disclaimer:** ValIntel is an independent project and is not affiliated with, endorsed by, or sponsored by Riot Games. VALORANT and related trademarks belong to Riot Games.



