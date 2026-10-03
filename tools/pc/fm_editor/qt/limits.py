"""The Limits page (a port of limits_tab.LimitsTab)."""
from __future__ import annotations

from .common import *      # noqa: F401,F403
from .common import (_qimage, _line_count, _pairs_text, _parse_pairs, _whole,
                     _card_image)      # noqa: F401


class LimitsMixin:
    def _build_limits_page(self, page, get, controls):
        fields = {}

        def rows(layout, group):
            for row, (key, label, retail, low, high, _storage) in enumerate(group):
                caption = QLabel(label)
                spin = QSpinBox()
                # One below the lowest the limit may be is "not set": the game's
                # own number, as an empty box means in the Tk form.
                spin.setRange(low - 1, high)
                spin.setSpecialValueText(self.LP_UNSET)
                spin.setValue(low - 1)
                spin.setMaximumWidth(130)
                spin.setMinimumWidth(96)
                own = "the start" if retail is None else f"{retail:,}"
                hint = QLabel(f"({own};  {low:,}–{high:,})")
                hint.setStyleSheet("color:#9aacc4")
                layout.addWidget(caption, row, 0)
                layout.addWidget(spin, row, 1)
                layout.addWidget(hint, row, 2)
                spin.valueChanged.connect(self._limits_edited)
                fields[key] = spin
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(2, 1)

        rows(get(QGridLayout, "simpleLimitsLayout"), limits.FIELDS)
        rows(get(QGridLayout, "advancedLimitsLayout"), limits.ADVANCED)
        advanced = get(QWidget, "advancedLimitsPanel")
        advanced.setVisible(False)
        toggle = get(QCheckBox, "showAdvancedCheck")
        toggle.toggled.connect(advanced.setVisible)

        table = get(QTableWidget, "duelistLpTable")
        table.setColumnCount(4)
        scope = get(QComboBox, "lpScopeCombo")
        value = get(QSpinBox, "lpValueSpin")
        value.setRange(1, limits.LIFE_POINTS_MAX)
        value.setValue(8000)
        controls.update(limits=fields, table=table, scope=scope, value=value,
                        status=get(QLabel, "limitsStatusLabel"), advanced=toggle,
                        rows={})
        for title in ("pageTitleLabel", "limitSettingsTitle", "startingLpTitle"):
            get(QLabel, title).setStyleSheet(
                "font-size:20px;font-weight:650;color:#f3f7fc" if title == "pageTitleLabel"
                else "font-size:16px;font-weight:650;color:#f3f7fc")
        for muted in ("pageSummaryLabel", "startingLpHint"):
            get(QLabel, muted).setStyleSheet("color:#9aacc4")
        for panel in ("limitSettingsPanel", "startingLpPanel"):
            get(QFrame, panel).setStyleSheet(
                f"QFrame#{panel} {{ background:#101b2b; border:1px solid #26374c; border-radius:10px; }}")
        # Without this the page's slack is shared out between the heading, the
        # summary and the status line, and the panels keep their bare hint.
        panels = get(QSplitter, "limitsSplitter")
        page_layout = page.layout()
        for index in range(page_layout.count()):
            page_layout.setStretch(index, 1 if page_layout.itemAt(index).widget() is panels else 0)
        panels.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for label in ("pageTitleLabel", "pageSummaryLabel", "limitsStatusLabel", "startingLpHint"):
            get(QLabel, label).setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        for panel in ("limitSettingsPanel", "startingLpPanel"):
            get(QFrame, panel).setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        # Room for the spin boxes, measured rather than guessed: 36 was short
        # of what a larger system font asks for and the boxes were clipped.
        spin_height = QSpinBox().sizeHint().height()
        table.verticalHeader().setDefaultSectionSize(max(36, spin_height + 4))
        settings_scroll = get(QScrollArea, "limitSettingsScroll")
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        get(QFrame, "limitSettingsPanel").setMinimumWidth(430)
        get(QFrame, "startingLpPanel").setMinimumWidth(420)
        splitter = get(QSplitter, "limitsSplitter")
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([520, 700])
        get(QPushButton, "applyLimitsButton").setStyleSheet(
            "background:#216cf1;border-color:#216cf1;color:white;font-weight:600")
        get(QPushButton, "setPlayerLpButton").clicked.connect(lambda: self._set_duelist_lp("player"))
        get(QPushButton, "setDuelistLpButton").clicked.connect(lambda: self._set_duelist_lp("opponent"))
        get(QPushButton, "resetDuelistLpButton").clicked.connect(self._reset_duelist_lp)
        get(QPushButton, "resetAllLimitsButton").clicked.connect(self._reset_all_limits)
        get(QPushButton, "revertLimitsButton").clicked.connect(self._revert_limits)
        get(QPushButton, "applyLimitsButton").clicked.connect(self._apply_limits)
        self.limits_filling = False
        self.limits_opened = None       # "limits" as the mod was opened with it
    def _limit_names(self):
        """Every duelist a row is drawn for: the wildcard, the disc's forty, and
        any other name the mod's own "limits" already carries."""
        known = list(DUELIST_NAMES[1:])
        extra = [name for name in (self.limits_duelists or {})
                 if name != "all" and name not in known]
        return ["all"] + known + sorted(extra)
    def _refresh_limits(self):
        c = self.workspace_controls.get("Limits")
        if not c:
            return
        stored = self.project.other.get("limits")
        if self.limits_opened is None:
            self.limits_opened = copy.deepcopy(stored)
        flat = limits.flatten(stored)
        self._limits_duelists = dict(flat.get("duelists", {}))
        self.limits_filling = True
        try:
            for key, spin in c["limits"].items():
                spin.setValue(flat[key] if key in flat else spin.minimum())
            self._fill_limit_duelists()
            scope = c["scope"]
            chosen = scope.currentData()
            scope.clear()
            scope.addItem("All duelists", "all")
            for name in self._limit_names()[1:]:
                scope.addItem(name, name)
            scope.setCurrentIndex(max(0, scope.findData(chosen)))
        finally:
            self.limits_filling = False
        self._limits_report()
    def _read_limits_form(self):
        c = self.workspace_controls["Limits"]
        flat = {}
        for key, spin in c["limits"].items():
            if spin.value() > spin.minimum():
                flat[key] = spin.value()
        duelists = {}
        for name, spins in c["rows"].items():
            player = spins[2].value() or None
            opponent = spins[3].value() or None
            if player is not None or opponent is not None:
                duelists[name] = (player, opponent)
        flat["duelists"] = duelists
        return flat
    def _limits_edited(self, *_):
        """Any field: store it at once, so nothing is lost by leaving the page."""
        if self.limits_filling or self.project is None:
            return
        self._limits_duelists = self._read_limits_form()["duelists"]
        before = self.project.other.get("limits")
        after = limits.build(self._read_limits_form(), before)
        if after == before:
            return
        if after is None:
            self.project.other.pop("limits", None)
        else:
            self.project.other["limits"] = after
        self._mark_dirty()
        self._limits_report()
    def _limits_report(self):
        c = self.workspace_controls["Limits"]
        problems = limits.check(self.project.other.get("limits")) if self.project else []
        c["status"].setText("\n".join(f"{level}: {where}: {message}"
                                      for level, where, message in problems[:8]))
        c["status"].setStyleSheet("color:#ff7777" if any(p[0] == "error" for p in problems)
                                  else "color:#f2c04c" if problems else "color:#9aacc4")
        return problems
    def _reset_all_limits(self):
        """Every limit back to the game's own number (LimitsTab.clear)."""
        c = self.workspace_controls["Limits"]
        self.limits_filling = True
        try:
            for spin in c["limits"].values():
                spin.setValue(spin.minimum())
            for spins in c["rows"].values():
                for spin in spins.values():
                    spin.setValue(0)
        finally:
            self.limits_filling = False
        self._limits_edited()
        self._refresh_limits()
    def _revert_limits(self):
        """Back to the "limits" the mod was opened with."""
        if self.limits_opened is None:
            self.project.other.pop("limits", None)
        else:
            self.project.other["limits"] = copy.deepcopy(self.limits_opened)
        self._mark_dirty()
        self._refresh_limits()
    def _apply_limits(self):
        self._limits_edited()
        problems = self._limits_report()
        errors = [p for p in problems if p[0] == "error"]
        c = self.workspace_controls["Limits"]
        if not problems:
            c["status"].setText("Limits applied; the loader would take all of them.")
            c["status"].setStyleSheet("color:#9aacc4")
        elif not errors:
            c["status"].setText(c["status"].text() + "\nApplied: the loader takes these with the notes above.")
        return not errors
