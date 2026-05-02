# Architecture Overview: ZeroBound CLI
## An Autonomous Terminal Agent with Web-UI Bridging

**Abstract:** This document outlines the architecture and implementation of ZeroBound CLI, a portable, self-contained autonomous agent designed for terminal environments. The system leverages a decoupled architecture that bridges high-level LLM reasoning with local OS-aware tool execution and persistent session management.

---

## 1. System Architecture

ZeroBound CLI is built on a modular design comprising five primary layers. This separation ensures portability and allows the agent to function as a standalone unit on any host machine.

### 1.1 Interface Layer (`cli.py`)
The terminal-based frontend. It manages the user input loop, session lifecycle (start/resume/restart), and background process orchestration. It is responsible for booting the internal router and maintaining the "Thinking" state visibility for the user.

### 1.2 Cognitive Layer (`agent.py`)
The "Brain" of the system. It handles:
- **System Prompting:** Dynamic injection of Host OS metadata (Windows/Linux/macOS).
- **Response Parsing:** Ultra-robust extraction of `<THINK>`, `[ACTION]`, and `[REPORT]` blocks.
- **Hallucination Protection:** A strict logic gate that prevents the agent from reporting success until actions are verified.

### 1.3 Tool Execution Layer (`zb_tools.py`)
A collection of OS-aware file system primitives (`navigate`, `list_files`, `read_file`, `write_file`, `create_folder`). These tools use relative path resolution anchored to a global `WORKING_DIR` to maintain context during navigation.

### 1.4 Persistence Layer (`db_manager.py`)
A robust SQLite implementation (`history.db`) that tracks:
- Conversation history (JSON-serialized messages).
- Associated DeepSeek Web URLs for session resumption.
- Automated path locking to prevent database "drifting" during folder navigation.

### 1.5 Infrastructure Layer (`router/`)
An embedded instance of `llm-web-router` that provides a local OpenAI-compatible API. It manages a headless (or headed) Edge/Chromium browser via Playwright, automating the interaction with the DeepSeek Web UI.

---

## 2. Technical Workflow

```mermaid
graph TD
    User([User Terminal]) <--> CLI[cli.py: Main Interface Loop]
    CLI <--> Agent[agent.py: Reasoning & Parsing]
    
    subgraph "Execution Context"
        Agent --> Tools[zb_tools.py: OS-Aware FS Tools]
        Tools <--> FS[(Local File System)]
    end
    
    subgraph "Memory & State"
        CLI <--> DB[db_manager.py: SQLite]
        DB <--> SQLite[(history.db)]
    end
    
    subgraph "Bridge Infrastructure (Background)"
        Agent <--> Router[router/server.py: FastAPI Bridge]
        Router <--> Browser[Playwright/Edge Context]
        Browser <--> DeepSeek[DeepSeek Web UI]
    end

    style CLI fill:#f9f,stroke:#333,stroke-width:2px
    style Agent fill:#bbf,stroke:#333,stroke-width:2px
    style Bridge Infrastructure (Background) fill:#dfd,stroke:#333,stroke-dasharray: 5 5
```

---

## 3. Key Design Features

### 3.1 OS-Awareness
The agent detects its environment at runtime using Python's `platform` module. This allows it to switch between Windows backslashes (`\`) and Unix forward slashes (`/`) and adapt its command syntax automatically, making the code-base 100% portable between OSs.

### 3.2 Robust JSON Recovery
Because Web-UIs can introduce noise or character encoding issues, the CLI includes an "Ultra-Robust" parser that fixes unescaped backslashes, raw newlines, and malformed JSON braces in real-time before processing tool calls.

### 3.3 Atomic Operation
The system enforces a turn-based verification protocol. If an agent initiates an action, the system suppresses the report mode until the tool result is logged, effectively eliminating the "hallucination of success" common in simple autonomous agents.

---

## 4. Distribution and Deployment
The project is designed to be shared as a single compressed folder.
- **`zb.bat` / `zb.sh`:** Automated launcher scripts that handle Virtual Environment (venv) setup and dependency installation.
- **Manual Login:** A pre-flight safety check ensures that the user has a valid `state.json` (Playwright session) before the agent boots, preventing runtime authentication failures.
