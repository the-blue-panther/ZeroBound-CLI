import os
import json
import base64
from typing import Dict, Any, List

# Global working directory for the CLI
WORKING_DIR = os.getcwd()

def _resolve_path(path: str) -> str:
    """Resolve paths relative to the current working directory."""
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(WORKING_DIR, path))

def navigate(path: str) -> Dict[str, Any]:
    global WORKING_DIR
    new_path = _resolve_path(path)
    if os.path.isdir(new_path):
        WORKING_DIR = new_path
        os.chdir(WORKING_DIR) # Also change process CWD for convenience
        return {"status": "success", "current_directory": WORKING_DIR}
    # If it failed, let's be descriptive
    exists = os.path.exists(new_path)
    return {"error": f"Navigation failed. Path {'exists but is not a directory' if exists else 'does not exist'}: {new_path}"}

def list_files(path: str = ".") -> Dict[str, Any]:
    target = _resolve_path(path)
    if not os.path.exists(target):
        return {"error": f"List failed. Path not found: {target}"}
    if not os.path.isdir(target):
        # If it's a file, just list the file itself
        return {"files": [{
            "name": os.path.basename(target),
            "type": "file",
            "size": os.path.getsize(target)
        }]}
    
    try:
        items = os.listdir(target)
        results = []
        for item in items:
            try:
                full_path = os.path.join(target, item)
                results.append({
                    "name": item,
                    "type": "folder" if os.path.isdir(full_path) else "file",
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else 0
                })
            except (PermissionError, OSError):
                continue # Skip items we can't access
        return {"files": results}
    except Exception as e:
        return {"error": f"OS Error listing {target}: {str(e)}"}

def read_file(path: str) -> Dict[str, Any]:
    target = _resolve_path(path)
    if not os.path.isfile(target):
        return {"error": f"File not found: {target}"}
    try:
        with open(target, 'r', encoding='utf-8') as f:
            return {"content": f.read()}
    except UnicodeDecodeError:
        try:
            with open(target, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                return {"content_base64": b64, "message": "Binary file provided in base64"}
        except Exception as e:
            return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}

def write_file(path: str, content: str = "", lines: List[str] = None) -> Dict[str, Any]:
    target = _resolve_path(path)
    try:
        os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
        final_content = content
        if lines is not None:
            final_content = "\n".join(lines)
            
        with open(target, 'w', encoding='utf-8') as f:
            f.write(final_content)
        return {"status": "success", "message": f"Successfully wrote to {target}"}
    except Exception as e:
        return {"error": str(e)}

def create_folder(path: str) -> Dict[str, Any]:
    target = _resolve_path(path)
    try:
        os.makedirs(target, exist_ok=True)
        return {"status": "success", "message": f"Directory created: {target}"}
    except Exception as e:
        return {"error": str(e)}

TOOLS = [
    {
        "name": "navigate",
        "description": "Change the agent's current working directory.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The directory to navigate to"}},
            "required": ["path"]
        }
    },
    {
        "name": "list_files",
        "description": "List files and folders in a directory.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}}
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file with new content. Use RAW BLOCK syntax for multiline text.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "lines": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["path"]
        }
    },
    {
        "name": "create_folder",
        "description": "Create a new folder recursively.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    }
]

def handle_tool_call(tool_name: str, args: Dict[str, Any]) -> Any:
    """Dispatcher for tool calls with internal logging for debugging."""
    # Internal log to router.log (since we redirect stderr/stdout)
    print(f"[DEBUG] Tool Call: {tool_name}({json.dumps(args)}) | CWD: {WORKING_DIR}")
    
    if tool_name == "navigate": return navigate(**args)
    if tool_name == "list_files": return list_files(**args)
    if tool_name == "read_file": return read_file(**args)
    if tool_name == "write_file": return write_file(**args)
    if tool_name == "create_folder": return create_folder(**args)
    return {"error": f"Unknown tool: {tool_name}"}

def get_tools_prompt_description() -> str:
    desc = "--- AVAILABLE TOOLS ---\n"
    for t in TOOLS:
        params = []
        for pk, pv in t.get("parameters", {}).get("properties", {}).items():
            req = "required" if pk in t.get("parameters", {}).get("required", []) else "optional"
            params.append(f"{pk} ({req})")
        desc += f"• {t['name']}({', '.join(params)}): {t['description']}\n"
    return desc
