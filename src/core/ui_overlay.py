"""Transparent overlay UI for the AI Agent."""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, List, Dict, Any
import threading
from datetime import datetime
from collections import deque
import time


class AgentOverlayUI:
    """Always-on-top transparent overlay UI for monitoring agent activity."""
    
    def __init__(self, opacity: float = 0.90):
        """Initialize the overlay UI.
        
        Args:
            opacity: Window opacity (0.0 to 1.0)
        """
        self.root: Optional[tk.Tk] = None  # Will be initialized in thread
        self.opacity = opacity
        self.is_visible = True
        self.is_minimized = False
        self._initialized = False
        
        # UI components
        self.status_label: Optional[tk.Label] = None
        self.task_label: Optional[tk.Label] = None
        self.step_label: Optional[tk.Label] = None
        self.log_text: Optional[scrolledtext.ScrolledText] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.content_frame: Optional[tk.Frame] = None
        self.step_detail_label: Optional[tk.Label] = None
        self.toast_label: Optional[tk.Label] = None
        self._toast_after_id: Optional[str] = None
        
        # State
        self.current_task: str = "Idle"
        self.current_step: str = ""
        self.total_steps: int = 0
        self.completed_steps: int = 0
        self.logs: deque = deque(maxlen=100)  # Keep last 100 log entries
        
        # Position
        self.window_width = 400
        self.window_height = 500
        self.minimized_height = 80
        
        # Thread safety
        self.ui_thread: Optional[threading.Thread] = None
        self.running = False
    
    def start(self):
        """Start the UI in a separate thread."""
        if self.running:
            return
        
        self.running = True
        self.ui_thread = threading.Thread(target=self._run_ui, daemon=True)
        self.ui_thread.start()
    
    def stop(self):
        """Stop the UI."""
        self.running = False
        if self.root:
            try:
                self.root.quit()
            except:
                pass
    
    def _run_ui(self):
        """Run the UI main loop."""
        try:
            self.root = tk.Tk()
            self.root.title("AI Agent Monitor")
            
            # Configure window
            self._setup_window()
            self._create_widgets()
            self._setup_bindings()
            
            self._initialized = True
            
            # Start main loop
            self.root.mainloop()
        except Exception as e:
            print(f"UI Error: {e}")
            self._initialized = False
    
    def _setup_window(self):
        """Configure window properties."""
        assert self.root is not None, "Root window must be initialized"
        
        # Set size and position (top-right corner)
        screen_width = self.root.winfo_screenwidth()
        x_position = screen_width - self.window_width - 20
        y_position = 20
        
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x_position}+{y_position}")
        
        # Always on top
        self.root.attributes('-topmost', True)
        
        # Set opacity
        self.root.attributes('-alpha', self.opacity)
        
        # Remove window decorations for cleaner look
        # self.root.overrideredirect(True)  # Uncomment for borderless
        
        # Dark theme colors
        self.bg_color = "#1e1e1e"
        self.fg_color = "#ffffff"
        self.accent_color = "#0078d4"
        self.success_color = "#4ec9b0"
        self.error_color = "#f48771"
        self.warning_color = "#dcdcaa"
        
        self.root.configure(bg=self.bg_color)
    
    def _create_widgets(self):
        """Create UI widgets."""
        # Header frame
        header_frame = tk.Frame(self.root, bg=self.accent_color, height=40)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="🤖 AI Agent Monitor",
            bg=self.accent_color,
            fg=self.fg_color,
            font=("Segoe UI", 12, "bold")
        )
        title_label.pack(side=tk.LEFT, padx=10, pady=8)
        
        # Control buttons
        btn_frame = tk.Frame(header_frame, bg=self.accent_color)
        btn_frame.pack(side=tk.RIGHT, padx=5)
        
        # Minimize button
        minimize_btn = tk.Button(
            btn_frame,
            text="−",
            command=self._toggle_minimize,
            bg=self.accent_color,
            fg=self.fg_color,
            font=("Segoe UI", 12, "bold"),
            relief=tk.FLAT,
            width=3,
            cursor="hand2"
        )
        minimize_btn.pack(side=tk.LEFT, padx=2)
        
        # Hide button
        hide_btn = tk.Button(
            btn_frame,
            text="👁",
            command=self._toggle_visibility,
            bg=self.accent_color,
            fg=self.fg_color,
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            width=3,
            cursor="hand2"
        )
        hide_btn.pack(side=tk.LEFT, padx=2)
        
        # Main content frame
        self.content_frame = tk.Frame(self.root, bg=self.bg_color)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Status section with better visual
        status_frame = tk.Frame(self.content_frame, bg="#2d2d2d", relief=tk.RAISED, bd=1)
        status_frame.pack(fill=tk.X, pady=(0, 10), padx=2)
        
        # Status header with icon
        status_header = tk.Frame(status_frame, bg="#2d2d2d")
        status_header.pack(fill=tk.X, padx=8, pady=(8, 4))
        
        tk.Label(
            status_header,
            text="⚡ Status",
            bg="#2d2d2d",
            fg=self.warning_color,
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)
        
        self.status_label = tk.Label(
            status_frame,
            text="🟢 Ready",
            bg="#2d2d2d",
            fg=self.success_color,
            font=("Segoe UI", 11, "bold"),
            anchor=tk.W,
            padx=8,
            pady=4
        )
        self.status_label.pack(fill=tk.X, pady=(0, 8))
        
        # Current task section with better wrapping
        task_frame = tk.Frame(self.content_frame, bg="#2d2d2d", relief=tk.RAISED, bd=1)
        task_frame.pack(fill=tk.X, pady=(0, 10), padx=2)
        
        # Task header
        task_header = tk.Frame(task_frame, bg="#2d2d2d")
        task_header.pack(fill=tk.X, padx=8, pady=(8, 4))
        
        tk.Label(
            task_header,
            text="📋 Current Task",
            bg="#2d2d2d",
            fg=self.warning_color,
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)
        
        self.task_label = tk.Label(
            task_frame,
            text="None",
            bg="#2d2d2d",
            fg=self.fg_color,
            font=("Segoe UI", 9),
            anchor=tk.W,
            wraplength=self.window_width - 50,
            justify=tk.LEFT,
            padx=8,
            pady=4
        )
        self.task_label.pack(fill=tk.X, pady=(0, 8))
        
        # Progress section with bordered frame
        progress_frame = tk.Frame(self.content_frame, bg="#2d2d2d", relief=tk.RAISED, bd=1)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Progress header
        progress_header = tk.Frame(progress_frame, bg="#2d2d2d")
        progress_header.pack(fill=tk.X, padx=8, pady=(8, 4))
        
        tk.Label(
            progress_header,
            text="⚡ Progress",
            bg="#2d2d2d",
            fg=self.success_color,
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)
        
        self.step_label = tk.Label(
            progress_frame,
            text="Step: 0/0",
            bg="#2d2d2d",
            fg=self.fg_color,
            font=("Segoe UI", 9),
            padx=8
        )
        self.step_label.pack(anchor=tk.W, pady=(0, 4))
        
        # Progress bar with padding
        progress_bar_container = tk.Frame(progress_frame, bg="#2d2d2d")
        progress_bar_container.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        # Progress bar
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Custom.Horizontal.TProgressbar",
            background=self.accent_color,
            troughcolor="#1a1a1a",
            bordercolor="#2d2d2d",
            lightcolor=self.accent_color,
            darkcolor=self.accent_color,
            thickness=20
        )
        
        self.progress_bar = ttk.Progressbar(
            progress_bar_container,
            style="Custom.Horizontal.TProgressbar",
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X)

        # Step detail section
        detail_frame = tk.Frame(self.content_frame, bg="#2d2d2d", relief=tk.RAISED, bd=1)
        detail_frame.pack(fill=tk.X, pady=(0, 10), padx=2)

        detail_header = tk.Frame(detail_frame, bg="#2d2d2d")
        detail_header.pack(fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(
            detail_header,
            text="🧠 Step Insight",
            bg="#2d2d2d",
            fg=self.accent_color,
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)

        self.step_detail_label = tk.Label(
            detail_frame,
            text="Waiting for first action...",
            bg="#2d2d2d",
            fg=self.fg_color,
            font=("Segoe UI", 9),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=self.window_width - 50,
            padx=8,
            pady=6
        )
        self.step_detail_label.pack(fill=tk.X)
        
        # Logs section with bordered frame
        logs_frame = tk.Frame(self.content_frame, bg="#2d2d2d", relief=tk.RAISED, bd=1)
        logs_frame.pack(fill=tk.BOTH, expand=True)
        
        # Logs header
        logs_header = tk.Frame(logs_frame, bg="#2d2d2d")
        logs_header.pack(fill=tk.X, padx=8, pady=(8, 4))
        
        tk.Label(
            logs_header,
            text="📜 Activity Log",
            bg="#2d2d2d",
            fg=self.accent_color,
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)
        
        # Log text area with padding
        log_container = tk.Frame(logs_frame, bg="#2d2d2d")
        log_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        
        self.log_text = scrolledtext.ScrolledText(
            log_container,
            bg="#1a1a1a",
            fg=self.fg_color,
            font=("Consolas", 8),
            height=15,
            wrap=tk.WORD,
            relief=tk.FLAT,
            padx=5,
            pady=5
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Configure log tags for colored output
        self.log_text.tag_config("INFO", foreground=self.success_color)
        self.log_text.tag_config("WARNING", foreground=self.warning_color)
        self.log_text.tag_config("ERROR", foreground=self.error_color)
        self.log_text.tag_config("DEBUG", foreground="#808080")
        
        # Make read-only
        self.log_text.config(state=tk.DISABLED)

        # Floating toast notifications
        self.toast_label = tk.Label(
            self.root,
            text="",
            bg="#2d2d2d",
            fg=self.fg_color,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
            relief=tk.RAISED,
            bd=1
        )
        self.toast_label.place_forget()
    
    def _setup_bindings(self):
        """Setup keyboard and mouse bindings."""
        assert self.root is not None, "Root window must be initialized"
        
        # Drag to move window
        self.root.bind('<Button-1>', self._start_drag)
        self.root.bind('<B1-Motion>', self._drag_window)
        
        # Double-click header to minimize
        self.root.bind('<Double-Button-1>', lambda e: self._toggle_minimize())
        
        # ESC to toggle visibility
        self.root.bind('<Escape>', lambda e: self._toggle_visibility())
    
    def _start_drag(self, event):
        """Start window drag."""
        self.drag_x = event.x
        self.drag_y = event.y
    
    def _drag_window(self, event):
        """Drag window to new position."""
        assert self.root is not None
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")
    
    def _toggle_minimize(self):
        """Toggle minimize state."""
        assert self.root is not None and self.content_frame is not None
        
        if self.is_minimized:
            # Restore
            self.root.geometry(f"{self.window_width}x{self.window_height}")
            self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            self.is_minimized = False
        else:
            # Minimize
            self.content_frame.pack_forget()
            self.root.geometry(f"{self.window_width}x{self.minimized_height}")
            self.is_minimized = True
    
    def _toggle_visibility(self):
        """Toggle UI visibility (for screenshots)."""
        if self.is_visible:
            self.hide()
        else:
            self.show()
    
    def hide(self):
        """Hide the UI window."""
        if self._initialized and self.root:
            try:
                self.root.withdraw()
                self.is_visible = False
            except Exception as e:
                print(f"Hide error: {e}")
    
    def show(self):
        """Show the UI window."""
        if self._initialized and self.root:
            try:
                self.root.deiconify()
                self.is_visible = True
            except Exception as e:
                print(f"Show error: {e}")
    
    def update_status(self, status: str, color: Optional[str] = None):
        """Update status display.
        
        Args:
            status: Status text
            color: Optional color for status
        """
        if not self._initialized or not self.root or not self.status_label:
            return
        
        try:
            self.root.after(0, lambda: self._do_update_status(status, color))
        except Exception as e:
            print(f"Update status error: {e}")
    
    def _do_update_status(self, status: str, color: Optional[str] = None):
        """Internal status update."""
        try:
            # Determine color if not provided
            if color is None:
                if "running" in status.lower() or "executing" in status.lower() or "working" in status.lower():
                    color = self.success_color
                elif "error" in status.lower() or "failed" in status.lower():
                    color = self.error_color
                elif "idle" in status.lower() or "ready" in status.lower():
                    color = self.warning_color
                else:
                    color = self.fg_color
            
            # Update label
            if self.status_label:
                self.status_label.config(text=status, fg=color)
        except Exception as e:
            print(f"[UI ERROR] Status update failed: {e}")
    
    def update_task(self, task: str):
        """Update current task display.
        
        Args:
            task: Task description
        """
        if not self._initialized or not self.root or not self.task_label:
            return
        
        self.current_task = task
        try:
            self.root.after(0, lambda: self._do_update_task(task))
        except Exception as e:
            print(f"Update task error: {e}")
    
    def _do_update_task(self, task: str):
        """Internal task update."""
        try:
            if self.task_label:
                self.task_label.config(text=task)
        except Exception as e:
            print(f"[UI ERROR] Task update failed: {e}")
    
    def update_progress(self, step: int, total: int, step_name: str = ""):
        """Update progress display.
        
        Args:
            step: Current step number
            total: Total steps
            step_name: Optional step name
        """
        if not self._initialized or not self.root:
            return
        
        self.completed_steps = step
        self.total_steps = total
        
        try:
            self.root.after(0, lambda: self._do_update_progress(step, total, step_name))
        except Exception as e:
            print(f"Update progress error: {e}")
    
    def _do_update_progress(self, step: int, total: int, step_name: str):
        """Internal progress update."""
        try:
            # Update step label
            step_text = f"Step: {step}/{total}"
            if step_name:
                step_text += f" - {step_name}"
            
            if self.step_label:
                self.step_label.config(text=step_text)
            
            # Update progress bar
            if self.progress_bar and total > 0:
                progress = (step / total) * 100
                self.progress_bar['value'] = progress
            elif self.progress_bar:
                self.progress_bar['value'] = 0
        except Exception as e:
            print(f"[UI ERROR] Progress update failed: {e}")

    def update_step_detail(self, summary: str):
        """Update contextual step insight text."""
        if not self._initialized or not self.root:
            return

        try:
            self.root.after(0, lambda: self._do_update_step_detail(summary))
        except Exception as e:
            print(f"Update step detail error: {e}")

    def _do_update_step_detail(self, summary: str):
        """Internal helper for step detail update."""
        try:
            if self.step_detail_label:
                self.step_detail_label.config(text=summary)
        except Exception as e:
            print(f"[UI ERROR] Step detail update failed: {e}")
    
    def add_log(self, message: str, level: str = "INFO"):
        """Add a log entry.
        
        Args:
            message: Log message
            level: Log level (INFO, WARNING, ERROR, DEBUG)
        """
        if not self._initialized or not self.root or not self.log_text:
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.logs.append((log_entry, level))
        
        try:
            self.root.after(0, lambda: self._do_add_log(log_entry, level))
        except Exception as e:
            print(f"Add log error: {e}")
    
    def _do_add_log(self, log_entry: str, level: str):
        """Internal log addition."""
        try:
            if self.log_text:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, log_entry, level)
                self.log_text.see(tk.END)  # Auto-scroll to bottom
                self.log_text.config(state=tk.DISABLED)
        except Exception as e:
            print(f"[UI ERROR] Log addition failed: {e}")
    
    def clear_logs(self):
        """Clear all log entries."""
        if not self._initialized or not self.root or not self.log_text:
            return
        
        try:
            self.root.after(0, self._do_clear_logs)
        except Exception as e:
            print(f"Clear logs error: {e}")
    
    def _do_clear_logs(self):
        """Internal log clearing."""
        try:
            if self.log_text:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete(1.0, tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.logs.clear()
        except Exception as e:
            print(f"Log clearing error: {e}")
    
    def reset(self):
        """Reset UI to idle state."""
        self.update_status("🟢 Idle")
        self.update_task("None")
        self.update_progress(0, 0, "")
        self.update_step_detail("Waiting for first action...")
        if self._initialized and self.root:
            self.root.after(0, self._hide_toast)
    
    def set_opacity(self, opacity: float):
        """Set window opacity.
        
        Args:
            opacity: Opacity value (0.0 to 1.0)
        """
        if self._initialized and self.root:
            try:
                root = self.root  # Capture for lambda
                self.root.after(0, lambda: root.attributes('-alpha', opacity))
            except Exception as e:
                print(f"Set opacity error: {e}")

    def show_toast(self, message: str, level: str = "info", duration: float = 2.5):
        """Display a transient toast notification."""
        if not self._initialized or not self.root or not self.toast_label:
            return

        colors = {
            "info": ("#2d2d2d", self.fg_color),
            "success": ("#1f4f46", self.success_color),
            "warning": ("#5a3c17", self.warning_color),
            "error": ("#5a1f1f", self.error_color),
        }
        bg_color, fg_color = colors.get(level, colors["info"])
        duration_ms = int(max(duration, 0.5) * 1000)

        root = self.root
        label = self.toast_label

        def _show():
            try:
                if not label or not root:
                    return

                label.config(text=message, bg=bg_color, fg=fg_color)

                width = label.winfo_reqwidth()
                height = label.winfo_reqheight()

                root_width = root.winfo_width()
                x = root_width - width - 30
                y = 20

                label.place(x=x, y=y)

                if self._toast_after_id:
                    root.after_cancel(self._toast_after_id)
                self._toast_after_id = root.after(duration_ms, self._hide_toast)
            except Exception as exc:
                print(f"Toast display error: {exc}")

        root.after(0, _show)

    def _hide_toast(self):
        """Hide the toast notification."""
        if not self._initialized or not self.root or not self.toast_label:
            return

        try:
            self.toast_label.place_forget()
            self._toast_after_id = None
        except Exception as e:
            print(f"Toast hide error: {e}")


# Global instance
_overlay_instance: Optional[AgentOverlayUI] = None


def get_overlay() -> AgentOverlayUI:
    """Get or create the global overlay instance."""
    global _overlay_instance
    if _overlay_instance is None:
        _overlay_instance = AgentOverlayUI()
    return _overlay_instance


def start_overlay():
    """Start the overlay UI."""
    overlay = get_overlay()
    overlay.start()


def stop_overlay():
    """Stop the overlay UI."""
    global _overlay_instance
    if _overlay_instance:
        _overlay_instance.stop()
        _overlay_instance = None
