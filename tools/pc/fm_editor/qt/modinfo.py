"""The Mod info page."""
from __future__ import annotations

from .common import *      # noqa: F401,F403
from .common import (_qimage, _line_count, _pairs_text, _parse_pairs, _whole,
                     _card_image)      # noqa: F401


class ModinfoMixin:
    def _style_mod_info_page(self, page, get, controls):
        """The page's own look: the two JSON boxes as panels, written in the
        fixed-width face the Tk window writes them in, and the slack to them
        rather than to a label."""
        boxes = page.layout().itemAt(3).layout()
        page_layout = page.layout()
        for index in range(page_layout.count()):
            page_layout.setStretch(index, 1 if page_layout.itemAt(index).layout() is boxes else 0)
        # pageSummaryLabel is not reachable by name: the form gives it the
        # objectName "muted" so the window's own stylesheet draws it.
        for label in ("modSettingsHint", "modOtherHint"):
            get(QLabel, label).setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        for title in ("modSettingsEditLabel", "modOtherEditLabel"):
            get(QLabel, title).setStyleSheet("font-size:16px;font-weight:650;color:#f3f7fc")
        for muted in ("modSettingsHint", "modOtherHint", "modFolderLabel"):
            get(QLabel, muted).setStyleSheet("color:#9aacc4")
        for panel in ("modSettingsPanel", "modOtherPanel"):
            get(QFrame, panel).setStyleSheet(
                f"QFrame#{panel} {{ background:#101b2b; border:1px solid #26374c; border-radius:10px; }}")
        mono = QFont("Monospace", 10)
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        for box in ("settings", "other"):
            controls[box].setFont(mono)
    def _shown_other(self) -> dict:
        """The keys the Other box shows: all but the editor's own pages'."""
        return {key: value for key, value in self.project.other.items()
                if key not in self.MOD_INFO_OWNED}
    def _refresh_mod_info(self):
        c=self.workspace_controls.get("Mod info")
        if not c:return
        info=self.project.info
        for key in ("id","name","version","author"):c[key].setText(getattr(info,key))
        c["description"].setPlainText(info.description)
        c["settings"].setPlainText(json.dumps(info.settings,indent=2,ensure_ascii=False) if info.settings else "")
        other=self._shown_other()
        c["other"].setPlainText(json.dumps(other,indent=2,ensure_ascii=False) if other else "")
        source=self.project.source_dir
        c["folder"].setText(f"Folder: {source}" if source else "Not saved yet")
        c["status"].setText("")
    def _apply_mod_info(self):
        c=self.workspace_controls.get("Mod info")
        if not c:return True
        try:
            mod_id=c["id"].text().strip()
            if not validate.MOD_ID_RE.fullmatch(mod_id):raise ValueError("ID must use 1–63 letters, digits, hyphens, or underscores.")
            settings=json.loads(c["settings"].toPlainText()) if c["settings"].toPlainText().strip() else []
            other=json.loads(c["other"].toPlainText()) if c["other"].toPlainText().strip() else {}
            if not isinstance(settings,list):raise ValueError("Settings must be a JSON list.")
            if not isinstance(other,dict):raise ValueError("Other mod data must be a JSON object.")
            reserved=set(other)&self.MOD_INFO_RESERVED
            if reserved:raise ValueError(f"Edit {', '.join(sorted(reserved))} in the editor's own pages.")
        except ValueError as error:
            c["status"].setText(str(error));c["status"].setStyleSheet("color:#ff8f87");return False
        info=self.project.info
        before=(info.id,info.name,info.version,info.author,info.description,info.settings,dict(self.project.other))
        info.id=mod_id;info.name=c["name"].text();info.version=c["version"].text().strip()
        info.author=c["author"].text();info.description=c["description"].toPlainText()
        info.settings=settings
        # The pages of the editor's own keep theirs; the box never showed them.
        for key in self.MOD_INFO_OWNED:
            if key in self.project.other:
                other[key]=self.project.other[key]
        self.project.other=other
        after=(info.id,info.name,info.version,info.author,info.description,info.settings,dict(self.project.other))
        c["status"].setText("Changes applied." if after!=before else "No changes to apply.")
        c["status"].setStyleSheet("color:#7fd49b" if after!=before else "color:#9aacc4")
        if after!=before:self._mark_dirty()
        return True
