# SPDX-FileCopyrightText: © 2024 RunScriptz Plugin
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Actions for RunScriptz plugin.
This file defines actions that will appear in Krita's keyboard shortcuts menu.
"""

from krita import Krita
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence
import os
import json

# Configuration file for hotkeys
HOTKEY_FILE = os.path.join(
    Krita.instance().getAppDataLocation() or os.path.expanduser("~"),
    "run_scriptz_hotkeys.json"
)

class RunScriptzAction(QAction):
    """Custom action class for RunScriptz commands"""
    
    def __init__(self, action_id, text, script_path, parent=None):
        super().__init__(text, parent)
        self.action_id = action_id
        self.script_path = script_path
        self.triggered.connect(self.run_script)
    
    def run_script(self):
        """Execute the associated script"""
        if not os.path.exists(self.script_path):
            print(f"[RunScriptz] Script not found: {self.script_path}")
            return
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("run_scriptz_external", self.script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Try to call main() function if it exists
            if hasattr(module, "main"):
                module.main()
            else:
                print(f"[RunScriptz] Executed {os.path.basename(self.script_path)}")
        except Exception as e:
            print(f"[RunScriptz] Error running {self.script_path}: {e}")

def get_all_scripts(scripts_folder):
    """
    Generator that yields (relative_path_key, full_path) for all scripts in folder and subfolders.
    For root files, key is just filename.
    For subfolder files, key is relative path (e.g. 'sub/foo.py').
    """
    try:
        # 1. Root files
        for fname in sorted(os.listdir(scripts_folder)):
            fpath = os.path.join(scripts_folder, fname)
            if os.path.isfile(fpath) and fname.endswith(".py"):
                yield (fname, fpath)
        
        # 2. Subfolders
        for dname in sorted(os.listdir(scripts_folder)):
            dpath = os.path.join(scripts_folder, dname)
            if os.path.isdir(dpath) and not dname.startswith('.'):
                try:
                    for fname in sorted(os.listdir(dpath)):
                        if fname.endswith(".py"):
                            # Consistent with runscriptz.py logic: folder/filename
                            rel_path = f"{dname}/{fname}"
                            fpath = os.path.join(dpath, fname)
                            yield (rel_path, fpath)
                except:
                    continue
    except Exception as e:
        print(f"[RunScriptz] Error scanning scripts: {e}")

def get_action_id_for_key(script_key):
    """
    Generate a safe action ID from the script key.
    Root file 'foo.py' -> 'run_scriptz_foo.py' (backward compatible)
    Sub file 'sub/foo.py' -> 'run_scriptz_sub_foo.py' (sanitized)
    """
    # Replace path separators with underscores for ID safety
    safe_suffix = script_key.replace("/", "_").replace("\\", "_")
    return f"run_scriptz_{safe_suffix}"


def create_actions_for_scripts(scripts_folder):
    """
    Create actions for all scripts in the specified folder.
    Returns a list of action objects.
    """
    actions = []
    
    if not scripts_folder or not os.path.isdir(scripts_folder):
        return actions
    
    # Load existing hotkeys
    hotkeys = load_hotkeys()
    
    for filename in sorted(os.listdir(scripts_folder)):
        if not filename.endswith(".py"):
            continue
            
        script_path = os.path.join(scripts_folder, filename)
        action_id = f"run_scriptz_{filename}"
        action_text = f"RunScriptz: {filename}"
        
        # Create action
        action = RunScriptzAction(action_id, action_text, script_path)
        
        # Set shortcut if available
        if filename in hotkeys:
            action.setShortcut(QKeySequence(hotkeys[filename]))
            action.setShortcutContext(Qt.ApplicationShortcut)
        
        actions.append(action)
    
    return actions

def clear_existing_actions(scripts_folder):
    """Clear existing RunScriptz actions to prevent duplicates"""
    app = Krita.instance()
    window = app.activeWindow()
    
    if not window:
        return
    
    if not scripts_folder or not os.path.isdir(scripts_folder):
        return
    
    for filename in os.listdir(scripts_folder):
        if not filename.endswith(".py"):
            continue
            
        action_id = f"run_scriptz_{filename}"
        
        # Try to clear shortcuts without disconnecting signals
        try:
            action = app.action(action_id)
            if action:
                action.setShortcut("")
        except:
            pass
        
        try:
            action = window.action(action_id)
            if action:
                action.setShortcut("")
        except:
            pass

def register_actions_with_krita(scripts_folder, retry_count=0, force_create_all=False, window=None):
    """
    Register all script actions with Krita's action system.
    This makes them appear in the keyboard shortcuts menu and persists shortcuts.

    Args:
        scripts_folder: Path to the scripts folder
        retry_count: Number of retry attempts
        force_create_all: If True, create actions for ALL scripts, not just those with hotkeys
        window: Explicit window instance to use (optional)
    """
    app = Krita.instance()
    if not app:
        print("[RunScriptz] No Krita instance found")
        return

    # Use provided window or try to find active window
    if not window:
        window = app.activeWindow()

    if not window and retry_count < 5:
        # If no window is available, try again after a short delay
        print(f"[RunScriptz] No active window found, retrying in 2 seconds... (attempt {retry_count + 1}/5)")
        QTimer.singleShot(2000, lambda: register_actions_with_krita(scripts_folder, retry_count + 1, force_create_all))
        return

    if not window:
        print("[RunScriptz] No active window found after retries, skipping registration")
        return

    if not scripts_folder or not os.path.isdir(scripts_folder):
        print("[RunScriptz] Invalid scripts folder")
        return

    print(f"[RunScriptz] Registering actions for scripts in: {scripts_folder}")

    # First, try to restore hotkeys from Krita's settings
    restore_hotkeys_from_krita_settings(scripts_folder)

    # Load existing hotkeys (now potentially updated from Krita settings)
    hotkeys = load_hotkeys()

    # Register each script as a persistent action
    for script_key, script_path in get_all_scripts(scripts_folder):
        
        action_id = get_action_id_for_key(script_key)
        action_text = f"RunScriptz: {script_key}"

        # Only create actions for scripts with hotkeys, unless force_create_all is True
        if not force_create_all and script_key not in hotkeys:
            continue

        try:
            # Always try to create the action - Krita will handle duplicates
            action = window.createAction(action_id, action_text, "tools/scripts")

            if action:
                print(f"[RunScriptz] Created action: {action_id}")

                # CRITICAL FIX: Create a proper closure to capture the script_path
                def create_script_runner(path):
                    return lambda: run_script_from_path(path)

                # Set up the triggered connection with proper closure
                action.triggered.connect(create_script_runner(script_path))
                print(f"[RunScriptz] Connected action to script: {script_path}")

                # Set shortcut if available - this will be saved by Krita
                if script_key in hotkeys:
                    shortcut_str = hotkeys[script_key]
                    shortcut = QKeySequence(shortcut_str)
                    action.setShortcut(shortcut)
                    action.setShortcutContext(Qt.ApplicationShortcut)
                    print(f"[RunScriptz] Set shortcut for {script_key}: {shortcut_str}")

                    # Force Krita to recognize and save the shortcut
                    try:
                        # Write directly to Krita's settings
                        app.writeSetting("Shortcuts", action_id, shortcut_str)
                        print(f"[RunScriptz] Forced write to Krita settings: {action_id} = {shortcut_str}")
                    except Exception as e:
                        print(f"[RunScriptz] Warning: Could not write setting: {e}")
                else:
                    print(f"[RunScriptz] No hotkey assigned for: {script_key}")
            else:
                print(f"[RunScriptz] Failed to create action: {action_id}")

        except Exception as e:
            print(f"[RunScriptz] Error registering action for {script_key}: {e}")

    print(f"[RunScriptz] Finished registering actions")

    # Force Krita to save the current shortcut configuration
    try:
        # This triggers Krita to save shortcuts to its configuration
        app.writeSetting("", "runscriptz_last_registration", str(len(hotkeys)))
        print("[RunScriptz] Triggered Krita settings save")
    except Exception as e:
        print(f"[RunScriptz] Could not trigger settings save: {e}")

def enforce_hotkeys(window=None):
    """
    Periodically called to ensure hotkeys haven't been wiped by Krita's loading process.
    Checks existing actions and re-applies shortcuts if they are missing.
    """
    if not window:
        app = Krita.instance()
        if app:
            window = app.activeWindow()
    
    if not window:
        return

    hotkeys = load_hotkeys()
    if not hotkeys:
        return

    print(f"[RunScriptz] Enforcing hotkeys for {len(hotkeys)} scripts...")
    
    fixed_count = 0
    app = Krita.instance() # For writeSetting

    for script_key, shortcut_str in hotkeys.items():
        action_id = get_action_id_for_key(script_key)
        
        # Try to find the action
        action = None
        try:
            # Try window first
            action = window.action(action_id)
        except:
            pass
            
        if not action:
            try:
                # Try application level
                action = app.action(action_id)
            except:
                pass
        
        if action:
            current_shortcut = action.shortcut().toString()
            # If shortcut is missing or different, fix it
            if current_shortcut != shortcut_str:
                print(f"[RunScriptz] Fix: Action {action_id} lost shortcut (has '{current_shortcut}', wants '{shortcut_str}'). Re-applying.")
                
                shortcut = QKeySequence(shortcut_str)
                action.setShortcut(shortcut)
                action.setShortcutContext(Qt.ApplicationShortcut)
                
                # Re-force Krita setting
                try:
                    app.writeSetting("Shortcuts", action_id, shortcut_str)
                except:
                    pass
                    
                fixed_count += 1

    if fixed_count > 0:
        print(f"[RunScriptz] Enforcer fixed {fixed_count} broken shortcuts.")
    else:
        print("[RunScriptz] Enforcer found all shortcuts correct.")

def ensure_actions_exist_on_startup(window=None):
    """
    Ensure all script actions with hotkeys exist when Krita starts.
    This should be called as early as possible in the plugin lifecycle.
    """
    print("[RunScriptz] === ENSURING ACTIONS EXIST ON STARTUP ===")

    app = Krita.instance()
    if not app:
        print("[RunScriptz] ERROR: No Krita instance found!")
        return

    # Use provided window or try to find active window
    if not window:
        window = app.activeWindow()
        
    print(f"[RunScriptz] Active window available: {window is not None}")

    # Load config to get scripts folder
    try:
        config_file = os.path.join(
            app.getAppDataLocation() or os.path.expanduser("~"),
            "run_scriptz_config.json"
        )

        print(f"[RunScriptz] Looking for config file: {config_file}")
        print(f"[RunScriptz] Config file exists: {os.path.exists(config_file)}")

        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                scripts_folder = cfg.get("scripts_folder", "")

            print(f"[RunScriptz] Scripts folder from config: {scripts_folder}")
            print(f"[RunScriptz] Scripts folder exists: {os.path.isdir(scripts_folder) if scripts_folder else False}")

            if scripts_folder and os.path.isdir(scripts_folder):
                # Load hotkeys to see what we need to create
                hotkeys = load_hotkeys()
                print(f"[RunScriptz] Found {len(hotkeys)} hotkeys in JSON file:")
                for script, key in hotkeys.items():
                    print(f"[RunScriptz]   {script} -> {key}")

                if hotkeys:
                    print(f"[RunScriptz] calling register_actions_with_krita...")
                    # Register actions for scripts that have hotkeys
                    register_actions_with_krita(scripts_folder, force_create_all=False, window=window)
                else:
                    print("[RunScriptz] No hotkeys found, nothing to register")
            else:
                print("[RunScriptz] No valid scripts folder found")
        else:
            print("[RunScriptz] No config file found")

    except Exception as e:
        print(f"[RunScriptz] ERROR in ensure_actions_exist_on_startup: {e}")
        import traceback
        traceback.print_exc()

    print("[RunScriptz] === END ENSURING ACTIONS ===")

def create_single_action_with_hotkey(scripts_folder, script_name, hotkey):
    """
    Create a single action with hotkey - for immediate creation
    """
    print(f"[RunScriptz] Creating single action: {script_name} -> {hotkey}")

    app = Krita.instance()
    window = app.activeWindow()

    if not window:
        print("[RunScriptz] No window available for single action creation")
        return False

    script_path = os.path.join(scripts_folder, script_name)
    action_id = f"run_scriptz_{script_name}"
    action_text = f"RunScriptz: {script_name}"

    try:
        # Create the action
        action = window.createAction(action_id, action_text, "tools/scripts")

        if action:
            # Connect to script execution with proper closure
            def create_script_runner(path):
                return lambda: run_script_from_path(path)

            action.triggered.connect(create_script_runner(script_path))

            # Set the shortcut
            shortcut = QKeySequence(hotkey)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ApplicationShortcut)
            action.setAutoRepeat(False)

            print(f"[RunScriptz] Successfully created single action: {action_id} with hotkey {hotkey}")
            return True
        else:
            print(f"[RunScriptz] Failed to create single action: {action_id}")
            return False

    except Exception as e:
        print(f"[RunScriptz] Error creating single action: {e}")
        return False

def register_at_app_level(app, scripts_folder):
    """Register actions at application level when no window is available"""
    if not scripts_folder or not os.path.isdir(scripts_folder):
        return

    print(f"[RunScriptz] Attempting app-level registration for: {scripts_folder}")
    hotkeys = load_hotkeys()

    for filename in sorted(os.listdir(scripts_folder)):
        if not filename.endswith(".py"):
            continue

        script_path = os.path.join(scripts_folder, filename)
        action_id = f"run_scriptz_{filename}"
        action_text = f"RunScriptz: {filename}"

        try:
            # Try to create action at application level
            action = app.createAction(action_id, action_text)
            if action:
                # Set up the triggered connection
                action.triggered.connect(lambda: run_script_from_path(script_path))

                # Set shortcut if available
                if filename in hotkeys:
                    action.setShortcut(QKeySequence(hotkeys[filename]))
                    action.setShortcutContext(Qt.ApplicationShortcut)
                    print(f"[RunScriptz] App-level action created with hotkey: {filename} -> {hotkeys[filename]}")
                else:
                    print(f"[RunScriptz] App-level action created: {filename}")
        except Exception as e:
            print(f"[RunScriptz] Failed to create app-level action for {filename}: {e}")

# Global variable to track last execution time
_last_execution_time = 0

def run_script_from_path(script_path):
    """Execute a script from the given path"""
    global _last_execution_time
    
    # Prevent rapid multiple executions (debounce)
    import time
    current_time = time.time()
    if current_time - _last_execution_time < 0.5:  # 500ms debounce
        return
    _last_execution_time = current_time
    
    if not os.path.exists(script_path):
        return
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_scriptz_external", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Try to call main() function if it exists
        if hasattr(module, "main"):
            module.main()
    except Exception as e:
        pass

def load_hotkeys():
    """Load hotkey configuration from file"""
    try:
        if os.path.exists(HOTKEY_FILE):
            with open(HOTKEY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        pass
    return {}

def save_hotkeys(hotkeys):
    """Save hotkey configuration to file"""
    try:
        os.makedirs(os.path.dirname(HOTKEY_FILE), exist_ok=True)
        with open(HOTKEY_FILE, "w", encoding="utf-8") as f:
            json.dump(hotkeys, f, indent=2)
    except Exception as e:
        pass

def assign_hotkey_to_script(script_name, key_sequence, script_path=None):
    """Assign a hotkey to a specific script and ensure it persists in Krita"""
    print(f"[RunScriptz] Assigning hotkey '{key_sequence}' to '{script_name}'")

    # Test the key sequence first
    try:
        test_seq = QKeySequence(key_sequence)
        if test_seq.isEmpty():
            print(f"[RunScriptz] Invalid key sequence: '{key_sequence}'")
            return False
    except Exception as e:
        print(f"[RunScriptz] Error parsing key sequence: {e}")
        return False

    # Save to our hotkey file
    hotkeys = load_hotkeys()
    hotkeys[script_name] = key_sequence
    save_hotkeys(hotkeys)
    print(f"[RunScriptz] Saved hotkey to config file")

    # Get Krita instances
    app = Krita.instance()
    window = app.activeWindow()
    if not window:
        print("[RunScriptz] No active window for hotkey assignment")
        return False

    action_id = get_action_id_for_key(script_name)

    # Always create/recreate the action to ensure it's properly registered
    try:
        # Create the action in Krita's action system
        action = window.createAction(action_id, f"RunScriptz: {script_name}", "tools/scripts")

        if action:
            print(f"[RunScriptz] Created/updated action: {action_id}")

            # Connect the script execution with proper closure
            if script_path and os.path.exists(script_path):
                def create_script_runner(path):
                    return lambda: run_script_from_path(path)

                action.triggered.connect(create_script_runner(script_path))
                print(f"[RunScriptz] Connected action to script: {script_path}")

            # Set the shortcut
            shortcut = QKeySequence(key_sequence)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ApplicationShortcut)
            action.setAutoRepeat(False)

            print(f"[RunScriptz] Set shortcut: {key_sequence}")

            # CRITICAL: Write to Krita's kritarc file directly
            try:
                # This writes to Krita's main configuration file
                app.writeSetting("Shortcuts", action_id, key_sequence)
                print(f"[RunScriptz] Saved shortcut to Krita's kritarc: {action_id} = {key_sequence}")
            except Exception as e:
                print(f"[RunScriptz] Could not save to kritarc: {e}")

            return True
        else:
            print(f"[RunScriptz] Failed to create action")
            return False

    except Exception as e:
        print(f"[RunScriptz] Error creating action: {e}")
        return False

def remove_hotkey_from_script(script_name):
    """Remove hotkey from a specific script"""
    print(f"[RunScriptz] Removing hotkey from '{script_name}'")

    hotkeys = load_hotkeys()
    if script_name in hotkeys:
        del hotkeys[script_name]
        save_hotkeys(hotkeys)
        print(f"[RunScriptz] Removed hotkey from config file")

        # Update the action if it exists
        app = Krita.instance()
        window = app.activeWindow()
        if not window:
            return

        action_id = get_action_id_for_key(script_name)

        # Try to find and update the action
        try:
            action = window.action(action_id)
            if action:
                action.setShortcut("")
                print(f"[RunScriptz] Cleared shortcut from action")

                # Remove from Krita settings
                try:
                    app.writeSetting("Shortcuts", action_id, "")
                    print(f"[RunScriptz] Cleared shortcut from Krita kritarc")
                except Exception as e:
                    print(f"[RunScriptz] Could not clear Krita setting: {e}")
        except Exception as e:
            print(f"[RunScriptz] Error updating action: {e}")

def restore_hotkeys_from_krita_settings(scripts_folder):
    """Restore hotkeys from Krita's own settings system"""
    if not scripts_folder or not os.path.isdir(scripts_folder):
        return

    print("[RunScriptz] Attempting to restore hotkeys from Krita settings...")
    app = Krita.instance()
    if not app:
        return

    hotkeys = load_hotkeys()
    restored_count = 0

    for script_key, script_path in get_all_scripts(scripts_folder):
        
        action_id = get_action_id_for_key(script_key)
        try:
            # Check if Krita has a saved shortcut for this script in the Shortcuts section
            saved_shortcut = app.readSetting("Shortcuts", action_id, "")
            if saved_shortcut and saved_shortcut != "":
                hotkeys[script_key] = saved_shortcut
                restored_count += 1
                print(f"[RunScriptz] Restored hotkey from Krita kritarc: {script_key} -> {saved_shortcut}")
        except Exception as e:
            print(f"[RunScriptz] Error reading Krita shortcut setting for {script_key}: {e}")

    if restored_count > 0:
        save_hotkeys(hotkeys)
        print(f"[RunScriptz] Restored {restored_count} hotkeys from Krita settings")
        return True
    else:
        print("[RunScriptz] No hotkeys found in Krita settings")
        return False

