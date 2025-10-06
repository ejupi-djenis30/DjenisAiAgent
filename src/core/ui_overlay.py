"""Transparent overlay UI for the AI Agent."""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, List, Dict, Any
import threading
from datetime import datetime
from collections import deque


class AgentOverlayUI:
    """Always-on-top transparent overlay UI for monitoring agent activity."""
    
    def __init__(self, opacity: float = 0.85):
        """Initialize the overlay UI.
        
        Args:
            opacity: Window opacity (0.0 to 1.0)
        """
        self.root: Optional[tk.Tk] = None
        self.opacity = opacity
        self.is_visible = True
        self.is_minimized = False
        
        # UI components
        self.status_label: Optional[tk.Label] = None
        self.task_label: Optional[tk.Label] = None
        self.step_label: Optional[tk.Label] = None
        self.log_text: Optional[scrolledtext.ScrolledText] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        
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
        self.root = tk.Tk()
        self.root.title("AI Agent Monitor")
        
        # Configure window
        self._setup_window()
        self._create_widgets()
        self._setup_bindings()
        
        # Start main loop
        self.root.mainloop()
    
    def _setup_window(self):
        """Configure window properties."""
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
        
        # Status section
        status_frame = tk.Frame(self.content_frame, bg=self.bg_color)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            status_frame,
            text="Status:",
            bg=self.bg_color,
            fg=self.warning_color,
            font=("Segoe UI", 9, "bold")
        ).pack(anchor=tk.W)
        
        self.status_label = tk.Label(
            status_frame,
            text="🟢 Idle",
            bg=self.bg_color,
            fg=self.success_color,
            font=("Segoe UI", 10),
            anchor=tk.W
        )
        self.status_label.pack(fill=tk.X, pady=(2, 0))
        
        # Current task section
        task_frame = tk.Frame(self.content_frame, bg=self.bg_color)
        task_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            task_frame,
            text="Current Task:",
            bg=self.bg_color,
            fg=self.warning_color,
            font=("Segoe UI", 9, "bold")
        ).pack(anchor=tk.W)
        
        self.task_label = tk.Label(
            task_frame,
            text="None",
            bg=self.bg_color,
            fg=self.fg_color,
            font=("Segoe UI", 9),
            anchor=tk.W,
            wraplength=self.window_width - 40,
            justify=tk.LEFT
        )
        self.task_label.pack(fill=tk.X, pady=(2, 0))
        
        # Progress section
        progress_frame = tk.Frame(self.content_frame, bg=self.bg_color)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.step_label = tk.Label(
            progress_frame,
            text="Step: 0/0",
            bg=self.bg_color,
            fg=self.warning_color,
            font=("Segoe UI", 9, "bold")
        )
        self.step_label.pack(anchor=tk.W)
        
        # Progress bar
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Custom.Horizontal.TProgressbar",
            background=self.accent_color,
            troughcolor=self.bg_color,
            bordercolor=self.bg_color,
            lightcolor=self.accent_color,
            darkcolor=self.accent_color
        )
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            style="Custom.Horizontal.TProgressbar",
            mode='determinate',
            length=self.window_width - 40
        )
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        
        # Logs section
        logs_frame = tk.Frame(self.content_frame, bg=self.bg_color)
        logs_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            logs_frame,
            text="Activity Log:",
            bg=self.bg_color,
            fg=self.warning_color,
            font=("Segoe UI", 9, "bold")
        ).pack(anchor=tk.W)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(
            logs_frame,
            bg="#2d2d2d",
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
    
    def _setup_bindings(self):
        """Setup keyboard and mouse bindings."""
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
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")
    
    def _toggle_minimize(self):
        """Toggle minimize state."""
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
        if self.root:
            self.root.withdraw()
            self.is_visible = False
    
    def show(self):
        """Show the UI window."""
        if self.root:
            self.root.deiconify()
            self.is_visible = True
    
    def update_status(self, status: str, color: str = None):
        """Update status display.
        
        Args:
            status: Status text
            color: Optional color for status
        """
        if not self.root or not self.status_label:
            return
        
        try:
            self.root.after(0, lambda: self._do_update_status(status, color))
        except:
            pass
    
    def _do_update_status(self, status: str, color: str = None):
        """Internal status update."""
        if color is None:
            if "running" in status.lower() or "executing" in status.lower():
                color = self.success_color
            elif "error" in status.lower() or "failed" in status.lower():
                color = self.error_color
            elif "idle" in status.lower():
                color = self.warning_color
            else:
                color = self.fg_color
        
        self.status_label.config(text=status, fg=color)
    
    def update_task(self, task: str):
        """Update current task display.
        
        Args:
            task: Task description
        """
        if not self.root or not self.task_label:
            return
        
        self.current_task = task
        try:
            self.root.after(0, lambda: self.task_label.config(text=task))
        except:
            pass
    
    def update_progress(self, step: int, total: int, step_name: str = ""):
        """Update progress display.
        
        Args:
            step: Current step number
            total: Total steps
            step_name: Optional step name
        """
        if not self.root:
            return
        
        self.completed_steps = step
        self.total_steps = total
        
        try:
            self.root.after(0, lambda: self._do_update_progress(step, total, step_name))
        except:
            pass
    
    def _do_update_progress(self, step: int, total: int, step_name: str):
        """Internal progress update."""
        # Update step label
        step_text = f"Step: {step}/{total}"
        if step_name:
            step_text += f" - {step_name}"
        self.step_label.config(text=step_text)
        
        # Update progress bar
        if total > 0:
            progress = (step / total) * 100
            self.progress_bar['value'] = progress
        else:
            self.progress_bar['value'] = 0
    
    def add_log(self, message: str, level: str = "INFO"):
        """Add a log entry.
        
        Args:
            message: Log message
            level: Log level (INFO, WARNING, ERROR, DEBUG)
        """
        if not self.root or not self.log_text:
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.logs.append((log_entry, level))
        
        try:
            self.root.after(0, lambda: self._do_add_log(log_entry, level))
        except:
            pass
    
    def _do_add_log(self, log_entry: str, level: str):
        """Internal log addition."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry, level)
        self.log_text.see(tk.END)  # Auto-scroll to bottom
        self.log_text.config(state=tk.DISABLED)
    
    def clear_logs(self):
        """Clear all log entries."""
        if not self.root or not self.log_text:
            return
        
        try:
            self.root.after(0, self._do_clear_logs)
        except:
            pass
    
    def _do_clear_logs(self):
        """Internal log clearing."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.logs.clear()
    
    def reset(self):
        """Reset UI to idle state."""
        self.update_status("🟢 Idle")
        self.update_task("None")
        self.update_progress(0, 0, "")
    
    def set_opacity(self, opacity: float):
        """Set window opacity.
        
        Args:
            opacity: Opacity value (0.0 to 1.0)
        """
        if self.root:
            try:
                self.root.after(0, lambda: self.root.attributes('-alpha', opacity))
            except:
                pass


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
