import tkinter as tk
from tkinter import messagebox
import threading
import json
import calendar
from datetime import datetime

import user_data_getter

CLASSES_HEADER = ["Class:", "Grade:"]
TODO_HEADER = ["To Do List:", "Due Date:"]


class tkManager:
    # ------------------------------------------------------------------
    # Background work + data syncing (replaces the old codespace/websocket code)
    # ------------------------------------------------------------------
    def run_async(self, fn, callback):
        """Run fn() on a worker thread so the window never freezes, then call
        callback(result, error) back on the Tk thread."""
        box = {}

        def worker():
            try:
                box["result"] = fn()
            except Exception as e:  # shown to the user, never contains the key
                box["error"] = e

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll():
            if thread.is_alive():
                self.root.after(100, poll)
            else:
                callback(box.get("result"), box.get("error"))

        poll()

    def apply_fetched_data(self, classes, todo):
        self.classes = [list(CLASSES_HEADER)] + classes
        self.assignments = [list(TODO_HEADER)] + todo
        self.save()

    def clear_main(self):
        """Destroy everything in the main area AND reset row weights.
        Grid row/column settings belong to the container, not the widgets, so they
        survive destroy(). Without this reset, the To Do view's row weight leaked
        into the other views and stretched their rows."""
        for widget in self.main_content.winfo_children():
            widget.destroy()
        for c in (0, 1):
            self.main_content.grid_columnconfigure(c, weight=1, uniform="")
        _, rows = self.main_content.grid_size()
        for r in range(max(rows, 20)):
            self.main_content.grid_rowconfigure(r, weight=0, minsize=0)

    def set_sidebar_state(self, state):
        for btn in (self.Setting_btn, self.Courses_btn, self.To_do_btn):
            btn.config(state=state)

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def show_setup(self, first_run=False):
        """Key entry screen. Shown on first launch, or from Settings to change the key."""
        self.clear_main()
        for btn in (self.Setting_btn, self.Courses_btn, self.To_do_btn):
            btn.config(bg="white")
        self.set_sidebar_state("disabled" if first_run else "normal")

        bg = self.main_content.cget("bg")
        box = tk.Frame(self.main_content, bg=bg)
        box.grid(row=0, column=0, columnspan=2, pady=60)

        tk.Label(box, text="Connect to Canvas", font=("Segoe UI", 18, "bold"), bg=bg).grid(
            row=0, column=0, columnspan=2, pady=(0, 10))
        tk.Label(box, bg=bg, justify="left", font=("Segoe UI", 11),
                 text="Enter your school's Canvas URL, for example:\n"
                      "https://my-school-domain.instructure.com\n\n"
                      "Then create an API key in Canvas under Account > Settings > New Access Token\n"
                      "and paste it below. Your key is stored in your operating system's secure\n"
                      "credential store, never in a file.").grid(row=1, column=0, columnspan=2, pady=(0, 15))

        existing = user_data_getter.get_credentials()
        url_var = tk.StringVar(value=existing[0] if existing else "")
        token_var = tk.StringVar()

        tk.Label(box, text="Canvas URL:", font=("Segoe UI", 12), bg=bg).grid(row=2, column=0, sticky="e", padx=10, pady=8)
        tk.Entry(box, textvariable=url_var, font=("Segoe UI", 12), width=36).grid(row=2, column=1, padx=10, pady=8)
        tk.Label(box, text="API Key:", font=("Segoe UI", 12), bg=bg).grid(row=3, column=0, sticky="e", padx=10, pady=8)
        token_entry = tk.Entry(box, textvariable=token_var, font=("Segoe UI", 12), width=36, show="•")
        token_entry.grid(row=3, column=1, padx=10, pady=8)

        status = tk.Label(box, text="", font=("Segoe UI", 11), bg=bg, fg="#b00020", wraplength=450, justify="left")
        status.grid(row=5, column=0, columnspan=2, pady=(5, 0))

        def submit(event=None):
            base_url, token = url_var.get().strip(), token_var.get().strip()
            connect_btn.config(state="disabled")
            status.config(text="Connecting...", fg="black")

            def work():
                clean_url = user_data_getter.validate(base_url, token)
                persisted = user_data_getter.save_credentials(clean_url, token)
                return persisted, user_data_getter.fetch_courses(), user_data_getter.fetch_todo()

            def done(result, error):
                if error:
                    status.config(text=str(error), fg="#b00020")
                    connect_btn.config(state="normal")
                    return
                persisted, classes, todo = result
                token_var.set("")  # don't leave the secret sitting in the widget
                self.apply_fetched_data(classes, todo)
                self.set_sidebar_state("normal")
                if not persisted:
                    messagebox.showwarning(
                        "Session only",
                        "No secure credential store was found on this system, so your key is "
                        "kept in memory for this session only. You'll need to re-enter it next time.")
                self.Courses()

            self.run_async(work, done)

        connect_btn = tk.Button(box, text="Connect", font=("Segoe UI", 12), width=12, command=submit)
        connect_btn.grid(row=4, column=0, columnspan=2, pady=10)
        token_entry.bind("<Return>", submit)

    def Settings(self):
        self.clear_main()
        for btn in self.sidebar.winfo_children():
            if btn == self.Menu_label:
                continue
            btn.config(bg="white")
        self.Setting_btn.config(bg="grey")

        settings_row = tk.Frame(self.main_content, bg="white")
        settings_row.grid(row=1, column=0, columnspan=3, pady=10)
        tk.Label(settings_row, text="Change Background Color:", font=("Segoe UI", 12)).grid(row=1, column=0, padx=10, pady=(10, 0), sticky="e")
        color_input = tk.Entry(settings_row, font=("Segoe UI", 12), width=30)
        color_input.grid(row=1, column=1, padx=10, pady=10)
        tk.Button(settings_row, text="Apply Color", font=("Segoe UI", 12), command=lambda: self.main_content.config(bg=color_input.get())).grid(row=1, column=2, padx=10, pady=10, sticky="w")

        creds = user_data_getter.get_credentials()
        shown = user_data_getter.mask(creds[1]) if creds else "not set"
        tk.Label(settings_row, text=f"Canvas API Key: {shown}", font=("Segoe UI", 12)).grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="e")
        tk.Button(settings_row, text="Change Key", font=("Segoe UI", 12), command=self.show_setup).grid(row=2, column=2, padx=10, pady=10, sticky="w")

        def sign_out():
            if not messagebox.askyesno("Remove key", "Delete the stored API key and your saved Canvas data from this computer?"):
                return
            user_data_getter.clear_credentials()
            self.classes = [list(CLASSES_HEADER)]
            self.assignments = [list(TODO_HEADER)]
            self.save()
            self.show_setup(first_run=True)

        tk.Button(settings_row, text="Remove Key & Sign Out", font=("Segoe UI", 12), command=sign_out).grid(row=3, column=1, padx=10, pady=10, sticky="w")

    def Courses(self):
        self.clear_main()
        for btn in self.sidebar.winfo_children():
            if btn == self.Menu_label:
                continue
            btn.config(bg="white")
        self.Courses_btn.config(bg="grey")

        for r in range(len(self.classes)):
            for c in range(len(self.classes[r])):
                cell = tk.Entry(self.main_content, font=("Segoe UI", 12), width=30)
                if c == 0:
                    cell.grid(row=r, column=c, sticky="e", padx=10)
                else:
                    cell.grid(row=r, column=c, sticky="w", padx=10)
                cell.insert(tk.END, str(self.classes[r][c]))
                cell.config(state='readonly')

    def To_Do(self):
        self.clear_main()
        for btn in self.sidebar.winfo_children():
            if btn == self.Menu_label:
                continue
            btn.config(bg="white")
        self.To_do_btn.config(bg="grey")

        self.main_content.grid_rowconfigure(0, weight=1)
        # Split the width 5:3, so the calendar gets 3/8 of the screen. "uniform" makes the
        # columns follow the ratio exactly instead of just sharing leftover space.
        self.main_content.grid_columnconfigure(0, weight=5, uniform="todo_split")
        self.main_content.grid_columnconfigure(1, weight=3, uniform="todo_split")
        selected_row = None
        todo_cells = []

        To_do_list = tk.Frame(self.main_content, bg=self.main_content.cget("bg"))
        To_do_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # The holder fills the whole right column. The calendar itself is a square that
        # gets centered inside it (see fit_calendar below).
        cal_holder = tk.Frame(self.main_content, bg=self.main_content.cget("bg"))
        cal_holder.grid(row=0, column=1, sticky="nsew")
        Calendar = tk.Frame(cal_holder, bg=self.main_content.cget("bg"))
        Calendar.grid_propagate(False)  # keep the exact square size we assign it
        cal_side = {"value": 0}         # current side length in pixels

        rows_frame = tk.Frame(To_do_list, bg=self.main_content.cget("bg"))
        rows_frame.grid(row=0, column=0, sticky="nsew")

        def select_row(r):
            nonlocal selected_row
            selected_row = r
            # Re-highlight all rows so only the selected one stands out
            for row_idx, row_cells in enumerate(todo_cells):
                color = "#cde8ff" if row_idx == r else "white"
                for cell in row_cells:
                    cell.config(readonlybackground=color, bg=color)

        def render_rows():
            nonlocal todo_cells
            for widget in rows_frame.winfo_children():
                widget.destroy()
            todo_cells = []

            for r in range(len(self.assignments)):
                row_cells = []
                for c in range(len(self.assignments[r])):
                    cell = tk.Entry(rows_frame, font=("Segoe UI", 12), width=30)
                    if c == 0:
                        cell.grid(row=r, column=c, sticky="e", padx=10, pady=2)
                    else:
                        cell.grid(row=r, column=c, sticky="w", padx=10, pady=2)
                    cell.insert(tk.END, str(self.assignments[r][c]))
                    cell.config(state='readonly')
                    if r > 0:  # header row (r == 0) isn't selectable
                        cell.bind("<Button-1>", lambda e, row=r: select_row(row))
                    row_cells.append(cell)
                todo_cells.append(row_cells)

        def add_row():
            self.assignments.append(["", ""])
            render_rows()

        def edit_row():
            if selected_row is None:
                return
            for cell in todo_cells[selected_row]:
                cell.config(state='normal', bg="white")

        def delete_row():
            nonlocal selected_row
            if selected_row is None or selected_row == 0:
                return
            del self.assignments[selected_row]
            selected_row = None
            render_rows()

        def confirm_changes():
            nonlocal selected_row
            for r, row_cells in enumerate(todo_cells):
                for c, cell in enumerate(row_cells):
                    self.assignments[r][c] = cell.get()
                    cell.config(state='readonly', bg="white", readonlybackground="white")
            selected_row = None
            build_calendar(Calendar, self.current_cal_year, self.current_cal_month)

        button_row = tk.Frame(To_do_list, bg=self.main_content.cget("bg"))
        button_row.grid(row=1, column=0, pady=10, sticky="ew")

        tk.Button(button_row, text="Add", font=("Segoe UI", 12), width=8, command=add_row).pack(side="left", padx=5)
        tk.Button(button_row, text="Edit", font=("Segoe UI", 12), width=8, command=edit_row).pack(side="left", padx=5)
        tk.Button(button_row, text="Delete", font=("Segoe UI", 12), width=8, command=delete_row).pack(side="left", padx=5)
        tk.Button(button_row, text="Confirm", font=("Segoe UI", 12), width=8, command=confirm_changes).pack(side="left", padx=5)

        def build_calendar(parent, year, month):
            # Fonts scale with the calendar size (480px side = 1.0) so it fits on any screen
            scale = max(0.6, min(1.6, (cal_side["value"] or 480) / 480))
            fs = lambda base: max(8, int(base * scale))

            # Clear out any previous calendar widgets
            for widget in parent.winfo_children():
                widget.destroy()

            # --- Header with month/year and nav buttons ---
            header = tk.Frame(parent, bg="white")
            header.grid(row=0, column=0, columnspan=7, pady=(0, 10), sticky="ew")

            def change_month(delta):
                # (fixed: this used `global` variables that didn't exist)
                self.current_cal_month += delta
                if self.current_cal_month > 12:
                    self.current_cal_month = 1
                    self.current_cal_year += 1
                elif self.current_cal_month < 1:
                    self.current_cal_month = 12
                    self.current_cal_year -= 1
                build_calendar(parent, self.current_cal_year, self.current_cal_month)

            tk.Button(header, text="<", font=("Segoe UI", fs(14), "bold"), width=3, command=lambda: change_month(-1)).pack(side="left")
            tk.Label(header, text=f"{calendar.month_name[month]} {year}", font=("Segoe UI", fs(20), "bold"), bg="white").pack(side="left", expand=True)
            tk.Button(header, text=">", font=("Segoe UI", fs(14), "bold"), width=3, command=lambda: change_month(1)).pack(side="right")

            # --- Weekday labels ---
            days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for c, day_name in enumerate(days_of_week):
                tk.Label(parent, text=day_name, font=("Segoe UI", fs(12), "bold"), bg="white").grid(row=1, column=c, padx=2, pady=2)

            # --- Figure out which days have assignments due ---
            due_days = set()
            for assignment in self.assignments[1:]:  # skip header row
                name, due_at = assignment[0], assignment[1]
                due_date = user_data_getter.parse_due(due_at)  # same parser the list uses
                if due_date and due_date.year == year and due_date.month == month:
                    due_days.add(due_date.day)

            # --- Day grid ---
            month_matrix = calendar.monthcalendar(year, month)  # weeks, each a list of 7 ints (0 = blank)

            # Let the grid fill the space it's given. Row weights live on the parent,
            # so reset them each time: months have 4-6 weeks.
            for c in range(7):
                parent.grid_columnconfigure(c, weight=1, uniform="cal_col")
            for r in range(2, 8):
                if r < 2 + len(month_matrix):
                    parent.grid_rowconfigure(r, weight=1, uniform="cal_row")
                else:
                    parent.grid_rowconfigure(r, weight=0, uniform="")
            for r, week in enumerate(month_matrix, start=2):
                for c, day in enumerate(week):
                    if day == 0:
                        tk.Frame(parent, bg="white", width=1, height=1).grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
                        continue

                    bg_color = "#ffdd57" if day in due_days else "white"
                    day_frame = tk.Frame(parent, bg=bg_color, width=1, height=1, highlightbackground="#ccc", highlightthickness=1)
                    day_frame.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
                    day_frame.grid_propagate(False)
                    tk.Label(day_frame, text=str(day), font=("Segoe UI", fs(15), "bold" if day in due_days else "normal"), bg=bg_color).pack(anchor="ne", padx=5, pady=3)

        def fit_calendar(event=None):
            # 1/4 of the window width, but never taller than the column allows
            # (the 100px margin keeps it clear of the Close button in the top-right corner).
            side = min(self.root.winfo_width() // 4,
                       cal_holder.winfo_height() - 100,
                       cal_holder.winfo_width() - 20)
            side = max(side, 200)
            if side == cal_side["value"]:
                return
            cal_side["value"] = side
            Calendar.place(relx=0.5, rely=0.5, anchor="center", width=side, height=side)
            build_calendar(Calendar, self.current_cal_year, self.current_cal_month)

        cal_holder.bind("<Configure>", fit_calendar)
        render_rows()

    def toggle_fullscreen(self, Event):
        self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen'))

    def close(self):
        self.save()
        self.root.destroy()

    def initialize_tkinter(self):
        self.sidebar.grid(row=0, column=0, sticky="ns")  # "ns" = stretch top-to-bottom
        self.sidebar.grid_propagate(False)  # prevents sidebar from shrinking to fit contents
        self.main_content.grid(row=0, column=1, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_columnconfigure(1, weight=1)

        self.Menu_label.grid(row=0, column=0, pady=(20, 10), padx=10)
        self.Setting_btn.grid(row=1, column=0, pady=5, padx=10, sticky="ew")
        self.Courses_btn.grid(row=2, column=0, pady=5, padx=10, sticky="ew")
        self.To_do_btn.grid(row=3, column=0, pady=5, padx=10, sticky="ew")

        self.close_btn.grid(row=0, column=1, sticky="ne")
        self.root.bind("<F11>", self.toggle_fullscreen)

    def start(self):
        """Decide what to show on launch: key screen, a fresh sync, or saved data."""
        if not user_data_getter.has_credentials():
            self.show_setup(first_run=True)
            return

        no_data_yet = len(self.classes) <= 1 and len(self.assignments) <= 1
        if not (self.is_first_startup or no_data_yet):
            self.Courses()
            return

        # Key is stored but we have no data yet: sync once, then show the app.
        self.set_sidebar_state("disabled")
        tk.Label(self.main_content, text="Loading your Canvas data...", font=("Segoe UI", 14), bg="white").grid(row=0, column=0, columnspan=2, pady=60)

        def work():
            return user_data_getter.fetch_courses(), user_data_getter.fetch_todo()

        def done(result, error):
            self.set_sidebar_state("normal")
            if error:
                messagebox.showerror("Canvas", f"{error}\n\nPlease re-enter your key.")
                self.show_setup(first_run=True)
                return
            self.apply_fetched_data(*result)
            self.Courses()

        self.run_async(work, done)

    # ------------------------------------------------------------------
    # initialize and save/load
    # ------------------------------------------------------------------
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Canvas Client")
        self.root.state("zoomed")
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.current_cal_year = datetime.now().year
        self.current_cal_month = datetime.now().month
        self.sidebar = tk.Frame(self.root, width=100, bg="#2b2b2b")
        self.Menu_label = tk.Label(self.sidebar, text="Menu", fg="white", bg="#2b2b2b", font=("Segoe UI", 14, "bold"))
        self.main_content = tk.Frame(self.root, bg="white")
        self.Setting_btn = tk.Button(self.sidebar, text="Settings", font=("Segoe UI", 14), command=lambda: self.Settings())
        self.Courses_btn = tk.Button(self.sidebar, text="Courses", font=("Segoe UI", 14), command=lambda: self.Courses())
        self.To_do_btn = tk.Button(self.sidebar, text="To Do", font=("Segoe UI", 14), command=lambda: self.To_Do())
        self.close_btn = tk.Button(self.root, text="Close", command=lambda: self.close(), font=("Segoe UI", 12))

        self.is_first_startup = self.load()

    def save(self, filename="save.json"):
        # Only non-secret data is saved here. The API key lives in the OS keyring.
        data = {
            "bg_color": self.main_content.cget("bg"),
            "classes": self.classes,
            "assignments": self.assignments
        }

        with open(filename, "w") as file:
            json.dump(data, file, indent=4)

    def load(self, filename="save.json"):
        try:
            with open(filename, "r") as file:
                data = json.load(file)
                self.main_content.config(bg=data.get("bg_color", "white"))
                self.classes = data.get("classes", [list(CLASSES_HEADER)])
                self.assignments = data.get("assignments", [list(TODO_HEADER)])
                # Migrate older saves that stored raw UTC timestamps
                for row in self.assignments[1:]:
                    row[1] = user_data_getter.format_due(row[1])
                return False
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"No save file found at {filename}. Starting with default settings.")
            self.classes = [list(CLASSES_HEADER)]
            self.assignments = [list(TODO_HEADER)]
            return True


manager = tkManager()
manager.initialize_tkinter()
manager.start()
manager.root.mainloop()