from krita import Krita, Extension, DockWidget, DockWidgetFactory, DockWidgetFactoryBase
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QListWidget, QListWidgetItem, QShortcut, QDialog, QLineEdit, QLabel, QDialogButtonBox, QMenu,
    QScrollArea, QGridLayout, QFrame, QMessageBox, QTextEdit, QApplication,
    QTreeWidget, QTreeWidgetItem, QSizePolicy
)
from PyQt5.QtGui import QKeySequence, QIcon, QKeyEvent
from PyQt5.QtCore import Qt, QTimer, QObject, QEvent
import os
import importlib.util
import json
import subprocess
from . import actions

CONFIG_FILE = os.path.join(
    Krita.instance().getAppDataLocation() or os.path.expanduser("~"),
    "run_scriptz_config.json"
)

HOTKEY_FILE = os.path.join(
    Krita.instance().getAppDataLocation() or os.path.expanduser("~"),
    "run_scriptz_hotkeys.json"
)


class HotkeyDialog(QDialog):
    """Dialog to capture a key combination"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assign Hotkey")
        self.setModal(True)
        self.key_sequence = None
        

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Press the desired key combination"))

        self.line_edit = QLineEdit()
        self.line_edit.setReadOnly(True)
        layout.addWidget(self.line_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def keyPressEvent(self, event):
        # Ignore modifier keys alone
        if event.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            event.accept()
            return
            
        # Use QKeySequence to properly format the key combination
        key_seq = QKeySequence(event.modifiers() | event.key())
        full_seq = key_seq.toString()
        
        # Handle special cases for better compatibility
        if full_seq == "":
            # Fallback to manual formatting for special keys
            modifiers = []
            if event.modifiers() & Qt.ControlModifier:
                modifiers.append("Ctrl")
            if event.modifiers() & Qt.AltModifier:
                modifiers.append("Alt")
            if event.modifiers() & Qt.ShiftModifier:
                modifiers.append("Shift")
            if event.modifiers() & Qt.MetaModifier:
                modifiers.append("Meta")
            
            key_name = QKeySequence(event.key()).toString()
            if key_name:
                full_seq = "+".join(modifiers + [key_name])
        
        if full_seq:
            self.line_edit.setText(full_seq)
            self.key_sequence = full_seq
        
        event.accept()

    def get_key_sequence(self):
        return self.key_sequence

class RunScriptzShortcutFilter(QObject):
    """
    Event filter to catch hotkeys globally on the main window.
    This bypasses Krita's action shortcut system which can be unreliable.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hotkeys = {}
        self.load_hotkeys()
        
    def load_hotkeys(self):
        self.hotkeys = actions.load_hotkeys()
        
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            # Create a key sequence from the event
            key = event.key()
            modifiers = event.modifiers()
            
            # Ignore modifier-only presses
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                return False

            # Use QKeySequence to generate a standard string representation
            # We combine modifiers and key to get "Ctrl+Shift+A" style string
            seq = QKeySequence(modifiers | key)
            seq_str = seq.toString()
            
            # print(f"[RunScriptz] Key Pressed: {seq_str}") # Uncomment for verbose heavy debugging
            
            # Check for docker toggle shortcut (Ctrl+Shift+D)
            if seq_str == "Ctrl+Shift+D":
                print(f"[RunScriptz] Docker toggle shortcut pressed: {seq_str}")
                self.toggle_docker()
                return True  # Consume event
            
            # Check for matches in our hotkeys
            for script_name, shortcut_str in self.hotkeys.items():
                if seq_str == shortcut_str:
                    print(f"[RunScriptz] Global Filter Caught MATCH: {seq_str} -> {script_name}")
                    
                    # Run the script
                    script_path = os.path.join(self.get_scripts_folder(), script_name)
                    if os.path.exists(script_path):
                        actions.run_script_from_path(script_path)
                        return True # Consume event
                    
        return super().eventFilter(obj, event)

    def get_scripts_folder(self):
        # Helper to get config
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    return cfg.get("scripts_folder", "")
        except:
            pass
        return ""
    
    def toggle_docker(self):
        """Toggle the RunScriptz docker visibility"""
        try:
            for docker in Krita.instance().dockers():
                if getattr(docker, "objectName", lambda: "")() == "RunScriptz":
                    docker.setVisible(not docker.isVisible())
                    if docker.isVisible():
                        docker.raise_()
                    print(f"[RunScriptz] Docker toggled: {'visible' if docker.isVisible() else 'hidden'}")
                    return
        except Exception as e:
            print(f"[RunScriptz] Error toggling docker: {e}")

