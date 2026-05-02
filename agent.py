import os
import re
import json
import httpx
import platform
from litellm import acompletion
from zb_tools import TOOLS, handle_tool_call, get_tools_prompt_description

API_BASE = "http://localhost:8000/v1"
MODEL = "openai/deepseek-chat"
os.environ["OPENAI_API_KEY"] = "sk-zerobound"

# ─── Path normalization helpers ──────────────────────────────────────────────
def normalize_path_for_display(path: str) -> str:
    """Handles ghost paths and ensures consistent display for the LLM."""
    if not path: return path
    norm = path.replace('\\', '/')
    # Fix 's' ghost paths if they appear (common in some Windows/WSL setups)
    # On Linux, we only do this if we are SURE it's a mangled path, 
    # but here we'll keep it generic to match the mother project's safety.
    return norm

def sanitize_conversation_paths(content: str) -> str:
    """Aggressively replace all ghost paths in conversation history string."""
    if not content: return content
    return content # Placeholder for now, can be expanded if specific ghost patterns are found

# ─── System Prompt (Modular Protocol v2.3) ────────────────────────────────────
def get_system_prompt() -> str:
    system_os = platform.system()
    release = platform.release()
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    tools_desc = get_tools_prompt_description()
    
    return f"""--- IDENTITY ---
You are ZeroBound CLI, the world's most capable engineering agent.
Current Host OS: {system_os} {release}
Current Workspace: {cwd}
User Home: {home}

--- RESPONSE MODES (MANDATORY) ---
You operate in TWO distinct modes. NEVER mix them in a single response:
1. **ACTION MODE**: Used when you need to execute tools. Include <THINK> and [ACTION] blocks only.
2. **REPORT MODE**: Used when the task is complete. Include <THINK> and [REPORT] blocks only.

--- CODE WRITING (ABSOLUTE REQUIREMENT) ---
You MUST use the RAW BLOCK syntax for ALL code when using write_file.
```json
CALL: write_file({{"path": "script.py"}})
```
````python
print("This is the gold standard for structural integrity")
````

--- PROTOCOLS ---
1. **FEEDBACK LOOP**: Action -> observe -> decide. NEVER presume success.
2. **VERIFICATION**: Analyze expectations in <THINK> before action, analyze ACTUAL result after.
3. **LINUX PATHS**: Use absolute paths like {home}/Downloads to avoid confusion.

{tools_desc}

--- FORMATTING ---
Respond in plain text or simple markdown suitable for a terminal.
Wrap your final summary inside [REPORT].
"""

def parse_structured_response(text: str) -> dict:
    """High-robustness parser from the mother project."""
    result = {"think": None, "actions": [], "report": None}
    if not text: return result

    # 1. Extract <THINK> block
    think_match = re.search(r'<THINK>(.*?)</THINK>', text, re.DOTALL | re.IGNORECASE)
    if not think_match:
        think_match = re.search(r'<THINK>(.*)', text, re.DOTALL | re.IGNORECASE)
    if think_match:
        result["think"] = think_match.group(1).strip()

    # 2. Extract [REPORT] block
    report_match = re.search(r'\[REPORT\](.*?)(?:\[/REPORT\]|$)', text, re.DOTALL | re.IGNORECASE)
    if report_match:
        result["report"] = report_match.group(1).strip()

    # 3. Extract [ACTION] blocks and tool calls
    action_matches = re.finditer(r'\[ACTION\](.*?)(?:\[/ACTION\]|$)', text, re.DOTALL | re.IGNORECASE)
    for match in action_matches:
        action_text = match.group(1).strip()
        result["actions"].extend(_parse_tool_calls(action_text))
    
    # Fallback for untagged actions
    if not result["actions"] and "CALL:" in text:
        result["actions"].extend(_parse_tool_calls(text))

    return result