def debug_krita_shortcuts():
    """Debug function to see what shortcuts are in Krita's settings"""
    app = Krita.instance()
    if not app:
        return "[RunScriptz] No Krita instance for debug\n"

    log = []
    log.append("[RunScriptz] === DEBUG: Krita Shortcuts ===")

    # Try to read some known shortcuts to see the format
    try:
        # Check if we can read any existing shortcuts
        test_shortcuts = [
            "file_new", "file_open", "file_save", "edit_undo", "edit_redo"
        ]

        for shortcut_name in test_shortcuts:
            try:
                value = app.readSetting("Shortcuts", shortcut_name, "NOT_FOUND")
                if value != "NOT_FOUND":
                    log.append(f"[RunScriptz] Found shortcut: {shortcut_name} = {value}")
                    break
            except:
                pass

        # Check our own shortcuts
        log.append("[RunScriptz] Checking RunScriptz shortcuts:")
        for i in range(5):  # Check a few potential script names
            action_id = f"run_scriptz_test_script_{i}.py"
            try:
                value = app.readSetting("Shortcuts", action_id, "")
                if value:
                    log.append(f"[RunScriptz] Found our shortcut: {action_id} = {value}")
            except Exception as e:
                log.append(f"[RunScriptz] Error reading {action_id}: {e}")

    except Exception as e:
        log.append(f"[RunScriptz] Debug error: {e}")

    log.append("[RunScriptz] === END DEBUG ===")
    return "\n".join(log)