class DebugInfoDialog(QDialog):
    """Dialog to show debug info with copy button"""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RunScriptz Debug Info")
        self.setModal(True)
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setText(text)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        
        self.btn_copy = QPushButton("Copy to Clipboard")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        btn_layout.addWidget(self.btn_copy)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        self.btn_copy.setText("Copied!")
        QTimer.singleShot(2000, lambda: self.btn_copy.setText("Copy to Clipboard"))


class RunScriptzDock(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RunScriptz")
        self.setObjectName("RunScriptz")

        # Main layout
        self.main_widget = QWidget()
        self.layout = QVBoxLayout(self.main_widget)

        # Mode switch button
        self.btn_mode = QPushButton("📋 List Mode")
        self.btn_mode.clicked.connect(self.toggle_mode)
        self.btn_mode.setToolTip("Switch between List and Button modes")
        self.layout.addWidget(self.btn_mode)

        # Script container (will hold either list or buttons)
        self.script_container = QWidget()
        self.script_layout = QVBoxLayout(self.script_container)
        self.script_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.script_container)

        # Script list (for list mode)
        self.script_list = QTreeWidget()
        self.script_list.setHeaderHidden(True)
        self.script_list.itemClicked.connect(self.run_selected_script)
        self.script_list.itemDoubleClicked.connect(self.run_selected_script)
        self.script_list.installEventFilter(self)
        self.script_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.script_list.customContextMenuRequested.connect(self.show_context_menu)
        self.script_layout.addWidget(self.script_list)

        # Script buttons container (for button mode)
        self.script_buttons_container = QScrollArea()
        self.script_buttons_widget = QWidget()
        self.script_buttons_layout = QVBoxLayout(self.script_buttons_widget)
        self.script_buttons_layout.setSpacing(0) # No spacing between buttons
        self.script_buttons_layout.setContentsMargins(0, 0, 0, 0) # No margins
        self.script_buttons_container.setWidget(self.script_buttons_widget)
        self.script_buttons_container.setWidgetResizable(True)
        self.script_buttons_container.setVisible(False)
        self.script_layout.addWidget(self.script_buttons_container)

        # Bottom buttons layout
        self.bottom_layout = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self.run_selected_script)
        self.btn_run.setToolTip("Run selected script")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_scripts)
        self.btn_refresh.setToolTip("Refresh script list")
        self.btn_folder = QPushButton("Folder")
        self.btn_folder.clicked.connect(self.choose_folder)
        self.btn_folder.setToolTip("Choose scripts folder")

        # Second row of buttons
        self.bottom_layout2 = QHBoxLayout()
        self.btn_register_hotkeys = QPushButton("Register Hotkeys")
        self.btn_register_hotkeys.clicked.connect(self.force_register_hotkeys)
        self.btn_register_hotkeys.setToolTip("Force re-register all hotkeys")

        self.btn_debug_shortcuts = QPushButton("Debug Shortcuts")
        self.btn_debug_shortcuts.clicked.connect(self.debug_shortcuts)
        self.btn_debug_shortcuts.setToolTip("Debug shortcut information")

        self.bottom_layout.addWidget(self.btn_run)
        self.bottom_layout.addWidget(self.btn_refresh)
        self.bottom_layout.addWidget(self.btn_folder)
        self.bottom_layout2.addWidget(self.btn_register_hotkeys)
        self.bottom_layout2.addWidget(self.btn_debug_shortcuts)

        self.layout.addLayout(self.bottom_layout)
        self.layout.addLayout(self.bottom_layout2)

        self.setWidget(self.main_widget)

        # Shortcut Alt+R for run selected
        self.shortcut_run = QShortcut(QKeySequence("Alt+R"), self.main_widget)
        self.shortcut_run.activated.connect(self.run_selected_script)

        # Allow unlimited resizing - no minimum size restrictions
        self.setMinimumWidth(1)
        self.setMinimumHeight(1)

        # Internal
        self.scripts_folder = ""
        self.hotkeys = {}
        self.button_mode = False
        self.script_buttons = []
        self.load_config()
        self.load_hotkeys()

        # Try to restore hotkeys from Krita's settings first
        if self.scripts_folder:
            actions.restore_hotkeys_from_krita_settings(self.scripts_folder)

        self.refresh_scripts()

        # AUTO-REGISTER HOTKEYS: Set up a timer to automatically register hotkeys
        # 1 second after the dock is created (when Krita is fully loaded)
        self.auto_register_timer = QTimer()
        self.auto_register_timer.setSingleShot(True)
        self.auto_register_timer.timeout.connect(self.auto_register_hotkeys)
        self.auto_register_timer.start(1000)  # 1 second delay
        print("[RunScriptz] Auto-register timer started - will register hotkeys in 1 second")

    def canvasChanged(self, canvas):
        pass

    def auto_register_hotkeys(self):
        """Automatically register hotkeys 1 second after dock creation"""
        print("[RunScriptz] Auto-registering hotkeys...")
        if self.scripts_folder and os.path.isdir(self.scripts_folder):
            try:
                # Register hotkeys without showing message boxes
                print("[RunScriptz] Auto-registering hotkeys for scripts folder...")
                actions.register_actions_with_krita(self.scripts_folder, force_create_all=True)

                # Also trigger extension registration
                extension = self.get_extension_instance()
                if extension:
                    extension.start_delayed_hotkey_registration()

                print("[RunScriptz] Auto-registration completed successfully")
            except Exception as e:
                print(f"[RunScriptz] Auto-registration failed: {e}")
                # Try again in 2 seconds if it failed
                print("[RunScriptz] Retrying auto-registration in 2 seconds...")
                QTimer.singleShot(2000, self.auto_register_hotkeys)
        else:
            print("[RunScriptz] No scripts folder configured for auto-registration")

    # --- Mode switching ---
    def toggle_mode(self):
        """Toggle between list and button modes"""
        self.button_mode = not self.button_mode
        if self.button_mode:
            self.btn_mode.setText("🔘 Button Mode")
            self.script_list.setVisible(False)
            self.script_buttons_container.setVisible(True)
            self.refresh_script_buttons()
        else:
            self.btn_mode.setText("📋 List Mode")
            self.script_list.setVisible(True)
            self.script_buttons_container.setVisible(False)

    def refresh_script_buttons(self):
        """Refresh script buttons in button mode"""
        # Clear existing buttons
        for button in self.script_buttons:
            button.deleteLater()
        self.script_buttons.clear()
        
        # Clear layout fully
        while self.script_buttons_layout.count():
            child = self.script_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.spacerItem():
                pass
        
        if not self.scripts_folder or not os.path.isdir(self.scripts_folder):
            return
        
        # Load hotkeys to show indicators
        hotkeys = actions.load_hotkeys()
        
        for fname in sorted(os.listdir(self.scripts_folder)):
            if not fname.endswith(".py"):
                continue
            
            # Create button
            button = QPushButton(fname)
            # Ignored horizontal allows shrinking indefinitely (good for <250px)
            # Fixed vertical prevents "too big" expanding
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            
            # Add hotkey indicator if available
            if fname in hotkeys:
                button.setText(f"{fname} [{hotkeys[fname]}]")
                button.setToolTip(f"Script: {fname}\nHotkey: {hotkeys[fname]}\nClick to run")
            else:
                button.setToolTip(f"Script: {fname}\nClick to run")
            
            # Connect button click with proper closure
            script_path = os.path.join(self.scripts_folder, fname)
            def create_button_handler(path):
                return lambda checked: self.run_script(path)
            button.clicked.connect(create_button_handler(script_path))
            
            # Add context menu for hotkeys
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos, name=fname: self.show_button_context_menu(pos, name))
            
            self.script_buttons_layout.addWidget(button)
            self.script_buttons.append(button)
            
        # Add stretch at the end to keep buttons packed at top
        self.script_buttons_layout.addStretch()

    def show_button_context_menu(self, pos, script_name):
        """Show context menu for script buttons"""
        button = self.sender()
        menu = QMenu()
        
        # Check if script already has a hotkey
        hotkeys = actions.load_hotkeys()
        has_hotkey = script_name in hotkeys
        
        assign_action = menu.addAction("Assign Hotkey")
        reveal_action = menu.addAction("Reveal in Explorer")
        
        if has_hotkey:
            remove_action = menu.addAction(f"Remove Hotkey ({hotkeys[script_name]})")
        else:
            remove_action = None
        
        action = menu.exec_(button.mapToGlobal(pos))
        if action == assign_action:
            self.assign_hotkey(script_name)
        elif action == reveal_action:
            self.reveal_in_explorer(script_name)
        elif action == remove_action and has_hotkey:
            self.remove_hotkey(script_name)

    # --- Folder ---
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Scripts Folder")
        if folder:
            self.scripts_folder = folder
            self.save_config()
            self.refresh_scripts()
            self.register_hotkeys()

    # --- Scripts ---
    def refresh_scripts(self):
        """Refresh scripts in both list and button modes"""
        # Refresh list mode
        self.script_list.clear() # Clears the QTreeWidget
        if not self.scripts_folder or not os.path.isdir(self.scripts_folder):
            return
        
        # Load hotkeys to show indicators
        hotkeys = actions.load_hotkeys()
        
        # 1. Add files in root folder
        root_files = []
        try:
            for fname in sorted(os.listdir(self.scripts_folder)):
                fpath = os.path.join(self.scripts_folder, fname)
                if os.path.isfile(fpath) and fname.endswith(".py"):
                    root_files.append(fname)
        except Exception:
            pass

        for fname in root_files:
            item = QTreeWidgetItem(self.script_list)
            
            # Key for hotkey lookup (filename for root files)
            hotkey_key = fname
            
            display_text = fname
            if hotkey_key in hotkeys:
                display_text = f"{fname} [{hotkeys[hotkey_key]}]"
                item.setToolTip(0, f"Hotkey: {hotkeys[hotkey_key]}")
            
            item.setText(0, display_text)
            # Store relative path or key for hotkey logic
            item.setData(0, Qt.UserRole, fname) 
            # Store full path for running
            item.setData(0, Qt.UserRole + 1, os.path.join(self.scripts_folder, fname))
        
        # 2. Add subfolders and their scripts
        try:
            for dname in sorted(os.listdir(self.scripts_folder)):
                dpath = os.path.join(self.scripts_folder, dname)
                if os.path.isdir(dpath) and not dname.startswith('.'):
                    # Check if there are python files inside
                    sub_files = []
                    try:
                        for fname in sorted(os.listdir(dpath)):
                            if fname.endswith(".py"):
                                sub_files.append(fname)
                    except:
                        continue
                        
                    if sub_files:
                        # Create Category Item
                        category_item = QTreeWidgetItem(self.script_list)
                        category_item.setText(0, dname)
                        # Make category slightly different visual if needed, or just bold
                        font = category_item.font(0)
                        font.setBold(True)
                        category_item.setFont(0, font)
                        
                        category_item.setExpanded(True)
                        
                        for fname in sub_files:
                            script_item = QTreeWidgetItem(category_item)
                            
                            # Construct relative path for hotkey key: "Subfolder/script.py"
                            # We normalize to forward slashes for consistency in JSON
                            rel_path = f"{dname}/{fname}"
                            fpath = os.path.join(dpath, fname)
                            
                            hotkey_key = rel_path
                            
                            display_text = fname
                            if hotkey_key in hotkeys:
                                display_text = f"{fname} [{hotkeys[hotkey_key]}]"
                                script_item.setToolTip(0, f"Hotkey: {hotkeys[hotkey_key]}")
                            
                            script_item.setText(0, display_text)
                            script_item.setData(0, Qt.UserRole, rel_path) # Relative path
                            script_item.setData(0, Qt.UserRole + 1, fpath) # Full path
                            
        except Exception as e:
            print(f"[RunScriptz] Error scanning subfolders: {e}")
        
        # Refresh button mode if active
        if self.button_mode:
            self.refresh_script_buttons()

    def run_selected_script(self):
        item = self.script_list.currentItem()
        if item:
            # Check if it has a path data (it's a script)
            path = item.data(0, Qt.UserRole + 1)
            if path:
                self.run_script(path)
            # Else it's likely a category folder, do nothing or toggle expand
            elif item.childCount() > 0:
                item.setExpanded(not item.isExpanded())

    def run_script(self, path):
        if not os.path.exists(path):
            print(f"[RunScriptz] Script not found: {path}")
            return
        try:
            spec = importlib.util.spec_from_file_location("run_scriptz_external", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[RunScriptz] Error running {path}: {e}")

    # --- Event filter ---
    def eventFilter(self, source, event):
        if source == self.script_list and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self.run_selected_script()
                return True
        return super().eventFilter(source, event)

    # --- Context menu for hotkeys ---
    # --- Context menu for hotkeys ---
    def show_context_menu(self, pos):
        item = self.script_list.itemAt(pos)
        if not item:
            return
        
        # Get relative path (script name/key) from data
        script_key = item.data(0, Qt.UserRole)
        full_path = item.data(0, Qt.UserRole + 1)
        
        if not script_key or not full_path:
            return # Probably a category folder
        
        menu = QMenu()
        
        # Check if script already has a hotkey
        hotkeys = actions.load_hotkeys()
        has_hotkey = script_key in hotkeys
        
        assign_action = menu.addAction("Assign Hotkey")
        reveal_action = menu.addAction("Reveal in Explorer")
        
        if has_hotkey:
            remove_action = menu.addAction(f"Remove Hotkey ({hotkeys[script_key]})")
        else:
            remove_action = None
        
        action = menu.exec_(self.script_list.viewport().mapToGlobal(pos))
        if action == assign_action:
            self.assign_hotkey(script_key) # script_key is rel_path
        elif action == reveal_action:
            self.reveal_in_explorer_path(full_path)
        elif action == remove_action and has_hotkey:
            self.remove_hotkey(script_key)

    def assign_hotkey(self, script_name):
        """Assign hotkey to a script using a dialog"""
        dialog = HotkeyDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            key_sequence = dialog.get_key_sequence()
            if key_sequence:
                # Calculate full path. 
                # script_name is now treated as relative path (key)
                # We need to construct absolute path for execution closure.
                script_path = os.path.join(self.scripts_folder, script_name)
                # If script_name has /, join works fine on windows mostly, but let's be careful
                # script_name could be "Sub/foo.py". os.path.join(root, "Sub/foo.py") -> root\Sub/foo.py -> works
                
                # Use the actions module to assign the hotkey
                success = actions.assign_hotkey_to_script(script_name, key_sequence, script_path)
                
                if success:
                    # Re-register actions to update shortcuts
                    self.register_hotkeys()
                    
                    # Refresh the script list to show the hotkey indicator
                    self.refresh_scripts()

                else:
                    QMessageBox.warning(self, "Hotkey Assignment Failed",
                        f"Failed to assign hotkey '{key_sequence}' to '{script_name}'\n"
                        "Check the console for error details.")

    def remove_hotkey(self, script_name):
        """Remove hotkey from a script"""
        actions.remove_hotkey_from_script(script_name)
        
        # Re-register actions to update shortcuts
        self.register_hotkeys()
        
        # Refresh the script list to remove the hotkey indicator
        self.refresh_scripts()

        QMessageBox.information(self, "Hotkey Removed",
            f"Hotkey removed from '{script_name}'")

    def reveal_in_explorer(self, script_name):
        """Reveal the script file in Windows Explorer (List Mode -> uses Helper)"""
        # This was the old list mode one, but we are upgrading.
        # Button mode still calls this with script_name (filename in root).
        # We need to support old behavior for button mode or fix it.
        # For button mode (flat list), script_name is filename.
        
        if not self.scripts_folder:
            return
        
        # If script_name contains /, it's a relative path (subfolder)
        # But button mode currently only supports root files, so script_name is just filename.
        # If we update button mode, we should pass full path.
        
        path = os.path.join(self.scripts_folder, script_name)
        self.reveal_in_explorer_path(path)
        
    def reveal_in_explorer_path(self, path):
        """Helper to reveal specific path"""
        path = os.path.normpath(path)
        
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"Script file not found:\n{path}")
            return
            
        try:
            # Use explorer /select, <path> to highlight the file
            subprocess.Popen(f'explorer /select,"{path}"')
        except Exception as e:
            print(f"[RunScriptz] Error revealing file: {e}")
            QMessageBox.warning(self, "Error", f"Could not reveal file:\n{e}")

    def test_hotkey_assignment(self):
        """Test hotkey assignment with debug output"""
        if not self.scripts_folder:
            QMessageBox.warning(self, "No Scripts Folder", "Please choose a scripts folder first.")
            return
        
        # Test with a simple key sequence
        test_script = "debug_hotkey.py"
        test_key = "Ctrl+1"
        
        print(f"[RunScriptz] Testing hotkey assignment...")
        print(f"[RunScriptz] Script: {test_script}")
        print(f"[RunScriptz] Key: {test_key}")
        print(f"[RunScriptz] Scripts folder: {self.scripts_folder}")
        
        script_path = os.path.join(self.scripts_folder, test_script)
        
        # Create debug script if it doesn't exist
        if not os.path.exists(script_path):
            debug_script_content = '''#!/usr/bin/env python3
"""
Debug script for hotkey testing
"""

def main():
    """Test function for hotkey debugging"""
    print("=== Hotkey Debug Test ===")
    print("This script is running via hotkey!")
    
    # Test Krita API access
    try:
        from krita import Krita
        app = Krita.instance()
        if app:
            print("✓ Krita instance found")
            doc = app.activeDocument()
            if doc:
                print(f"✓ Active document: {doc.name()}")
            else:
                print("⚠ No active document")
        else:
            print("✗ No Krita instance found")
    except Exception as e:
        print(f"✗ Error accessing Krita API: {e}")
    
    print("=== End Debug Test ===")

if __name__ == "__main__":
    main()
'''
            try:
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(debug_script_content)
                print(f"[RunScriptz] Created debug script: {script_path}")
            except Exception as e:
                print(f"[RunScriptz] Error creating debug script: {e}")
        
        print(f"[RunScriptz] Script path: {script_path}")
        print(f"[RunScriptz] Script exists: {os.path.exists(script_path)}")
        
        success = actions.assign_hotkey_to_script(test_script, test_key, script_path)

        if success:
            QMessageBox.information(self, "Test Successful", 
                f"Successfully assigned '{test_key}' to '{test_script}'\n"
                "Check the console for details.")
        else:
            QMessageBox.warning(self, "Test Failed", 
                f"Failed to assign '{test_key}' to '{test_script}'\n"
                "Check the console for error details.")

    def register_hotkeys(self):
        """Register hotkeys using the actions system"""
        if not self.scripts_folder:
            return

        print("[RunScriptz] Dock widget registering hotkeys...")
        # Use the actions module to register all script actions (force create all)
        actions.register_actions_with_krita(self.scripts_folder, force_create_all=True)

        # Also trigger the extension's registration system
        extension = self.get_extension_instance()
        if extension:
            extension.start_delayed_hotkey_registration()

    def get_extension_instance(self):
        """Get the extension instance"""
        app = Krita.instance()
        if app:
            for extension in app.extensions():
                if isinstance(extension, RunScriptzExtension):
                    return extension
        return None

    def force_register_hotkeys(self):
        """Force re-registration of all hotkeys"""
        if not self.scripts_folder:
            QMessageBox.warning(self, "No Scripts Folder", "Please choose a scripts folder first.")
            return

        try:
            # Direct registration (force create all actions)
            actions.register_actions_with_krita(self.scripts_folder, force_create_all=True)

            # Also trigger extension registration
            extension = self.get_extension_instance()
            if extension:
                extension.start_delayed_hotkey_registration()

        except Exception as e:
            QMessageBox.warning(self, "Registration Error",
                f"Error during hotkey registration:\n{str(e)}\n\n"
                "Check the console for more details.")

    def debug_shortcuts(self):
        """Debug shortcut information"""
        log = []
        log.append("=== RunScriptz Debug Info ===")
        
        # Debug our JSON file
        hotkeys = actions.load_hotkeys()
        log.append(f"[JSON] Hotkeys file: {len(hotkeys)} entries")
        for script, key in hotkeys.items():
            log.append(f"  {script} -> {key}")

        # Debug Krita's shortcuts
        log.append("\n[Krita Settings]")
        log.append(actions.debug_krita_shortcuts())

        # Debug current actions
        log.append("\n[Current Window Actions (via Krita.instance().action())]")
        app = Krita.instance()
        # We check Krita.instance().action() which is the reliable way to find actions
        for script in hotkeys.keys():
            action_id = f"run_scriptz_{script}"
            try:
                action = app.action(action_id)
                if action:
                    shortcut = action.shortcut().toString()
                    log.append(f"  Action {action_id}: FOUND, shortcut = '{shortcut}'")
                    if action.isEnabled():
                        log.append(f"    - Enabled: Yes")
                    else:
                        log.append(f"    - Enabled: No")
                else:
                    log.append(f"  Action {action_id}: NOT FOUND in Krita.instance().action()")
            except Exception as e:
                log.append(f"  Action {action_id}: ERROR - {e}")
        
        log.append("\n=== End Debug Info ===")
        
        full_log = "\n".join(log)
        print(full_log) # Still print to console just in case

        # Show dialog
        dialog = DebugInfoDialog(full_log, self)
        dialog.exec_()

    # --- Config ---
    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.scripts_folder = cfg.get("scripts_folder", "")
        except Exception:
            self.scripts_folder = ""

    def save_config(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"scripts_folder": self.scripts_folder}, f, indent=2)
        except Exception:
            pass

    def load_hotkeys(self):
        try:
            if os.path.exists(HOTKEY_FILE):
                with open(HOTKEY_FILE, "r", encoding="utf-8") as f:
                    self.hotkeys = json.load(f)
        except Exception:
            self.hotkeys = {}

    def save_hotkeys(self):
        try:
            os.makedirs(os.path.dirname(HOTKEY_FILE), exist_ok=True)
            with open(HOTKEY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.hotkeys, f, indent=2)
        except Exception:
            pass


class RunScriptzExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self.dock_factory = None
        self.scripts_folder = ""
        self.hotkey_registration_timer = None
        self.registration_attempts = 0
        self.max_registration_attempts = 10
        self.load_config()

        # Try to create actions immediately if we have a scripts folder
        print("[RunScriptz] Extension __init__ - attempting immediate action creation...")
        # REMOVED: potentially creating windowless actions that conflict
        # if self.scripts_folder:
        #    actions.ensure_actions_exist_on_startup()

    def setup(self):
        self.dock_factory = DockWidgetFactory(
            "RunScriptz",
            DockWidgetFactoryBase.DockLeft,
            RunScriptzDock
        )
        Krita.instance().addDockWidgetFactory(self.dock_factory)

        # CRITICAL: Try to ensure actions exist immediately in setup
        print("[RunScriptz] Extension setup - attempting immediate action creation...")
        # REMOVED: relying on createActions to provide the window
        # actions.ensure_actions_exist_on_startup()

        # Start delayed hotkey registration as backup
        self.start_delayed_hotkey_registration()

        # BACKUP: Set up a timer to auto-register hotkeys even if dock isn't opened
        # This ensures hotkeys work even if user never opens the dock
        self.backup_register_timer = QTimer()
        self.backup_register_timer.setSingleShot(True)
        self.backup_register_timer.timeout.connect(self.backup_auto_register)
        self.backup_register_timer.start(3000)  # 3 seconds after extension setup
        print("[RunScriptz] Backup auto-register timer started - will register in 3 seconds")

    def load_config(self):
        """Load configuration to get scripts folder"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.scripts_folder = cfg.get("scripts_folder", "")
        except Exception:
            self.scripts_folder = ""

    def start_delayed_hotkey_registration(self):
        """Start delayed hotkey registration with multiple attempts"""
        if not self.scripts_folder or not os.path.isdir(self.scripts_folder):
            print("[RunScriptz] No scripts folder configured, skipping hotkey registration")
            return

        print("[RunScriptz] Starting delayed hotkey registration...")
        self.registration_attempts = 0
        self.attempt_hotkey_registration()

    def attempt_hotkey_registration(self):
        """Attempt to register hotkeys with retry logic"""
        self.registration_attempts += 1
        print(f"[RunScriptz] Hotkey registration attempt {self.registration_attempts}/{self.max_registration_attempts}")

        app = Krita.instance()
        window = app.activeWindow() if app else None

        if window:
            print("[RunScriptz] Active window found, registering hotkeys...")
            try:
                actions.register_actions_with_krita(self.scripts_folder)
                print("[RunScriptz] Hotkey registration completed successfully")
                return  # Success, stop trying
            except Exception as e:
                print(f"[RunScriptz] Error during hotkey registration: {e}")
        else:
            print("[RunScriptz] No active window found yet")

        # If we haven't succeeded and haven't reached max attempts, try again
        if self.registration_attempts < self.max_registration_attempts:
            delay = min(2000 * self.registration_attempts, 10000)  # Increasing delay, max 10 seconds
            print(f"[RunScriptz] Retrying in {delay/1000} seconds...")
            self.hotkey_registration_timer = QTimer()
            self.hotkey_registration_timer.setSingleShot(True)
            self.hotkey_registration_timer.timeout.connect(self.attempt_hotkey_registration)
            self.hotkey_registration_timer.start(delay)
        else:
            print("[RunScriptz] Max registration attempts reached, giving up")

    def backup_auto_register(self):
        """Backup auto-registration that runs even if dock isn't opened"""
        print("[RunScriptz] Backup auto-registration triggered...")
        if self.scripts_folder and os.path.isdir(self.scripts_folder):
            try:
                print("[RunScriptz] Running backup hotkey registration...")
                actions.register_actions_with_krita(self.scripts_folder, force_create_all=True)
                print("[RunScriptz] Backup auto-registration completed")
            except Exception as e:
                print(f"[RunScriptz] Backup auto-registration failed: {e}")
        else:
            print("[RunScriptz] No scripts folder for backup registration")

    def register_startup_hotkeys(self):
        """Register hotkeys when Krita starts up - legacy method"""
        if self.scripts_folder and os.path.isdir(self.scripts_folder):
            # Use the actions module to register all script actions
            actions.register_actions_with_krita(self.scripts_folder)

    def createActions(self, window):
        # Menu action to show dock
        show_action = window.createAction("run_scriptz_show", "Show RunScriptz", "tools/scripts")
        show_action.triggered.connect(self.show_dock)

        # CRITICAL: Ensure all script actions with hotkeys exist immediately
        print("[RunScriptz] Window created - installing global event filter...")
        
        # Strategy C: Global Event Filter on QApplication
        # This catches keys even if the main window focus is weird (e.g. on a docker)
        if not hasattr(self, 'shortcut_filter'):
            self.shortcut_filter = RunScriptzShortcutFilter(QApplication.instance())
            QApplication.instance().installEventFilter(self.shortcut_filter)
            print("[RunScriptz] Global event filter installed on QApplication")
        
        # We still create the actions for visual feedback (menu items)
        # But we do it once, cleanly.
        actions.ensure_actions_exist_on_startup(window)

    def create_script_actions_immediately(self, window):
        """Create all script actions immediately when Krita window is created"""
        try:
            # First restore hotkeys from Krita's settings
            actions.restore_hotkeys_from_krita_settings(self.scripts_folder)

            # Load hotkeys (now updated from Krita settings)
            hotkeys = actions.load_hotkeys()

            print(f"[RunScriptz] Creating actions for {len(hotkeys)} scripts with hotkeys")

            # Create actions for all scripts that have hotkeys
            for filename in os.listdir(self.scripts_folder):
                if not filename.endswith(".py"):
                    continue

                script_path = os.path.join(self.scripts_folder, filename)
                action_id = f"run_scriptz_{filename}"
                action_text = f"RunScriptz: {filename}"

                try:
                    # Create the action
                    action = window.createAction(action_id, action_text, "tools/scripts")

                    if action:
                        # Connect to script execution with proper closure
                        def create_action_handler(path):
                            return lambda: actions.run_script_from_path(path)
                        action.triggered.connect(create_action_handler(script_path))

                        # Set shortcut if available
                        if filename in hotkeys:
                            shortcut = QKeySequence(hotkeys[filename])
                            action.setShortcut(shortcut)
                            action.setShortcutContext(Qt.ApplicationShortcut)
                            print(f"[RunScriptz] Created action with shortcut: {filename} -> {hotkeys[filename]}")
                        else:
                            print(f"[RunScriptz] Created action without shortcut: {filename}")

                except Exception as e:
                    print(f"[RunScriptz] Error creating action for {filename}: {e}")

            print("[RunScriptz] Finished creating script actions")

        except Exception as e:
            print(f"[RunScriptz] Error in create_script_actions_immediately: {e}")

    def show_dock(self):
        for d in Krita.instance().dockers():
            if getattr(d, "objectName", lambda: "")() == "RunScriptz":
                d.setVisible(True)
                d.raise_()
                return
