# ZeroBound CLI

Welcome to **ZeroBound CLI**, a lightweight, fully self-contained terminal version of the ZeroBound autonomous agent. This project is designed to be highly portable and completely reproducible on any new machine (Windows, Linux, or macOS).

---

## 🛠️ First-Time Setup (On a New Machine)

Because this CLI uses the official DeepSeek Web UI under the hood, you need to log in to DeepSeek **just once** on any new machine.

### Step 1: Initialize the Environment
Open your terminal and navigate into the `ZeroBound_CLI` folder. Then run the launcher script to automatically install all requirements and browsers.

**On Windows (PowerShell or CMD):**
```powershell
.\zb.bat
```

**On Linux/macOS:**
```bash
chmod +x zb.sh
./zb.sh
```
*(Note: You can press `Ctrl+C` to exit the CLI once the installation finishes if you need to proceed to Step 2).*

### Step 2: The One-Time DeepSeek Login
To allow the CLI to communicate with DeepSeek, you must generate a `state.json` login token.

1. Make sure you are inside the `ZeroBound_CLI` folder.
2. Activate the virtual environment:
   - **Windows:** `.\venv\Scripts\activate`
   - **Linux/Mac:** `source venv/bin/activate`
3. Run the manual login script:
   ```bash
   python router/manual_login.py deepseek
   ```
4. A browser window will pop up. Log in to DeepSeek manually.
5. Once you are logged in and see the chat screen, close the browser window. 
*(Your session is now saved securely in `router/profiles/deepseek/state.json`).*

---

## 🚀 How to Run the CLI

Whenever you want to use the agent, simply open your terminal in the `ZeroBound_CLI` folder and run the launcher script. 

**On Windows:**
```powershell
.\zb.bat
```

**On Linux/macOS:**
```bash
./zb.sh
```

**What happens in the background?**
The script will automatically start the hidden Web Router in the background, give it a few seconds to boot, and then launch the terminal UI (`zb>`). 

---

## 🛑 How to Stop the CLI

To safely stop the CLI and cleanly shut down the background Web Router:

1. Type `exit` or `quit` into the `zb>` prompt and hit Enter.
2. **Alternatively:** Press `Ctrl+C` on your keyboard.

The CLI will print `Shutting down ZeroBound Web Router...` and safely terminate all background processes.

---

## 🎮 CLI Commands Reference

Once the `zb>` prompt is active, you can talk to the agent naturally ("Create a python script that prints hello world"), or use these special system commands:

| Command | Description |
| :--- | :--- |
| `help` | Lists all available system commands and the Agent's file-system tools. |
| `restart` | Starts a completely fresh conversation session. |
| `history` | Lists your 10 most recent sessions (including their DeepSeek Web URLs). |
| `resume <id>` | Instantly reloads a past session (e.g., `resume 2`) and commands the hidden browser to navigate back to that exact DeepSeek Chat link! |
| `exit` | Closes the CLI and shuts down the router. |

---

## ⚙️ Cross-Platform OS Awareness
ZeroBound CLI is smart. It uses Python's `platform` module internally. If you run this folder on an Ubuntu machine, the Agent will automatically realize it's on Linux and start using `bash` syntax and `/` forward slashes for all its file operations. You do not need to configure anything when switching OS!
