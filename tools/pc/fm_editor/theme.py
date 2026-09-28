"""The editor's two looks: the desktop's own (light, as the editor always
was) and a dark one, switched at run time under View > Dark mode.

The ttk widgets follow a theme: the light one is "vista" on Windows and
"clam" elsewhere, the dark one "fm-dark", a clam made dark (clam's elements
take colors; the native vista ones do not). The few classic Tk widgets (the
text boxes, the menus, a Combobox's drop-down list, the dialogs' Toplevel)
take colors of their own: set on the ones that exist and in the option
database for those made later, and put back to Tk's defaults for light.
The hint and result labels use the named styles in INKS, and the trees'
row tags the colors in TAGS, so they change with the theme too."""
from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

DARK_THEME = "fm-dark"

# The dark palette. Text and every ink below are at least 4.5:1 against the
# backgrounds they are drawn on (WCAG AA); disabled text is dimmer, as
# disabled controls may be.
BG = "#202124"          # windows, frames, labels
FIELD = "#2a2b2f"       # entries, lists, text boxes, trees
RAISED = "#35373c"      # buttons, headings, the unselected tabs
HOVER = "#404349"
PRESSED = "#2a2b2f"
BORDER = "#55585e"
TROUGH = "#18191b"
FG = "#e8eaed"
DISABLED = "#8c9197"
SELECT = "#264266"      # selected rows and text
FOCUS = "#6f9dd6"       # a focused field's border

# Label styles (ttk.Label(..., style="Hint.TLabel")): light, dark.
INKS = {
    "Hint": ("#777", "#a3a9b0"),        # explanations and counts
    "Note": ("#555", "#c4c8cd"),        # the Art tab's captions
    "Error": ("#c01c28", "#ff8f87"),
    "Ok": ("#26a269", "#7fd49b"),
    "Warning": ("#9c6500", "#f2c04c"),
}

# Tree row tags (widgets.scrolled_tree): light, dark.
TAGS = {
    "changed": ("#1a5fb4", "#8ab4f8"),
    "added": ("#26a269", "#7fd49b"),
    "removed": ("#c01c28", "#ff8f87"),
    "glitch": ("#865e3c", "#e0ae78"),
    "error": ("#c01c28", "#ff8f87"),
    "warning": ("#9c6500", "#f2c04c"),
}

# The classic widgets' colors in the dark look, by widget class.
CLASSIC = {
    "Text": {"background": FIELD, "foreground": FG, "insertbackground": FG, "selectbackground": SELECT,
             "selectforeground": FG, "inactiveselectbackground": SELECT, "highlightbackground": BG,
             "highlightcolor": FOCUS},
    "Listbox": {"background": FIELD, "foreground": FG, "selectbackground": SELECT, "selectforeground": FG,
                "disabledforeground": DISABLED, "highlightbackground": BG, "highlightcolor": FOCUS},
    "Menu": {"background": FIELD, "foreground": FG, "activebackground": SELECT, "activeforeground": FG,
             "disabledforeground": DISABLED, "selectcolor": FG},
    "Toplevel": {"background": BG},
}


def is_dark(widget) -> bool:
    return ttk.Style(widget).theme_use() == DARK_THEME


def tag_color(widget, tag: str) -> str:
    light, dark = TAGS[tag]
    return dark if is_dark(widget) else light