def _parse_tool_calls(text: str) -> list:
    """Advanced parser supporting RAW BLOCK content extraction."""
    actions = []
    starts = [m.start() for m in re.finditer(r'CALL:\s*\w+\s*\(', text, re.IGNORECASE)]
    
    for i, start_pos in enumerate(starts):
        end_boundary = starts[i+1] if i+1 < len(starts) else len(text)
        chunk = text[start_pos:end_boundary]
        
        # 1. Parse the CALL: line
        match = re.search(r'CALL:\s*(\w+)\s*\((.*?)\)', chunk, re.DOTALL | re.IGNORECASE)
        if not match: continue
        
        tool_name = match.group(1)
        args_raw = match.group(2).strip()
        call_end = match.end()
        
        # Auto-wrap positional strings
        if not args_raw.startswith('{'):
            if '/' in args_raw or '\\' in args_raw or '"' in args_raw:
                val = args_raw.strip('"\'')
                args_raw = json.dumps({"path": val})
        
        try:
            args = json.loads(_fix_json_string(args_raw))
            
            # 2. Extract potential RAW BLOCK content (for write_file)
            remaining = chunk[call_end:].strip()
            # Look for 4 backticks or 3 backticks
            raw_match = re.search(r'(`{3,4})[a-zA-Z0-9_]*\n(.*?)\1', remaining, re.DOTALL)
            if raw_match:
                args["content"] = raw_match.group(2).strip()
            
            actions.append({"tool": tool_name, "args": args})
        except:
            continue
    return actions

def _fix_json_string(json_str: str) -> str:
    """Safely escape raw newlines and fix backslashes without corrupting existing ones."""
    # Fix raw newlines
    fixed = json_str.replace('\n', '\\n').replace('\r', '\\r')
    
    # Simple backslash fix: Only escape backslashes that are NOT followed by a valid JSON escape char
    valid_escapes = '"\\/bfnrtu'
    result = []
    i = 0
    while i < len(fixed):
        if fixed[i] == '\\':
            if i + 1 < len(fixed) and fixed[i+1] in valid_escapes:
                result.append(fixed[i:i+2])
                i += 2
                continue
            else:
                result.append('\\\\')
                i += 1
                continue
        result.append(fixed[i])
        i += 1
    return "".join(result)

async def fetch_current_url() -> str:
    """Helper to get the current browser URL from the router."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_BASE}/current_url", timeout=2.0)
            if resp.status_code == 200:
                return resp.json().get("url")
    except:
        pass
    return None

async def navigate_to_url(url: str):
    """Helper to force the browser to a specific URL (used for session resume)."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{API_BASE}/navigate", json={"url": url}, timeout=10.0)
    except:
        pass

async def chat_with_agent(messages: list, print_callback) -> dict:
    # Ensure system prompt is first
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": get_system_prompt()})
        
    try:
        response = await acompletion(
            model=MODEL,
            messages=messages,
            api_base=API_BASE,
            stop=["[/ACTION]", "[/REPORT]", "````\n[REPORT]"]
        )
        
        raw_content = response.choices[0].message.content or ""
        parsed = parse_structured_response(raw_content)
        
        if parsed["think"]: 
            print_callback("🧠 Thinking...", color="dim")
            
        tool_results = []
        for action in parsed["actions"]:
            t_name = action["tool"]
            t_args = action["args"]
            print_callback(f"⚙️ EXECUTING: {t_name}({json.dumps(t_args)})", color="cyan")
            try:
                res = handle_tool_call(t_name, t_args)
            except Exception as te:
                res = {"error": str(te)}
            tool_results.append({"tool": t_name, "result": res})
            
        # FORCE: If there were actions, we IGNORE the report from this turn
        final_report = ""
        if parsed["report"] and not parsed["actions"]:
            final_report = parsed["report"]
            print_callback(f"\n{final_report}", color="green")
            
        return {
            "raw": raw_content,
            "actions": parsed["actions"],
            "tool_results": tool_results,
            "report": final_report
        }
    except (ConnectionResetError, httpx.ConnectError):
        return {"error": "Router connection reset. It might still be processing."}
    except Exception as e:
        print_callback(f"LLM Error: {str(e)}", color="red")
        return {"error": str(e)}
