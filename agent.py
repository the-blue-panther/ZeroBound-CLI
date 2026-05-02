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

def get_system_prompt() -> str:
    system_os = platform.system()
    release = platform.release()
    
    return f"""--- IDENTITY ---
You are ZeroBound CLI, a lightweight terminal-based autonomous agent.
Current Host OS: {system_os} {release}
You MUST adapt your terminal commands and file paths for {system_os}.

--- RESPONSE MODES ---
1. **ACTION MODE**: Used to execute tools. Include <THINK> and [ACTION] blocks.
2. **REPORT MODE**: Used to communicate back to the user. Include <THINK> and [REPORT] blocks.

**CRITICAL RULE**: Do NOT combine [ACTION] and [REPORT] in the same response. If you need to use a tool, use [ACTION] and WAIT for the result. Only use [REPORT] AFTER you have seen the tool results in your history.

--- TOOL SYNTAX (STRICT JSON) ---
Invoke tools EXACTLY like this inside [ACTION]:
CALL: tool_name({{"arg": "val"}})

{get_tools_prompt_description()}

--- FORMATTING ---
Respond in plain text or simple markdown suitable for a terminal. 
Do not use complex HTML or advanced markdown features that a basic terminal cannot render.
"""

def _fix_json_string(json_str: str) -> str:
    """Fix common JSON errors, especially unescaped backslashes and raw newlines."""
    # Fix raw newlines inside strings (JSON doesn't allow them)
    # This is a bit tricky, but we can try to escape them if they are between quotes
    fixed = json_str.replace('\n', '\\n').replace('\r', '\\r')
    
    # Fix single backslashes in paths: "C:\Users" -> "C:\\Users"
    # But don't break existing valid escapes like \" or \\ or \n
    fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', fixed)
    return fixed

def parse_actions(text: str) -> list:
    """Ultra-robust parser for CALL: tool({...})"""
    actions = []
    
    # 1. Try to find content inside [ACTION] blocks
    action_content = ""
    matches = list(re.finditer(r'\[ACTION\](.*?)(?:\[/ACTION\]|$)', text, re.DOTALL | re.IGNORECASE))
    for m in matches:
        action_content += m.group(1) + "\n"
    
    # 2. Fallback: if no [ACTION] tags or no tools found in them, search the whole text
    if not action_content:
        action_content = text

    starts = [m.start() for m in re.finditer(r'CALL:\s*\w+\s*\(', action_content, re.IGNORECASE)]
    
    for i, start_pos in enumerate(starts):
        end_boundary = starts[i+1] if i+1 < len(starts) else len(action_content)
        chunk = action_content[start_pos:end_boundary]
        
        # Match CALL: name(args)
        # We use a non-greedy capture for args until the LAST matching parenthesis in the chunk
        match = re.search(r'CALL:\s*(\w+)\s*\(\s*(.*)\)\s*$', chunk.strip(), re.DOTALL | re.IGNORECASE)
        if match:
            tool_name = match.group(1)
            args_raw = match.group(2).strip()
            
            # If the greedy capture ate too much (e.g. into the next line's junk), 
            # find the first valid JSON ending
            if args_raw.startswith('{'):
                # Basic balance check or find last }
                last_brace = args_raw.rfind('}')
                if last_brace != -1:
                    args_raw = args_raw[:last_brace+1]
            
            # Auto-wrap if it looks like positional/missing braces
            if not args_raw.startswith('{') and ':' in args_raw:
                args_raw = "{" + args_raw + "}"
            
            try:
                args = json.loads(_fix_json_string(args_raw))
                actions.append({"tool": tool_name, "args": args})
            except:
                # Fuzzy brace recovery for the most desperate cases
                brace_match = re.search(r'(\{.*\})', args_raw, re.DOTALL)
                if brace_match:
                    try:
                        args = json.loads(_fix_json_string(brace_match.group(1)))
                        actions.append({"tool": tool_name, "args": args})
                    except: pass
    return actions

def parse_report(text: str) -> str:
    # Look for [REPORT] and take everything until [/REPORT] or end
    # We use a non-greedy match to avoid eating subsequent actions, but greedy enough to get the content
    match = re.search(r'\[REPORT\](.*?)(?:\[/REPORT\]|$)', text, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback: if no [REPORT] tag but has plain text at the end
        if "[ACTION]" not in text and "<THINK>" not in text:
            return text.strip()
        return ""
    return match.group(1).strip()

def parse_think(text: str) -> str:
    match = re.search(r'<THINK>(.*?)</THINK>', text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'<THINK>(.*)', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""

async def fetch_current_url() -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_BASE}/current_url", timeout=2.0)
            if resp.status_code == 200:
                return resp.json().get("url")
    except (httpx.ConnectError, httpx.ReadTimeout, ConnectionResetError, Exception):
        pass
    return None

async def navigate_to_url(url: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{API_BASE}/navigate", json={"url": url}, timeout=10.0)
    except (httpx.ConnectError, httpx.ReadTimeout, ConnectionResetError, Exception):
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
            functions=TOOLS,
            function_call="none",
            stop=["[/ACTION]", "[/REPORT]"]
        )
        
        raw_content = response.choices[0].message.content or ""
        
        # Parse the structured response
        think = parse_think(raw_content)
        actions = parse_actions(raw_content)
        report = parse_report(raw_content)
        
        # User requested to hide THINK blocks in CLI, so we show a minimal indicator
        if think: 
            print_callback("🧠 Thinking...", color="dim")
            
        tool_results = []
        for action in actions:
            t_name = action["tool"]
            t_args = action["args"]
            print_callback(f"⚙️ EXECUTING: {t_name}({json.dumps(t_args)})", color="cyan")
            try:
                res = handle_tool_call(t_name, t_args)
            except Exception as te:
                res = {"error": str(te)}
                
            tool_results.append({
                "tool": t_name,
                "result": res
            })
            
        # FORCE: If there were actions, we IGNORE the report from this turn to prevent hallucination
        final_report = ""
        if report and not actions:
            final_report = report
            print_callback(f"\n{final_report}", color="green")
            
        return {
            "raw": raw_content,
            "actions": actions,
            "tool_results": tool_results,
            "report": final_report
        }
    except (ConnectionResetError, httpx.ConnectError):
        # Silence specific Windows asyncio noise
        return {"error": "Router connection reset. It might still be processing."}
    except Exception as e:
        print_callback(f"LLM Error: {str(e)}", color="red")
        return {"error": str(e)}