class Theme:
    """Switches a window (and the dialogs it opens) between the two looks."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        self.light = self.style.theme_use()
        self.dark = False
        # A row as tall as a line of text, in either theme.
        self.row_height = tkfont.nametofont("TkDefaultFont", root=root).metrics("linespace") + 4
        self.style.configure("Treeview", rowheight=self.row_height)
        for name, (light, _) in INKS.items():
            self.style.configure(f"{name}.TLabel", foreground=light)
        # Tk's own defaults for the classic widgets, to go back to.
        self.defaults = {}
        for cls, options in CLASSIC.items():
            sample = root if cls == "Toplevel" else getattr(tk, cls)(root)
            self.defaults[cls] = {option: str(sample.configure(option)[3]) for option in options}
            if sample is not root:
                sample.destroy()
        root.bind_class("Toplevel", "<Map>", lambda e: self.title_bar(e.widget), add="+")
        self.menubar = None     # the window's own menu bar, while the strip stands in for it
        self.strip = None
        root.bind("<Alt-KeyPress>", self.alt_key, add="+")
        root.bind("<F10>", self.alt_key, add="+")

    def use(self, dark: bool):
        if dark and DARK_THEME not in self.style.theme_names():
            self.make_dark()
        self.style.theme_use(DARK_THEME if dark else self.light)
        self.root.update_idletasks()      # the widgets take the theme (and ask their sizes again) now
        self.dark = dark
        for cls, options in CLASSIC.items():
            values = options if dark else self.defaults[cls]
            for option, value in values.items():
                self.root.option_add(f"*{cls}.{option}", value)
        # The widgets that exist, Tcl's own included (tkinter's
        # winfo_children skips the Combobox's drop-down list).
        call = self.root.tk.call
        for path in self.walk("."):
            cls = call("winfo", "class", path)
            cls = "Toplevel" if cls == "Tk" else cls
            if cls in CLASSIC:
                values = CLASSIC[cls] if dark else self.defaults[cls]
                call(path, "configure", *[item for option, value in values.items()
                                          for item in (f"-{option}", value)])
            elif cls == "Treeview":
                for tag, (light, dark_ink) in TAGS.items():
                    call(path, "tag", "configure", tag, "-foreground", dark_ink if dark else light)
                # The theme change had the tree ask for its columns' widths,
                # stretched by now, squeezing the form beside it: back to the
                # widths it was made with, and ask again.
                widths = getattr(self.widget(path), "widths", None)
                if widths:
                    for key, width in widths.items():
                        call(path, "column", key, "-width", width)
                    call(path, "configure", "-height", call(path, "cget", "-height"))
            if cls == "Toplevel" and call("winfo", "ismapped", path):
                self.title_bar(self.widget(path))
        self.menu_bar(dark)

    def widget(self, path):
        """The tkinter object of a path, or None for a widget Tcl made."""
        try:
            return self.root.nametowidget(path)
        except KeyError:
            return None

    def walk(self, path):
        yield path
        for child in self.root.tk.splitlist(self.root.tk.call("winfo", "children", path)):
            yield from self.walk(child)

    def title_bar(self, window):
        """Windows 10 (20H1) and 11 draw a window's title bar dark when
        asked; elsewhere the window manager's own is kept."""
        if sys.platform != "win32" or (not self.dark and not getattr(window, "dark_title", False)):
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            value = ctypes.c_int(1 if self.dark else 0)
            # DWMWA_USE_IMMERSIVE_DARK_MODE, then its number before 20H1.
            for attribute in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                              ctypes.sizeof(value)) == 0:
                    break
            # Redraw the frame now, not at the next activation.
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)   # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
            window.dark_title = self.dark
        except (AttributeError, OSError, KeyError):
            pass

    def menu_bar(self, dark):
        """Windows draws a window's menu bar itself, light whatever Tk asks
        (uxtheme's undocumented dark mode calls leave it light too). In the
        dark look the bar is a strip of Tk menubuttons instead, each posting
        a clone of the bar's menu: a clone keeps its menu's entries, added
        ones (an importer's) included. The menus themselves Tk draws, dark,
        but for the thin frame Windows puts around them. X11 draws Tk's own
        bar, colored with the other menus."""
        if sys.platform != "win32" or (not dark and self.strip is None):
            return
        root = self.root
        if dark:
            if self.strip is None:
                self.menubar = root.nametowidget(root.cget("menu"))
                self.strip = self.make_strip(self.menubar)
            if self.strip.winfo_manager():
                return
            root.configure(menu="")
            self.strip.pack(side="top", fill="x", before=root.pack_slaves()[0])
            grow = self.strip.winfo_reqheight()
        elif self.strip.winfo_manager():
            self.strip.pack_forget()
            root.configure(menu=self.menubar)
            grow = -self.strip.winfo_reqheight()
        else:
            return
        # Tk keeps the size inside the frame, which the bar is not: keep the
        # window's own size instead, the strip taking the bar's room.
        if root.winfo_ismapped() and root.state() == "normal":
            root.geometry(f"{root.winfo_width()}x{root.winfo_height() + grow}")

    def make_strip(self, bar):
        strip = ttk.Frame(self.root)
        for index in range(bar.index("end") + 1):
            if bar.type(index) != "cascade":
                continue
            button = tk.Menubutton(strip, text=bar.entrycget(index, "label"), underline=0, background=BG,
                                   foreground=FG, activebackground=HOVER, activeforeground=FG, borderwidth=0,
                                   highlightthickness=0, padx=7, pady=2)
            clone = f"{button}.menu"
            self.root.tk.call(bar.entrycget(index, "menu"), "clone", clone, "normal")
            button.configure(menu=clone)
            button.pack(side="left")
        return strip

    def alt_key(self, event):
        """Alt+letter and F10 open the strip's menus, as they do the bar's."""
        if self.strip is None or not self.strip.winfo_manager():
            return None
        call = self.root.tk.call
        if event.keysym == "F10":
            call("tk::FirstMenu", ".")
            return "break"
        if event.char and call("tk::MenuFind", ".", event.char):
            call("tk::TraverseToMenu", ".", event.char)
            return "break"
        return None

    def make_dark(self):
        """fm-dark: clam's elements and layouts, clam's settings in dark colors."""
        style = self.style
        style.theme_create(DARK_THEME, parent="clam")
        current = style.theme_use()
        style.theme_use(DARK_THEME)       # configure and map set the theme in use
        style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=BORDER,
                        lightcolor=RAISED, darkcolor=BG, troughcolor=TROUGH, selectbackground=SELECT,
                        selectforeground=FG, selectborderwidth=0, insertcolor=FG, arrowcolor=FG,
                        focuscolor=FOCUS, font="TkDefaultFont")
        style.map(".", background=[("disabled", BG), ("active", HOVER)], foreground=[("disabled", DISABLED)],
                  arrowcolor=[("disabled", DISABLED)])
        style.configure("TButton", background=RAISED, lightcolor=HOVER, darkcolor=RAISED, anchor="center",
                        width=-11, padding=5, relief="raised")
        style.map("TButton", background=[("disabled", BG), ("pressed", PRESSED), ("active", HOVER)],
                  lightcolor=[("pressed", PRESSED)], darkcolor=[("pressed", PRESSED)],
                  bordercolor=[("focus", FOCUS)])
        for field in ("TEntry", "TSpinbox", "TCombobox"):
            style.configure(field, fieldbackground=FIELD, foreground=FG, background=RAISED, lightcolor=FIELD,
                            darkcolor=FIELD, insertwidth=1, padding=1)
            style.map(field, fieldbackground=[("disabled", BG), ("readonly", FIELD)],
                      foreground=[("disabled", DISABLED)], bordercolor=[("focus", FOCUS)],
                      lightcolor=[("focus", FIELD)], darkcolor=[("focus", FIELD)],
                      background=[("disabled", BG), ("pressed", HOVER), ("active", HOVER)],
                      arrowcolor=[("disabled", DISABLED)])
        style.configure("TCombobox", padding=(1, 1, 1, 1))
        style.configure("ComboboxPopdownFrame", background=FIELD, bordercolor=BORDER, relief="solid")
        style.configure("TNotebook", background=BG, bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                        tabmargins=(2, 2, 2, 0))
        style.configure("TNotebook.Tab", background=RAISED, foreground=FG, lightcolor=RAISED, darkcolor=BG,
                        bordercolor=BORDER, padding=(6, 2, 6, 2))
        style.map("TNotebook.Tab", background=[("selected", BG), ("active", HOVER)],
                  padding=[("selected", (6, 4, 6, 2))], lightcolor=[("selected", BG)])
        style.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, bordercolor=BORDER,
                        lightcolor=FIELD, darkcolor=FIELD, rowheight=self.row_height)
        style.map("Treeview", background=[("disabled", BG), ("selected", SELECT)],
                  foreground=[("disabled", DISABLED), ("selected", FG)])
        style.configure("Heading", background=RAISED, foreground=FG, lightcolor=RAISED, darkcolor=RAISED,
                        bordercolor=BORDER, relief="raised", font="TkHeadingFont")
        style.map("Heading", background=[("active", HOVER)])
        style.configure("TScrollbar", background=RAISED, troughcolor=TROUGH, bordercolor=TROUGH,
                        lightcolor=RAISED, darkcolor=RAISED, arrowcolor=FG, gripcount=0)
        style.map("TScrollbar", background=[("pressed", BORDER), ("active", HOVER)])
        style.configure("TLabelframe", background=BG, bordercolor=BORDER, lightcolor=BG, darkcolor=BG, relief="solid",
                        borderwidth=1, labelmargins=(6, 0, 6, 2))
        style.configure("TLabelframe.Label", background=BG, foreground=FG)
        style.configure("TSeparator", background=BORDER)
        for toggle in ("TCheckbutton", "TRadiobutton"):
            style.configure(toggle, indicatorbackground=FIELD, indicatorforeground=FG, upperbordercolor=BORDER,
                            lowerbordercolor=BORDER, indicatormargin=(1, 1, 4, 1), padding=2)
            style.map(toggle, indicatorbackground=[("pressed", BG), ("disabled", BG)],
                      background=[("active", BG)])
        for name, (_, dark) in INKS.items():
            style.configure(f"{name}.TLabel", foreground=dark)
        style.theme_use(current)
