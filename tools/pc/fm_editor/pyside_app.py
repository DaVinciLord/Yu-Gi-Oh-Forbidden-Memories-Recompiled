"""The incremental PySide6 FM Editor frontend (Cards first).

It edits the same Project as the Tk frontend and saves through manifest.py;
the original editor remains available while the other modern tabs are built.
"""
from __future__ import annotations

import sys
import struct
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRect, QFile, QIODevice, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHeaderView,
    QButtonGroup, QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QListView, QStyledItemDelegate, QStyle, QTextEdit, QPlainTextEdit,
    QVBoxLayout, QWidget, QAbstractItemView, QRadioButton, QGroupBox, QTabWidget, QLayout)
from PySide6.QtUiTools import QUiLoader

from . import art, disc, gamedata, manifest, validate, pools as poolmath, bulk_fusions
from .gamedata import (ATTRIBUTE_NAMES, FRAME_NAMES, STAR_NAMES, TYPE_NAMES, DUELIST_NAMES, POOLS,
                       POOL_LABELS, POOL_TOTAL, DECK_SIZE, DECK_COPY_LIMIT, STARTER_WEIGHT_LIMIT,
                       exodia_piece)
from .model import KEY_RE, Project, StarterDeck

PC_TOOLS = Path(__file__).resolve().parents[1]
if str(PC_TOOLS) not in sys.path:
    sys.path.insert(0, str(PC_TOOLS))
import extract_images as image_extract  # noqa: E402


APP_QSS = """
QMainWindow, QWidget { background: #0b1220; color: #e5edf8; }
QWidget#root { background: #0b1220; color: #e5edf8; }
QMenuBar { background: #101b2b; color: #e5edf8; border-bottom: 1px solid #26374c; }
QMenuBar::item:selected, QMenu::item:selected { background: #1b3151; color: #ffffff; }
QMenu { background: #101b2b; color: #e5edf8; border: 1px solid #30435c; }
QWidget#topbar { background: #101b2b; border: 1px solid #26374c; border-radius: 10px; }
QWidget#sidebar { background: #101b2b; border: 1px solid #26374c; border-radius: 10px; }
QFrame#panel { background: #101b2b; border: 1px solid #26374c; border-radius: 10px; }
QWidget#artSectionCard { background: #101b2b; border: 1px solid #26374c; border-radius: 11px; }
QGroupBox { border: 1px solid #2a3d55; border-radius: 10px; margin-top: 14px;
  padding: 12px 8px 8px; background: #0f1a2a; color: #c9d8ed; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #aebfd6; }
QLabel#artPreviewImage { background: #0b1220; border: 1px solid #26374c; border-radius: 8px; }
QLabel { background: transparent; color: #dce6f4; }
QLabel#heading { font-size: 16px; font-weight: 650; color: #f3f7fc; }
QLabel#muted { color: #9aacc4; }
QLabel#artPartHeading { color: #f3f7fc; font-size: 13pt; font-weight: 650; padding: 4px 2px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox { background: #162337; color: #e5edf8; border: 1px solid #344862;
  border-radius: 6px; padding: 7px 9px; selection-background-color: #246df2; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #3984ff; }
QTableWidget { background: #101b2b; alternate-background-color: #142236; color: #dce6f4;
  gridline-color: #26374c; border: 1px solid #26374c; border-radius: 6px; selection-background-color: #1e64df;
  selection-color: #ffffff; }
QHeaderView::section { background: #162337; color: #aebfd6; border: 0; border-bottom: 1px solid #26374c;
 padding: 7px; font-weight: 600; }
QPushButton#fusionSortHeader { background: transparent; border: 0; color: #aebfd6; padding: 4px 7px;
  text-align: left; font-weight: 600; }
QPushButton#fusionSortHeader:hover { color: #ffffff; background: #162337; }
QPushButton#fusionSortHeader { background: transparent; border: 0; color: #aebfd6; padding: 4px 7px;
  text-align: left; font-weight: 600; }
QPushButton#fusionSortHeader:hover { color: #ffffff; background: #162337; }
QPushButton { background: #162337; color: #dce6f4; border: 1px solid #344862; border-radius: 6px;
 padding: 8px 13px; }
QPushButton:hover { background: #1b3151; border-color: #4f6b90; }
QPushButton:checked { background: #216cf1; border-color: #3984ff; color: #ffffff; }
QPushButton#artScaleButton { min-width: 42px; padding: 6px 10px; border-radius: 5px; }
QPushButton#primary { background: #216cf1; border-color: #216cf1; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #155bda; }
QPushButton:disabled { color: #75849a; }
QCheckBox { spacing: 8px; }
QStatusBar { background: #101b2b; color: #9aacc4; border-top: 1px solid #26374c; }
QSplitter::handle { background: transparent; width: 8px; }
QSplitter#workspaceSplitter::handle { background: #152236; width: 16px; margin: 4px 3px; border-radius: 3px; }
QScrollArea { border: 0; background: transparent; }
QToolTip { background: #20314a; color: white; border: 0; padding: 5px; }
"""


def _qimage(width: int, height: int, rgba: bytes) -> QImage:
    return QImage(rgba, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()


def _line_count(text: str) -> int:
    return validate.text_lines(text)


class CardIdSpinBox(QSpinBox):
    """Display card IDs with at least three digits."""

    def textFromValue(self, value: int) -> str:
        return f"{value:03d}"


def _card_image(project: Project, wa: bytes, cid: int, frame_cache: dict, scale: int = 1) -> QPixmap:
    """Compose the full 140x196 card sprite from its atlas fragments."""
    card = project.cards[cid]
    frame_index = card.shown_frame()
    texture_key = (frame_index, id(wa), "texture")
    if texture_key not in frame_cache:
        palette = image_extract.read_palette(wa, 0xF06800 + (8 + frame_index) * 0x200, 256)
        width, height, rgba = image_extract.decode(wa, 0xEE6800, 64, 256, 8, palette)
        face = _qimage(width, height, rgba)
        right_width, right_height, right_rgba = image_extract.decode(
            wa, 0xEE6800 + 16 * image_extract.SECTOR, 64, 256, 8, palette)
        frame_cache[texture_key] = (face, _qimage(right_width, right_height, right_rgba))

    is_monster = card.is_monster()
    frame_key = (frame_index, id(wa), "monster" if is_monster else "non-monster")
    if frame_key not in frame_cache:
        atlas, right_atlas = frame_cache[texture_key]
        # Merge the 128x192 face, both right-side pieces, and both bottom
        # pieces before drawing the image into the preview label.
        frame = QImage(140, 196, QImage.Format.Format_ARGB32_Premultiplied)
        frame.fill(QColor(0, 0, 0, 0))
        painter = QPainter(frame)
        painter.drawImage(QRect(0, 0, 128, 192), atlas, QRect(0, 0, 128, 192))
        # Four right strips are packed left-to-right: front top-right, back
        # top-right, front bottom-right, back bottom-right.
        right_top = right_atlas.copy(4, 0, 12, 128)
        right_bottom = right_atlas.copy(36, 0, 12, 68)
        painter.drawImage(QRect(128, 0, 12, 128), right_top)
        painter.drawImage(QRect(128, 128, 12, 68), right_bottom)
        if not is_monster:
            painter.drawImage(QRect(0, 144, 128, 48), atlas, QRect(0, 208, 128, 48))
        # Keep the existing lower outline and extend it with 62px left and
        # middle pieces plus the four-pixel corner at the right.
        bottom = atlas.copy(0, 0, 128, 4).mirrored(False, True)
        bottom_left = bottom.copy(0, 0, 62, 4)
        bottom_middle = bottom.copy(62, 0, 62, 4)
        painter.drawImage(QRect(0, 192, 64, 4), bottom_left)
        painter.drawImage(QRect(64, 192, 64, 4), bottom_middle)
        painter.end()
        frame_cache[frame_key] = frame

    scale = 4 if scale >= 4 else 1
    out = QImage(140 * scale, 196 * scale, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(QColor(0, 0, 0, 0))
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    p.drawImage(QRect(0, 0, 140 * scale, 196 * scale), frame_cache[frame_key])

    try:
        picture = art.in_game(project, wa, cid, "art", scale)
        if picture:
            # These are the frame atlas' actual transparent art-window bounds;
            # art.in_game supplies the same 102x96 texel size used by the game.
            p.drawImage(QRect(19 * scale, 50 * scale, 102 * scale, 96 * scale),
                        _qimage(picture.width, picture.height, picture.rgba))
    except (OSError, ValueError, art.pngio.PngError):
        pass

    p.end()
    return QPixmap.fromImage(out)


class FusionImageDelegate(QStyledItemDelegate):
    """Paint fusion cards as a grid or as image-and-name rows."""

    def __init__(self, image_for_card, parent=None):
        super().__init__(parent)
        self.image_for_card = image_for_card

    def sizeHint(self, option, index):
        view = self.parent()
        if view is not None and view.viewMode() == QListView.ViewMode.IconMode:
            width = view.gridSize().width() or max(420, view.viewport().width() // 3)
            return QSize(width, 190)
        return QSize(max(700, option.rect.width()), 82)

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_grid = self.parent() is not None and self.parent().viewMode() == QListView.ViewMode.IconMode
        painter.fillRect(rect, QColor("#1e64df") if selected else
                         (QColor("#142236") if index.row() % 2 else QColor("#101b2b")))
        painter.setPen(QColor("#30445e"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        pair = index.data(Qt.ItemDataRole.UserRole)
        outcome = index.data(int(Qt.ItemDataRole.UserRole) + 1)
        names = index.data(int(Qt.ItemDataRole.UserRole) + 2) or ("?", "?", "No fusion")
        state = index.data(int(Qt.ItemDataRole.UserRole) + 3) or "Stock"
        atk = index.data(int(Qt.ItemDataRole.UserRole) + 4) or 0
        defense = index.data(int(Qt.ItemDataRole.UserRole) + 5) or 0
        ids = (pair[0], pair[1], outcome) if pair else (None, None, None)
        fg = QColor("#ffffff") if selected else QColor("#dce6f4")
        painter.setPen(fg)

        if is_grid:
            slot_width = rect.width() / 3.0
            centers = tuple(round(rect.x() + slot_width * (i + 0.5)) for i in range(3))
            image_y = rect.y() + 10
            for pos, (cid, name, center) in enumerate(zip(ids, names, centers)):
                target = QRect(center - 34, image_y, 68, 66)
                self._draw_card(painter, target, cid)
                name_rect = QRect(round(rect.x() + slot_width * pos + 5), image_y + 72,
                                  max(1, round(slot_width - 10)), 48)
                text_flags = (int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) |
                              int(Qt.TextFlag.TextWordWrap))
                painter.drawText(name_rect, text_flags, name)
                if pos < 2:
                    painter.setPen(QColor("#aebfd6"))
                    painter.drawText(QRect(round(rect.x() + slot_width * (pos + 1) - 12), image_y,
                                           24, 66), Qt.AlignmentFlag.AlignCenter,
                                     "+" if pos == 0 else "→")
            painter.setPen(QColor("#93a6bf"))
            painter.drawText(QRect(rect.x() + 10, rect.bottom() - 24, rect.width() - 20, 18),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, state)
        else:
            gap = 12
            separator = 28
            status_width = 84
            stat_width = 70
            image_width = 46
            usable = max(210, rect.width() - 24 - 3 * (image_width + gap) - 2 * separator
                         - status_width - 2 * stat_width)
            text_width = usable // 3
            x = rect.x() + 12
            y = rect.y() + (rect.height() - 58) // 2
            for pos, (cid, name) in enumerate(zip(ids, names)):
                target = QRect(x, y, image_width, 58)
                self._draw_card(painter, target, cid)
                label = QRect(x + image_width + 6, rect.y() + 4,
                              text_width, rect.height() - 8)
                painter.drawText(label, Qt.AlignmentFlag.AlignVCenter, name)
                x += image_width + 6 + text_width
                if pos < 2:
                    painter.setPen(QColor("#aebfd6"))
                    painter.drawText(QRect(x, y, separator, 58), Qt.AlignmentFlag.AlignCenter,
                                     "+" if pos == 0 else "→")
                    x += separator
                    painter.setPen(fg)
            for value in (atk, defense):
                painter.setPen(fg)
                painter.drawText(QRect(x, rect.y() + 4, stat_width, rect.height() - 8),
                                 Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                                 str(value))
                x += stat_width
            status_rect = QRect(rect.right() - status_width - 12, rect.y() + 4,
                                status_width, rect.height() - 8)
            painter.setPen(QColor("#aebfd6"))
            painter.drawText(status_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             state)
        painter.restore()

    def _draw_card(self, painter, target, cid):
        painter.fillRect(target, QColor("#0b1220"))
        pixmap = self.image_for_card(cid) if cid is not None else None
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(target, pixmap)
        else:
            painter.setPen(QColor("#718198"))
            painter.drawText(target, Qt.AlignmentFlag.AlignCenter, "—")


class ModernEditor(QMainWindow):
    FILTERS = ["All cards", "Changed", "Added by the mod", "With notes", "Monsters", "Non-monsters"] + TYPE_NAMES
    NAV = ["Cards", "Art", "Campaign", "Fusions", "Equips", "Rituals", "Duelists", "Starter decks",
           "Mod info", "Problems"]

    def __init__(self, game=None, mod=None):
        super().__init__()
        self.setWindowTitle("FM Editor — Forbidden Memories Mod Studio")
        self.resize(1580, 980)
        self.setMinimumSize(1280, 760)
        self.files = self._load_game(game)
        self.retail = gamedata.load_game(self.files)
        self.project = Project(self.retail)
        self.frame_cache = {}
        self.fusion_art_cache = {}
        self.preview_scale = 1
        self.current = None
        self.current_art_card = None
        self.current_workspace = "Cards"
        self.workspace_forms = {}
        self.workspace_controls = {}
        self._loading_workspace = False
        self._loading = False
        self._last_type_index = None
        self.dirty = False
        self._build_ui()
        if mod:
            self.open_mod_path(mod)
        else:
            self.refresh_cards(select_id=1)
        self.refresh_art_list(select_id=self.current)
        for workspace_name in self.NAV[2:]:
            self._refresh_workspace(workspace_name)
        # The .ui layout has not reached its final geometry during __init__.
        # Render once the event loop has shown and laid out the preview label.
        QTimer.singleShot(0, self._render_preview)

    def _load_game(self, game):
        try:
            files = disc.load(game) if game else disc.find_game()
        except (OSError, disc.GameFilesError) as problem:
            files = None
            message = str(problem)
        else:
            message = ""
        if files is None:
            folder = QFileDialog.getExistingDirectory(self, "Choose the game files", str(Path.cwd()))
            if folder:
                try:
                    files = disc.load(folder)
                except (OSError, disc.GameFilesError) as problem:
                    QMessageBox.critical(self, "Game files", str(problem))
                    raise SystemExit(2)
            else:
                QMessageBox.warning(self, "Game files needed", message or
                                    "Choose a folder with SLUS_014.11 and DATA/WA_MRG.MRG to continue.")
                raise SystemExit(2)
        return files

    def _build_ui(self):
        self.setStyleSheet(APP_QSS)
        root = QWidget(objectName="root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)
        self.setCentralWidget(root)

        top = QWidget(objectName="topbar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 10, 14, 10)
        brand = QLabel("🎮  Yu-Gi-Oh! Forbidden Memories")
        brand.setStyleSheet("font-size:19px;font-weight:700;color:#f3f7fc")
        sub = QLabel("Mod Editor")
        sub.setStyleSheet("font-size:14px;color:#aebfd6")
        self.workspace_toggle = QPushButton("☰")
        self.workspace_toggle.setObjectName("workspaceToggle")
        self.workspace_toggle.setCheckable(True)
        self.workspace_toggle.setChecked(True)
        self.workspace_toggle.setToolTip("Collapse workspace navigation")
        self.workspace_toggle.setAccessibleName("Toggle workspace navigation")
        self.workspace_toggle.toggled.connect(self._toggle_workspace)
        top_layout.addWidget(self.workspace_toggle)
        top_layout.addWidget(brand)
        top_layout.addWidget(sub)
        top_layout.addStretch(1)
        self.game_label = QLabel("●  Game loaded")
        self.game_label.setStyleSheet("color:#13866a;font-weight:600")
        top_layout.addWidget(self.game_label)
        for label, slot in (("New mod", self.new_mod), ("Open mod", self.open_mod),
                            ("Preview mod.json", self.preview_manifest),
                            ("Save as…", lambda: self.save_mod(choose=True)), ("Save", self.save_mod)):
            button = QPushButton(label)
            if label == "Save":
                button.setObjectName("primary")
            button.clicked.connect(slot)
            top_layout.addWidget(button)
        outer.addWidget(top)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setObjectName("workspaceSplitter")
        body.setHandleWidth(20)
        outer.addWidget(body, 1)
        self.workspace_splitter = body
        sidebar = QWidget(objectName="sidebar")
        self.workspace_sidebar = sidebar
        sidebar.setMinimumWidth(155)
        sidebar.setMaximumWidth(230)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(10, 12, 10, 12)
        section = QLabel("WORKSPACE")
        section.setStyleSheet("font-size:11px;font-weight:700;color:#75849a")
        nav.addWidget(section)
        self.nav_buttons = {}
        self.workspace_indices = {"Cards": 0, "Art": 1}
        for name in self.NAV:
            b = QPushButton(name)
            b.setFlat(True)
            b.setCheckable(True)
            b.setMinimumHeight(38)
            b.setChecked(name == "Cards")
            b.clicked.connect(lambda checked=False, page=name: self.select_workspace(page))
            if name == "Cards":
                b.setObjectName("primary")
            nav.addWidget(b)
            self.nav_buttons[name] = b
        nav.addStretch(1)
        body.addWidget(sidebar)

        self.pages = QStackedWidget()
        cards = QWidget()
        self._build_cards(cards)
        self.pages.addWidget(cards)
        art_page = QWidget()
        self._build_art_page(art_page)
        self.pages.addWidget(art_page)
        for name in self.NAV[2:]:
            page = QWidget()
            self._build_workspace_page(name, page)
            self.workspace_indices[name] = self.pages.addWidget(page)
        body.addWidget(self.pages)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([185, 1350])
        self.statusBar().showMessage(f"Game files: {self.files.source}")

        self._build_menus()

    def _toggle_workspace(self, expanded):
        self.workspace_sidebar.setVisible(expanded)
        self.workspace_toggle.setToolTip(
            "Collapse workspace navigation" if expanded else "Expand workspace navigation")
        if expanded:
            self.workspace_splitter.setSizes([185, max(1, self.workspace_splitter.width() - 205)])

    def select_workspace(self, name):
        if name not in self.workspace_indices:
            return
        if self.current_workspace == "Cards" and name != "Cards":
            if self.current and not self.apply_card(quiet=True):
                self._set_navigation_active(self.current_workspace)
                return
        if self.current_workspace == "Mod info" and name != "Mod info":
            if not self._apply_mod_info():
                self._set_navigation_active(self.current_workspace)
                return
        if self.current_workspace == "Campaign" and name != "Campaign":
            if not self._apply_campaign():
                self._set_navigation_active(self.current_workspace)
                return
        self.pages.setCurrentIndex(self.workspace_indices[name])
        self.current_workspace = name
        self._set_navigation_active(name)
        if name == "Art" and self.current_art_card is None:
            self.refresh_art_list(select_id=self.current)
        if name in self.NAV[2:]:
            self._refresh_workspace(name)

    def _set_navigation_active(self, name):
        for page_name, button in self.nav_buttons.items():
            button.setChecked(page_name == name)
            button.setObjectName("primary" if page_name == name else "")
            button.style().unpolish(button)
            button.style().polish(button)

    def _build_art_page(self, parent):
        ui_path = Path(__file__).with_name("ui") / "arts_page.ui"
        ui_file = QFile(str(ui_path))
        if not ui_file.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError(f"Could not open Art Designer form {ui_path}: {ui_file.errorString()}")
        loader = QUiLoader()
        page = loader.load(ui_file, parent)
        ui_file.close()
        if page is None:
            raise RuntimeError(f"Could not load Art Designer form {ui_path}: {loader.errorString()}")
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page)
        self.art_form = page

        def widget(widget_type, name):
            found = page.findChild(widget_type, name)
            if found is None:
                raise RuntimeError(f"Art Designer form is missing widget {name!r}")
            return found

        self.art_search = widget(QLineEdit, "artSearchEdit")
        self.art_filter = widget(QComboBox, "artFilterCombo")
        self.art_table = widget(QTableWidget, "artCardTable")
        splitter = widget(QSplitter, "artsSplitter")
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 8)
        splitter.setSizes([320, 1150])
        self.art_count = widget(QLabel, "artCountLabel")
        self.art_status = widget(QLabel, "artStatusLabel")
        # The compact Art form has a single title/status pair; older forms
        # exposed separate labels for the selected card, instructions, and pack.
        # Use the compact title as the heading and treat the extra labels as
        # optional so either Designer layout can be loaded.
        self.art_heading = (page.findChild(QLabel, "selectedArtCardLabel")
                            or page.findChild(QLabel, "artworkTitle"))
        if self.art_heading is None:
            raise RuntimeError("Art Designer form is missing its artwork title label")
        self.art_pack_status = page.findChild(QLabel, "texturePackStatusLabel")
        self.art_instructions = page.findChild(QLabel, "artInstructionsLabel")
        self.art_previews = {}
        self.art_info = {}
        self.art_scales = {}
        canvas_sizes = {"art": QSize(240, 226), "thumbnail": QSize(180, 144),
                        "title": QSize(288, 42)}
        for part, stem in (("art", "picture"), ("thumbnail", "thumbnail"), ("title", "title")):
            # Designer forms may use a named QWidget wrapper or place the named
            # category layout directly in the scroll area. Keep the UI flexible:
            # only style a wrapper when one exists; the category contents are
            # found by their stable object names below either way.
            section = page.findChild(QWidget, stem + "Tab")
            if section is not None:
                section.setObjectName("artSectionCard")
            elif page.findChild(QVBoxLayout, stem + "Layout") is None:
                raise RuntimeError(
                    f"Art Designer form is missing the {stem!r} category layout"
                )
            widget(QLabel, stem + "HelpLabel").setObjectName("artPartHeading")
            self.art_previews[part] = {
                "disc": widget(QLabel, stem + "DiscPreview"),
                "game": widget(QLabel, stem + "GamePreview"),
                "mod": widget(QLabel, stem + "ModPreview"),
            }
            self.art_info[part] = {
                "disc": widget(QLabel, stem + "DiscInfo"),
                "game": widget(QLabel, stem + "GameInfo"),
                "mod": widget(QLabel, stem + "ModInfo"),
            }
            scale_group = QButtonGroup(self)
            scale_group.setExclusive(True)
            self.art_scales[part] = scale_group
            for scale in (1, 2, 4):
                button = widget(QPushButton, f"{stem}Scale{scale}Button")
                button.setObjectName("artScaleButton")
                scale_group.addButton(button, scale)
                if scale == 1:
                    button.setChecked(True)
            scale_group.idClicked.connect(lambda scale, p=part: self._change_art_scale(p, scale))
            for preview in self.art_previews[part].values():
                preview.setFixedSize(canvas_sizes[part])
                preview.setObjectName("artPreviewImage")
            for suffix in ("DiscGroup", "GameGroup", "ModGroup"):
                widget(QWidget, stem + suffix).setObjectName("artPreviewTile")
            button_names = {
                "import": f"import{stem.title()}Button",
                "export_disc": f"export{stem.title()}DiscButton",
                "export_mod": f"export{stem.title()}ModButton",
                "revert": f"revert{stem.title()}Button",
            }
            for action, handler in (("import", self.import_art), ("export_disc", self.export_art_disc),
                                    ("export_mod", self.export_art_mod), ("revert", self.revert_art)):
                button = widget(QPushButton, button_names[action])
                button.clicked.connect(lambda checked=False, p=part, fn=handler: fn(p))
                if action == "import":
                    button.setObjectName("primary")
                if action in ("export_mod", "revert"):
                    button.setEnabled(False)
                self.art_info[part][action] = button

        self.art_filter.addItems(["All cards", "Art of the mod", "Added by the mod"])
        self.art_table.setColumnWidth(0, 62)
        self.art_table.setColumnWidth(1, 220)
        self.art_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.art_table.setSortingEnabled(True)
        self.art_table.verticalHeader().setVisible(False)
        self.art_search.textChanged.connect(self.refresh_art_list)
        self.art_filter.currentTextChanged.connect(self.refresh_art_list)
        self.art_table.itemSelectionChanged.connect(self.select_art_card)

    def _build_workspace_page(self, name, parent):
        filenames = {"Campaign": "campaign_page.ui", "Fusions": "fusions_page.ui",
                     "Equips": "equips_page.ui", "Rituals": "rituals_page.ui",
                     "Duelists": "duelists_page.ui", "Starter decks": "starter_decks_page.ui",
                     "Mod info": "mod_info_page.ui", "Problems": "problems_page.ui"}
        path = Path(__file__).with_name("ui") / filenames[name]
        source = QFile(str(path))
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError(f"Could not open {name} form {path}: {source.errorString()}")
        loader = QUiLoader()
        page = loader.load(source, parent)
        source.close()
        if page is None:
            raise RuntimeError(f"Could not load {name} form {path}: {loader.errorString()}")
        wrapper = QVBoxLayout(parent)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(page)
        controls = {"page": page}
        self.workspace_forms[name] = page
        self.workspace_controls[name] = controls
        if name == "Rituals":
            splitter=page.findChild(QSplitter,"ritualSplit")
            if splitter is not None:
                splitter.setSizes([330,950])
                splitter.setStretchFactor(0,0)
                splitter.setStretchFactor(1,1)
            recipe_layout=page.findChild(QVBoxLayout,"ritualRecipeLayout")
            if recipe_layout is not None:
                recipe_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        if name == "Duelists":
            splitter=page.findChild(QSplitter,"duelistSplit")
            if splitter is not None:
                splitter.setChildrenCollapsible(False)
                splitter.setStretchFactor(0,0)
                splitter.setStretchFactor(1,1)
                splitter.setSizes([560,900])

        def get(cls, key):
            item = page.findChild(cls, key)
            if item is None:
                raise RuntimeError(f"{name} form is missing {key!r}")
            return item

        def optional(cls, key):
            return page.findChild(cls, key)

        if name == "Campaign":
            controls.update(data=get(QPlainTextEdit, "campaignDataEdit"),
                            status=get(QLabel, "campaignStatusLabel"))
            get(QPushButton, "applyCampaignButton").clicked.connect(self._apply_campaign)
        elif name == "Fusions":
            fusion_pages = get(QTabWidget, "fusionPages")
            header = get(QWidget, "fusionImageHeader")
            sort_names = ("fusionSortCardAButton", "fusionSortCardBButton",
                          "fusionSortResultButton", "fusionSortAtkButton",
                          "fusionSortDefButton", "fusionSortStateButton")
            sort_headers = [get(QPushButton, control_name) for control_name in sort_names]
            header_layout = header.layout()
            for column, button in enumerate(sort_headers):
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda checked=False, col=column: self._sort_fusions(col))
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
                button.setStyleSheet("text-align:center")
            # Plus/arrow separators take 18 px immediately before the State column
            # in the row delegate; reserve the same space in the header layout.
            if not header.property("fusionStateGapAdded"):
                header_layout.insertSpacing(5, 18)
                header.setProperty("fusionStateGapAdded", True)
            controls.update(search=get(QLineEdit, "fusionSearchEdit"),
                            changed=get(QCheckBox, "fusionChangedCheck"),
                            count=get(QLabel, "fusionCountLabel"), table=get(QTableWidget, "fusionTable"),
                            image_list=get(QListWidget, "fusionImageList"),
                            stack=get(QStackedWidget, "fusionViewStack"),
                            grid=get(QPushButton, "fusionGridButton"),
                            list=get(QPushButton, "fusionListButton"), header=header,
                            sort_headers=sort_headers, sort=(0, True), pages=fusion_pages,
                            search_materials=get(QRadioButton, "fusionSearchMaterialsRadio"),
                            search_results=get(QRadioButton, "fusionSearchResultsRadio"),
                            search_both=get(QRadioButton, "fusionSearchBothRadio"))
            controls["search"].setMaximumWidth(360)
            controls["search_materials"].toggled.connect(self._refresh_fusions)
            controls["search_results"].toggled.connect(self._refresh_fusions)
            controls["search_both"].toggled.connect(self._refresh_fusions)
            table = controls["table"]
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["Card A", "Card B", "Result", "ATK", "DEF", "State"])
            view_group = QButtonGroup(self)
            view_group.setExclusive(True)
            view_group.addButton(controls["grid"], 0)
            view_group.addButton(controls["list"], 1)
            controls["view_group"] = view_group
            view_group.idClicked.connect(self._set_fusion_view)
            controls["image_list"].setItemDelegate(
                FusionImageDelegate(self._fusion_card_pixmap, controls["image_list"]))
            self._set_fusion_view(1)
            controls["image_list"].itemDoubleClicked.connect(lambda *_: self._edit_fusion())
            controls["search"].textChanged.connect(self._refresh_fusions)
            controls["changed"].toggled.connect(self._refresh_fusions)
            controls["table"].cellDoubleClicked.connect(lambda *_: self._edit_fusion())
            for key, callback in (("addFusionButton", lambda: self._edit_fusion(add=True)),
                                  ("editFusionButton", self._edit_fusion),
                                  ("removeFusionButton", self._remove_fusions),
                                  ("revertFusionButton", self._revert_fusions)):
                get(QPushButton, key).clicked.connect(callback)
            self._build_bulk_fusions_page(get(QWidget, "genericFusionTab"), controls)
        elif name == "Equips":
            controls.update(equips=get(QTableWidget, "equipTable"),
                            monsters=get(QTableWidget, "equipMonsterTable"),
                            heading=get(QLabel, "equipHeadingLabel"),
                            preview=get(QLabel, "equipCardPreview"),
                            search=get(QLineEdit, "equipSearchEdit"),
                            monster_search=get(QLineEdit, "equipMonsterSearchEdit"),
                            type=get(QComboBox, "equipTypeCombo"))
            controls["type"].addItems(TYPE_NAMES[:20])
            controls["search"].textChanged.connect(self._filter_equip_cards)
            controls["monster_search"].textChanged.connect(self._filter_equip_monsters)
            controls["equips"].itemSelectionChanged.connect(self._select_equip)
            controls["monsters"].itemChanged.connect(self._toggle_equip_monster)
            controls["monsters"].setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            controls["monsters"].setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            for key, callback in (("addMonsterButton", self._add_equip_monster),
                                  ("addTypeButton", lambda: self._equip_by_type(True)),
                                  ("removeTypeButton", lambda: self._equip_by_type(False)),
                                  ("removeMonsterButton", self._remove_equip_monsters),
                                  ("revertEquipButton", self._revert_equip)):
                get(QPushButton, key).clicked.connect(callback)
        elif name == "Rituals":
            controls.update(cards=get(QTableWidget, "ritualCardTable"),
                            preview=get(QLabel, "ritualCardPreview"),
                            card_meta={key:widget for key,widget in (("id",optional(QLineEdit,"ritualMetaId")),
                                       ("name",optional(QLineEdit,"ritualMetaName")),
                                       ("type",optional(QComboBox,"ritualMetaType")),
                                       ("attribute",optional(QComboBox,"ritualMetaAttribute")),
                                       ("level",optional(QSpinBox,"ritualMetaLevel")),
                                       ("atk",optional(QSpinBox,"ritualMetaAtk")),
                                       ("def",optional(QSpinBox,"ritualMetaDef"))) if widget is not None},
                            search=get(QLineEdit, "ritualSearchEdit"),
                            heading=get(QLabel, "ritualRecipeHeading"),
                            tribute_images=[get(QLabel,f"ritualTribute{i}Image") for i in range(1,4)],
                            tribute_fields=[{"id":get(QLineEdit,f"ritualTribute{i}Id"),"atk":get(QSpinBox,f"ritualTribute{i}Atk"),
                                             "def":get(QSpinBox,f"ritualTribute{i}Def"),"type":get(QComboBox,f"ritualTribute{i}Type"),
                                             "attribute":get(QComboBox,f"ritualTribute{i}Attribute"),"level":get(QSpinBox,f"ritualTribute{i}Level")} for i in range(1,4)],
                            tribute_combos=[get(QComboBox,f"ritualTribute{i}Combo") for i in range(1,4)],
                            summon_combo=get(QComboBox,"ritualSummonCombo"),
                            summon_image=get(QLabel,"ritualSummonImage"),
                            summon_fields={"id":get(QLineEdit,"ritualSummonId"),"atk":get(QSpinBox,"ritualSummonAtk"),
                                           "def":get(QSpinBox,"ritualSummonDef"),"type":get(QComboBox,"ritualSummonType"),
                                           "attribute":get(QComboBox,"ritualSummonAttribute"),"level":get(QSpinBox,"ritualSummonLevel")},
                            state=get(QLabel,"ritualStateLabel"))
            self.ritual_pending = {}
            controls["cards"].setColumnCount(3)
            controls["cards"].setHorizontalHeaderLabels(["ID", "Ritual card", "State"])
            for combo in controls["tribute_combos"]+[controls["summon_combo"]]:
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                combo.addItem("Choose a card…", None)
                for cid in self.project.monsters():
                    combo.addItem(self.project.card_label(cid), cid)
                combo.currentIndexChanged.connect(self._stage_ritual_selector_recipe)
            for fields in [controls["card_meta"],*controls["tribute_fields"],controls["summon_fields"]]:
                for key in ("type","attribute"):
                    if fields.get(key) is not None:
                        fields[key].addItems(TYPE_NAMES if key == "type" else ATTRIBUTE_NAMES)
                        fields[key].setEnabled(False)
                for key in ("id","name"):
                    if fields.get(key) is not None:fields[key].setReadOnly(True)
                for key in ("level","atk","def"):
                    if fields.get(key) is not None:fields[key].setReadOnly(True)
            controls["cards"].itemSelectionChanged.connect(self._select_ritual)
            controls["search"].textChanged.connect(self._filter_ritual_cards)
            controls["cards"].horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
            controls["cards"].horizontalHeader().resizeSection(0,58)
            controls["cards"].horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
            controls["cards"].horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
            controls["cards"].horizontalHeader().resizeSection(2,90)
            for key, callback in (("editRitualButton", self._apply_ritual_selector_recipe),
                                  ("removeRitualButton", self._remove_ritual),
                                  ("revertRitualButton", self._revert_ritual)):
                get(QPushButton, key).clicked.connect(callback)
        elif name == "Duelists":
            controls.update(duelists=get(QTableWidget, "duelistTable"),
                            search=get(QLineEdit, "duelistSearchEdit"),
                            page=get(QComboBox, "duelistPageCombo"),
                            portrait=get(QLabel, "duelistPortraitPreview"),
                            name=get(QLineEdit, "duelistNameEdit"),
                            id=get(QLineEdit, "duelistIdEdit"),
                            base=get(QComboBox, "duelistBaseCombo"),
                            position=get(QComboBox, "duelistPositionCombo"),
                            pool=get(QComboBox, "duelistPoolCombo"),
                            summary=get(QLabel, "duelistPoolSummary"),
                            table=get(QTableWidget, "duelistPoolTable"),
                            weight=get(QSpinBox, "duelistWeightSpin"))
            controls["remove"] = get(QPushButton, "removeDuelistButton")
            grid=controls["duelists"]
            grid.setRowCount(5);grid.setColumnCount(8)
            grid.horizontalHeader().setVisible(False);grid.verticalHeader().setVisible(False)
            grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            grid.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            grid.setIconSize(QSize(48,48));grid.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            grid.cellClicked.connect(self._select_duelist)
            controls["page"].addItems([f"Page {i + 1}" for i in range(4)])
            controls["page"].currentIndexChanged.connect(self._refresh_duelists)
            controls["search"].textChanged.connect(self._refresh_duelists)
            controls["base"].addItem("Choose a base…",None)
            for did,base_name in enumerate(DUELIST_NAMES):
                if did:controls["base"].addItem(f"{did:02d} · {base_name}",did)
            controls["position"].addItem("Automatic · first empty",None)
            for slot in range(40,128):controls["position"].addItem(f"Position {slot}",slot)
            controls["pool"].addItems([POOL_LABELS[p] for p in POOLS])
            controls["pool"].currentIndexChanged.connect(self._refresh_duelist_pool)
            controls["table"].itemSelectionChanged.connect(self._select_pool_card)
            get(QPushButton,"duelistPortraitButton").clicked.connect(self._choose_duelist_portrait)
            get(QPushButton,"addDuelistButton").clicked.connect(lambda: self._save_duelist(True))
            get(QPushButton,"applyDuelistButton").clicked.connect(lambda: self._save_duelist(False))
            controls["remove"].clicked.connect(self._remove_duelist)
            for key, callback in (("addPoolCardButton", self._add_pool_card),
                                  ("setPoolWeightButton", self._set_pool_weight),
                                  ("removePoolCardButton", self._remove_pool_cards),
                                  ("normalizePoolButton", self._normalize_pool),
                                  ("revertPoolButton", self._revert_pool)):
                get(QPushButton, key).clicked.connect(callback)
        elif name == "Starter decks":
            controls.update(decks=get(QTableWidget, "starterDeckTable"),
                            name=get(QLineEdit, "starterNameEdit"),
                            weight=get(QSpinBox, "starterWeightSpin"),
                            cards=get(QTableWidget, "starterCardTable"),
                            copies=get(QSpinBox, "starterCopiesSpin"))
            controls["decks"].itemSelectionChanged.connect(self._select_starter_deck)
            controls["cards"].itemSelectionChanged.connect(self._select_starter_card)
            for key, callback in (("addDeckButton", self._add_starter_deck),
                                  ("removeDeckButton", self._remove_starter_deck),
                                  ("applyDeckButton", self._apply_starter_details),
                                  ("addDeckCardButton", self._add_starter_card),
                                  ("setDeckCopiesButton", self._set_starter_copies),
                                  ("removeDeckCardButton", self._remove_starter_cards)):
                get(QPushButton, key).clicked.connect(callback)
        elif name == "Mod info":
            controls.update(id=get(QLineEdit, "modIdEdit"), name=get(QLineEdit, "modNameEdit"),
                            version=get(QLineEdit, "modVersionEdit"), author=get(QLineEdit, "modAuthorEdit"),
                            description=get(QPlainTextEdit, "modDescriptionEdit"),
                            settings=get(QPlainTextEdit, "modSettingsEdit"),
                            other=get(QPlainTextEdit, "modOtherEdit"), status=get(QLabel, "modInfoStatusLabel"))
            get(QPushButton, "applyModInfoButton").clicked.connect(self._apply_mod_info)
            get(QPushButton, "previewModJsonButton").clicked.connect(self.preview_manifest)
        elif name == "Problems":
            controls.update(table=get(QTableWidget, "problemsTable"),
                            summary=get(QLabel, "problemSummaryLabel"))
            get(QPushButton, "checkModButton").clicked.connect(self._refresh_problems)
        for table in page.findChildren(QTableWidget):
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        if name == "Equips":
            # The shared table setup above stretches every column. Override it
            # here so checkbox and numeric ID columns stay compact.
            equip_header=controls["equips"].horizontalHeader()
            equip_header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
            equip_header.resizeSection(0,58)
            equip_header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
            equip_header.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
            equip_header.resizeSection(2,58)
            monster_header=controls["monsters"].horizontalHeader()
            monster_header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
            monster_header.resizeSection(0,42)
            monster_header.setSectionResizeMode(1,QHeaderView.ResizeMode.Fixed)
            monster_header.resizeSection(1,54)
            for col in (2,3,4):
                monster_header.setSectionResizeMode(col,QHeaderView.ResizeMode.Stretch)
        elif name == "Rituals":
            card_header=controls["cards"].horizontalHeader()
            card_header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
            card_header.resizeSection(0,58)
            card_header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self._refresh_workspace(name)

    def _refresh_workspace(self, name):
        if not hasattr(self, "workspace_controls") or name not in self.workspace_controls:
            return
        c, p = self.workspace_controls[name], self.project
        if name == "Campaign":
            value = p.other.get("story", {})
            c["data"].setPlainText(json.dumps(value, indent=2, ensure_ascii=False) if value else "")
            c["status"].setText("Story data found in mod.json." if value else
                                "No story key is present. This project format does not include a campaign editor.")
        elif name == "Fusions":
            self._refresh_fusions()
            self._refresh_bulk_fusion_plan()
        elif name == "Equips":
            self._refresh_equips()
        elif name == "Rituals":
            self._refresh_rituals()
        elif name == "Duelists":
            self._refresh_duelists()
        elif name == "Starter decks":
            self._refresh_starter_decks()
        elif name == "Mod info":
            self._refresh_mod_info()
        elif name == "Problems":
            self._refresh_problems()

    @staticmethod
    def _put_rows(table, rows):
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))

    def _card_combo(self, parent, selected=None, ids=None):
        combo = QComboBox(parent)
        for cid in sorted(ids if ids is not None else self.project.cards):
            card = self.project.cards.get(cid)
            if card is not None:
                combo.addItem(f"{cid:03d}  {card.name}", cid)
        if selected is not None:
            index = combo.findData(selected)
            if index >= 0: combo.setCurrentIndex(index)
        return combo

    def _set_fusion_view(self, mode):
        controls = self.workspace_controls.get("Fusions")
        if not controls:
            return
        image_list = controls["image_list"]
        controls["stack"].setCurrentWidget(image_list)
        grid = int(mode) == 0
        image_list.setViewMode(QListView.ViewMode.IconMode if grid else QListView.ViewMode.ListMode)
        image_list.setFlow(QListView.Flow.LeftToRight if grid else QListView.Flow.TopToBottom)
        image_list.setWrapping(grid)
        image_list.setResizeMode(QListView.ResizeMode.Adjust)
        image_list.setMovement(QListView.Movement.Static)
        image_list.setSpacing(10 if grid else 4)
        image_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        image_list.verticalScrollBar().setSingleStep(96 if grid else 52)
        if grid:
            width = max(420, (image_list.viewport().width() - 28) // 3)
            image_list.setGridSize(QSize(width, 190))
        else:
            image_list.setGridSize(QSize())
        controls["header"].setVisible(not grid)
        image_list.doItemsLayout()
        self._sync_fusion_header()

    def _sync_fusion_header(self):
        """Match the Designer header columns to the image-row delegate geometry."""
        controls = self.workspace_controls.get("Fusions")
        if not controls:
            return
        image_list = controls["image_list"]
        header = controls["header"]
        layout = header.layout()
        if layout is None:
            return

        row_width = max(1, image_list.viewport().width())
        # Reproduce FusionImageDelegate.paint()'s column widths exactly.
        name_width = max(210, row_width - 478) // 3
        widths = (80 + name_width, 80 + name_width, 52 + name_width, 70, 70, 84)

        # The header sits outside the list viewport, so account for the frame and
        # vertical scrollbar that reduce the actual row width.
        viewport_inset = max(0, header.width() - row_width)
        margins = layout.contentsMargins()
        layout.setContentsMargins(12, margins.top(), 12 + viewport_inset,
                                  margins.bottom())
        for column, width in enumerate(widths):
            controls["sort_headers"][column].setFixedWidth(width)

    def _fusion_card_pixmap(self, cid):
        if cid is None or self.files is None:
            return None
        try:
            if cid not in self.fusion_art_cache:
                image = art.in_game(self.project, self.files.wa, cid, "art", 1)
                if image is None:
                    return None
                pixmap = QPixmap.fromImage(_qimage(image.width, image.height, image.rgba))
                self.fusion_art_cache[cid] = pixmap.scaled(
                    QSize(56, 58), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation)
            return self.fusion_art_cache[cid]
        except (IndexError, KeyError, ValueError):
            return None

    def _refresh_fusions(self, *_):
        c = self.workspace_controls.get("Fusions")
        if not c: return
        table, image_list, p = c["table"], c["image_list"], self.project
        query = c["search"].text().strip().casefold()
        changed_only = c["changed"].isChecked()
        rows = []
        for pair in sorted(set(p.fusions) | set(p.retail.fusions)):
            status = p.fusion_status(pair)
            result = p.fusions.get(pair) or p.retail.fusions.get(pair)
            a, b = p.card_label(pair[0]), p.card_label(pair[1])
            outcome = p.card_label(result) if result else ("No fusion" if pair not in p.retail.fusions else "Removed")
            if changed_only and status in ("", "glitch"): continue
            if query:
                materials_match = any(
                    query in text.casefold()
                    for text in (a, b, str(pair[0]), str(pair[1])))
                result_match = query in outcome.casefold() or (
                    result is not None and query in str(result))
                if c["search_both"].isChecked():
                    matched = materials_match or result_match
                elif c["search_results"].isChecked():
                    matched = result_match
                else:
                    matched = materials_match
                if not matched:
                    continue
            result_card = p.cards.get(result) if result else None
            atk = result_card.attack if result_card else 0
            defense = result_card.defense if result_card else 0
            rows.append((pair, a, b, outcome, status or ("Glitch" if status == "glitch" else "Stock"),
                         atk, defense))
        sort_column, ascending = c.get("sort", (0, True))
        sort_keys = (lambda row: row[0][0], lambda row: row[0][1],
                     lambda row: p.fusions.get(row[0]) or p.retail.fusions.get(row[0]) or 0,
                     lambda row: row[5], lambda row: row[6], lambda row: row[4].casefold())
        rows.sort(key=sort_keys[sort_column], reverse=not ascending)
        self._update_fusion_sort_headers()
        selected_pairs = [item.data(Qt.ItemDataRole.UserRole)
                          for item in image_list.selectedItems()]
        table.setRowCount(len(rows))
        image_list.clear()
        for i, (pair, a, b, result, status, atk, defense) in enumerate(rows):
            for col, value in enumerate((a, b, result, atk, defense, status)):
                item = QTableWidgetItem(str(value))
                if col == 0: item.setData(Qt.ItemDataRole.UserRole, pair)
                table.setItem(i, col, item)
            outcome_id = p.fusions.get(pair)
            if outcome_id is None:
                outcome_id = p.retail.fusions.get(pair)
            row_item = QListWidgetItem(f"{a} + {b} → {result} · {status}")
            row_item.setData(Qt.ItemDataRole.UserRole, pair)
            row_item.setData(int(Qt.ItemDataRole.UserRole) + 1, outcome_id)
            row_item.setData(int(Qt.ItemDataRole.UserRole) + 2, (a, b, result))
            row_item.setData(int(Qt.ItemDataRole.UserRole) + 3, status)
            row_item.setData(int(Qt.ItemDataRole.UserRole) + 4, atk)
            row_item.setData(int(Qt.ItemDataRole.UserRole) + 5, defense)
            image_list.addItem(row_item)
            if pair in selected_pairs:
                row_item.setSelected(True)
        c["count"].setText(f"{len(rows):,} fusion rules")

    def _sort_fusions(self, column):
        controls = self.workspace_controls.get("Fusions")
        if not controls:
            return
        old_column, ascending = controls.get("sort", (0, True))
        controls["sort"] = (column, not ascending if column == old_column else True)
        self._refresh_fusions()

    def _update_fusion_sort_headers(self):
        controls = self.workspace_controls.get("Fusions")
        if not controls:
            return
        column, ascending = controls.get("sort", (0, True))
        titles = ("Card A", "Card B", "Fusion result", "ATK", "DEF", "State")
        for index, button in enumerate(controls["sort_headers"]):
            arrow = (" ↑" if ascending else " ↓") if index == column else ""
            button.setText(titles[index] + arrow)

    def _build_bulk_fusions_page(self, page, controls):
        """Bind the Generic Fusions Designer form to the fusion planner."""
        def get(cls, name):
            item = page.findChild(cls, name)
            if item is None:
                raise RuntimeError(f"Fusions Designer form is missing {name!r}")
            return item

        def bind_filter(side):
            cap = side.upper()
            types = get(QListWidget, f"material{cap}TypeList")
            stars = get(QListWidget, f"material{cap}StarList")
            self._populate_checkable_list(types, TYPE_NAMES[:20])
            self._populate_checkable_list(stars, STAR_NAMES[1:])
            return {
                "group": get(QGroupBox, f"material{cap}Group"),
                "kinds": {}, "types": types, "stars": stars,
                "attributes": [get(QCheckBox, f"material{cap}Attribute{i}") for i in range(6)],
                "bounds": {
                    "atk_min": get(QLineEdit, f"material{cap}AtkMin"),
                    "atk_max": get(QLineEdit, f"material{cap}AtkMax"),
                    "def_min": get(QLineEdit, f"material{cap}DefMin"),
                    "def_max": get(QLineEdit, f"material{cap}DefMax"),
                },
                "name": get(QLineEdit, f"material{cap}Name"),
                "text": get(QLineEdit, f"material{cap}Text"),
                "cards": get(QLineEdit, f"material{cap}Cards"),
                "results_only": get(QCheckBox, f"material{cap}ResultsOnly"),
                "count": get(QLabel, f"material{cap}CountLabel"),
                "level_any": get(QRadioButton, f"material{cap}LevelAny"),
                "level_exact_radio": get(QRadioButton, f"material{cap}LevelExactRadio"),
                "level_range_radio": get(QRadioButton, f"material{cap}LevelRangeRadio"),
                "level_exact": get(QSpinBox, f"material{cap}LevelExact"),
                "level_min": get(QSpinBox, f"material{cap}LevelMin"),
                "level_max": get(QSpinBox, f"material{cap}LevelMax"),
                "advanced_toggle": get(QPushButton, f"material{cap}AdvancedToggle"),
                "advanced": get(QLayout, f"material{cap}AdvancedLayout"),
            }

        controls["bulk_filters"] = {"a": bind_filter("a"), "b": bind_filter("b")}
        get(QPushButton, "copyAToBButton").clicked.connect(lambda: self._copy_bulk_filter("a", "b"))
        get(QPushButton, "copyBToAButton").clicked.connect(lambda: self._copy_bulk_filter("b", "a"))

        choose_card = get(QRadioButton, "chooseFusionCardRadio")
        use_ladder = get(QRadioButton, "fusionLadderRadio")
        result_picker = get(QPushButton, "chooseFusionResultButton")
        ladder = get(QLineEdit, "fusionLadderCandidates")
        stronger = get(QCheckBox, "fusionStrongerCheck")
        allow_self = get(QCheckBox, "fusionAllowSelfCheck")
        overwrite = get(QCheckBox, "fusionOverwriteCheck")
        intro = get(QLabel, "genericFusionIntroLabel")
        intro.setStyleSheet("color:#9aacc4")
        summary = get(QLabel, "genericFusionSummaryLabel")
        summary.setStyleSheet("font-size:16px; font-weight:650")
        errors = get(QLabel, "genericFusionErrorsLabel")
        errors.setStyleSheet("color:#ff9292")
        warnings = get(QLabel, "genericFusionWarningsLabel")
        warnings.setStyleSheet("color:#9aacc4")
        for key in ("materialACountLabel", "materialBCountLabel"):
            get(QLabel, key).setStyleSheet("color:#9aacc4")
        preview = get(QTableWidget, "genericFusionPlanTable")
        preview.setAlternatingRowColors(True)
        preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        preview.verticalHeader().setVisible(False)
        preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        apply = get(QPushButton, "applyBulkFusionsButton")
        apply.setObjectName("primary")
        undo = get(QPushButton, "undoBulkFusionsButton")
        splitter = get(QSplitter, "genericFusionSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1400, 700])
        left_scroll = get(QScrollArea, "genericFusionLeftScroll")
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        controls["bulk"] = {"choose_card": choose_card, "use_ladder": use_ladder,
                            "result_button": result_picker, "result_id": 0, "ladder": ladder,
                            "stronger": stronger, "allow_self": allow_self,
                            "overwrite": overwrite, "summary": summary, "errors": errors,
                            "warnings": warnings, "preview": preview, "apply": apply,
                            "undo": undo, "batch": None, "result_project": self.project}
        result_picker.clicked.connect(self._choose_bulk_result)
        for side in controls["bulk_filters"].values():
            for widget in side["attributes"]:
                widget.stateChanged.connect(self._schedule_bulk_fusion_plan)
            for widget in (side["name"], side["text"], side["cards"], *side["bounds"].values()):
                widget.textChanged.connect(self._schedule_bulk_fusion_plan)
            for widget in (side["types"], side["stars"]):
                widget.itemChanged.connect(self._schedule_bulk_fusion_plan)
            side["results_only"].stateChanged.connect(self._schedule_bulk_fusion_plan)
            for widget in (side["level_any"], side["level_exact_radio"], side["level_range_radio"]):
                widget.toggled.connect(self._schedule_bulk_fusion_plan)
            for widget in (side["level_exact"], side["level_min"], side["level_max"]):
                widget.valueChanged.connect(self._schedule_bulk_fusion_plan)
            self._set_layout_widgets_visible(side["advanced"], side["advanced_toggle"].isChecked())
            side["advanced_toggle"].toggled.connect(
                lambda visible, layout=side["advanced"]: self._set_layout_widgets_visible(layout, visible))
        ladder.textChanged.connect(self._schedule_bulk_fusion_plan)
        for widget in (choose_card, use_ladder, stronger, allow_self, overwrite):
            widget.toggled.connect(self._schedule_bulk_fusion_plan)
        apply.clicked.connect(lambda _checked=False: self._apply_bulk_fusions())
        undo.clicked.connect(self._undo_bulk_fusions)

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(300)
        timer.timeout.connect(self._refresh_bulk_fusion_plan)
        controls["bulk_timer"] = timer
        self._refresh_bulk_fusion_plan()

    @staticmethod
    def _populate_checkable_list(listing, names):
        listing.clear()
        for index, name in enumerate(names):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            listing.addItem(item)

    @staticmethod
    def _set_layout_widgets_visible(layout, visible):
        """Show/hide all widgets in an advanced-filter layout from Designer."""
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is not None:
                item.widget().setVisible(visible)
            elif item.layout() is not None:
                ModernEditor._set_layout_widgets_visible(item.layout(), visible)

    def _choose_bulk_result(self):
        controls = self.workspace_controls.get("Fusions")
        if not controls or "bulk" not in controls:
            return
        bulk = controls["bulk"]
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose fusion result")
        dialog.setMinimumSize(420, 460)
        dialog.resize(480, 560)
        layout = QVBoxLayout(dialog)
        search = QLineEdit(dialog)
        search.setPlaceholderText("Search monster cards by name or ID…")
        listing = QListWidget(dialog)
        listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        current_row = -1
        for cid in sorted(self.project.cards):
            card = self.project.cards[cid]
            if not card.is_monster():
                continue
            item = QListWidgetItem(f"{cid:03d}  {card.name}")
            item.setData(Qt.ItemDataRole.UserRole, cid)
            listing.addItem(item)
            if cid == bulk["result_id"]:
                current_row = listing.count() - 1
        if current_row >= 0:
            listing.setCurrentRow(current_row)

        def filter_results(text):
            query = text.strip().casefold()
            for row in range(listing.count()):
                item = listing.item(row)
                item.setHidden(query not in item.text().casefold())
            current = listing.currentItem()
            if current is None or current.isHidden():
                first = next((listing.item(row) for row in range(listing.count())
                              if not listing.item(row).isHidden()), None)
                listing.setCurrentItem(first) if first is not None else listing.setCurrentRow(-1)

        search.textChanged.connect(filter_results)
        search.returnPressed.connect(dialog.accept)
        layout.addWidget(search)
        layout.addWidget(listing, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel", dialog)
        choose = QPushButton("Choose", dialog)
        choose.setObjectName("primary")
        buttons.addWidget(cancel)
        buttons.addWidget(choose)
        layout.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)
        choose.clicked.connect(dialog.accept)
        listing.itemDoubleClicked.connect(lambda *_: dialog.accept())
        search.setFocus()
        if dialog.exec() == QDialog.DialogCode.Accepted and listing.currentItem() is not None:
            item = listing.currentItem()
            bulk["result_id"] = int(item.data(Qt.ItemDataRole.UserRole))
            bulk["result_button"].setText(item.text())
            bulk["choose_card"].setChecked(True)
            self._schedule_bulk_fusion_plan()

    @staticmethod
    def _checkable_list(names, parent, height=6):
        listing = QListWidget(parent)
        listing.setMaximumHeight(108)
        for index, name in enumerate(names):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            listing.addItem(item)
        return listing

    def _read_bulk_filter(self, controls):
        numbers = {}
        for key, edit in controls["bounds"].items():
            value = edit.text().strip()
            try:
                numbers[key] = int(value) if value else None
            except ValueError:
                raise ValueError(f"{controls['group'].title()}: {key.replace('_', ' ')} must be a whole number") from None
        for label, low, high in (("ATK", "atk_min", "atk_max"), ("DEF", "def_min", "def_max")):
            if numbers[low] is not None and numbers[high] is not None and numbers[low] > numbers[high]:
                raise ValueError(f"{controls['group'].title()}: {label} minimum exceeds maximum")
        if controls["level_exact_radio"].isChecked():
            numbers["level_min"] = numbers["level_max"] = controls["level_exact"].value()
        elif controls["level_range_radio"].isChecked():
            numbers["level_min"] = controls["level_min"].value()
            numbers["level_max"] = controls["level_max"].value()
            if numbers["level_min"] > numbers["level_max"]:
                raise ValueError(f"{controls['group'].title()}: Level minimum exceeds maximum")
        else:
            numbers["level_min"] = numbers["level_max"] = None
        card_filter = bulk_fusions.CardFilter(
            kinds={"monster"},
            types={item.data(Qt.ItemDataRole.UserRole) for item in self._checked_items(controls["types"])},
            attributes={i for i, widget in enumerate(controls["attributes"]) if widget.isChecked()},
            stars={item.data(Qt.ItemDataRole.UserRole) + 1 for item in self._checked_items(controls["stars"])},
            name=controls["name"].text(), text=controls["text"].text(), cards=controls["cards"].text(),
            results_only=controls["results_only"].isChecked(), **numbers)
        explicit = (bool(card_filter.types or card_filter.attributes or card_filter.stars) or
                    card_filter.level_min is not None or card_filter.level_max is not None or
                    card_filter.atk_min is not None or card_filter.atk_max is not None or
                    card_filter.def_min is not None or card_filter.def_max is not None or
                    bool(card_filter.name.strip() or card_filter.text.strip() or card_filter.cards.strip()) or
                    card_filter.results_only)
        if not explicit:
            raise ValueError(f"{controls['group'].title()}: choose at least one filter")
        return card_filter

    @staticmethod
    def _checked_items(listing):
        return [listing.item(i) for i in range(listing.count())
                if listing.item(i).checkState() == Qt.CheckState.Checked]

    def _copy_bulk_filter(self, source, destination):
        controls = self.workspace_controls["Fusions"]["bulk_filters"]
        src, dst = controls[source], controls[destination]
        for mine, theirs in zip(dst["attributes"], src["attributes"]):
            mine.setChecked(theirs.isChecked())
        for key in ("name", "text", "cards"):
            dst[key].setText(src[key].text())
        for key in src["bounds"]:
            dst["bounds"][key].setText(src["bounds"][key].text())
        dst["level_any"].setChecked(src["level_any"].isChecked())
        dst["level_exact_radio"].setChecked(src["level_exact_radio"].isChecked())
        dst["level_range_radio"].setChecked(src["level_range_radio"].isChecked())
        dst["level_exact"].setValue(src["level_exact"].value())
        dst["level_min"].setValue(src["level_min"].value())
        dst["level_max"].setValue(src["level_max"].value())
        dst["results_only"].setChecked(src["results_only"].isChecked())
        for key in ("types", "stars"):
            for i in range(src[key].count()):
                dst[key].item(i).setCheckState(src[key].item(i).checkState())

    def _schedule_bulk_fusion_plan(self, *_):
        controls = self.workspace_controls.get("Fusions")
        if controls and "bulk_timer" in controls:
            controls["bulk_timer"].start()

    def _refresh_bulk_fusion_plan(self):
        controls = self.workspace_controls.get("Fusions")
        if not controls or "bulk" not in controls:
            return
        bulk = controls["bulk"]
        if bulk["result_project"] is not self.project:
            bulk["result_id"] = 0
            bulk["result_button"].setText("Choose a result…")
            bulk["result_project"] = self.project
            bulk["batch"] = None
            bulk["undo"].setEnabled(False)
        try:
            a = self._read_bulk_filter(controls["bulk_filters"]["a"])
            b = self._read_bulk_filter(controls["bulk_filters"]["b"])
            ladder_mode = bulk["use_ladder"].isChecked()
            spec = bulk_fusions.BulkSpec(
                a=a, b=b, result=0 if ladder_mode else int(bulk["result_id"] or 0),
                ladder=bulk["ladder"].text() if ladder_mode else "",
                stronger=bulk["stronger"].isChecked(), allow_self=bulk["allow_self"].isChecked(),
                overwrite=bulk["overwrite"].isChecked())
            plan = bulk_fusions.plan(self.project, spec)
        except ValueError as problem:
            bulk["summary"].setText("Preview needs valid criteria")
            bulk["errors"].setText(str(problem))
            bulk["errors"].setVisible(True)
            bulk["warnings"].clear()
            bulk["warnings"].setVisible(False)
            bulk["preview"].setRowCount(0)
            # Keep Apply clickable so users get the specific validation reason
            # in a dialog instead of a button that appears unresponsive.
            bulk["apply"].setEnabled(True)
            return
        for key, spec_filter in (("a", a), ("b", b)):
            results = bulk_fusions.fusion_results(self.project) if (a.results_only or b.results_only) else None
            chosen, _unknown = spec_filter.select(self.project, results)
            controls["bulk_filters"][key]["count"].setText(f"{len(chosen):,} cards match")
        bulk["summary"].setText(
            f"A {plan.a_count} · B {plan.b_count} · {plan.pairs:,} pairs  |  "
            f"+{plan.added} new · {plan.replaced} replaced · {plan.kept} kept  |  "
            f"{plan.rules_after:,} mod rules")
        bulk["summary"].setToolTip(plan.summary() + "\n" + plan.budget_line())
        bulk["errors"].setText("\n".join(plan.errors))
        bulk["errors"].setVisible(bool(plan.errors))
        bulk["warnings"].setText("\n".join(plan.warnings))
        bulk["warnings"].setVisible(bool(plan.warnings))
        table = bulk["preview"]
        table.setRowCount(0)
        label = lambda cid: self.project.card_label(cid) if cid else ("(forbidden)" if cid == 0 else "(none)")
        for pair, before, after, action in plan.samples[:bulk_fusions.SAMPLE]:
            row = table.rowCount()
            table.insertRow(row)
            after_label = label(after)
            values = (self.project.card_label(pair[0]), self.project.card_label(pair[1]), label(before),
                      after_label, action)
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        bulk["apply"].setEnabled(True)
        bulk["apply"].setToolTip("Review the validation message before applying." if plan.errors
                                 else "Apply the previewed fusion changes to this mod.")

    def _apply_bulk_fusions(self):
        controls = self.workspace_controls.get("Fusions")
        if not controls:
            return
        self._refresh_bulk_fusion_plan()
        bulk = controls["bulk"]
        try:
            a = self._read_bulk_filter(controls["bulk_filters"]["a"])
            b = self._read_bulk_filter(controls["bulk_filters"]["b"])
            ladder_mode = bulk["use_ladder"].isChecked()
            plan = bulk_fusions.plan(self.project, bulk_fusions.BulkSpec(
                a=a, b=b, result=0 if ladder_mode else int(bulk["result_id"] or 0),
                ladder=bulk["ladder"].text() if ladder_mode else "",
                stronger=bulk["stronger"].isChecked(), allow_self=bulk["allow_self"].isChecked(),
                overwrite=bulk["overwrite"].isChecked()))
        except ValueError as problem:
            QMessageBox.warning(self, "Bulk fusions", str(problem))
            return
        if not plan.ok():
            QMessageBox.warning(self, "Bulk fusions", "\n".join(plan.errors) or "There are no fusion changes to apply.")
            return
        answer = QMessageBox.question(self, "Apply bulk fusions",
            plan.summary() + "\n\n" + plan.budget_line() +
            f"\n\nApply {plan.added} new fusion(s) and replace {plan.replaced} existing result(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        bulk["batch"] = bulk_fusions.apply(self.project, plan, "bulk add fusions")
        bulk["undo"].setEnabled(True)
        self._mark_dirty()
        self._refresh_fusions()
        self._refresh_bulk_fusion_plan()
        self.statusBar().showMessage(
            f"Applied {plan.added:,} new and {plan.replaced:,} replacement fusion rules. Save the mod to keep them.",
            10000)

    def _undo_bulk_fusions(self):
        controls = self.workspace_controls.get("Fusions")
        if not controls or "bulk" not in controls:
            return
        bulk = controls["bulk"]
        batch = bulk.get("batch")
        if batch is None or batch.project is not self.project:
            bulk["undo"].setEnabled(False)
            return
        restored, skipped = bulk_fusions.undo(self.project, batch)
        bulk["batch"] = None
        bulk["undo"].setEnabled(False)
        self._mark_dirty()
        self._refresh_fusions()
        self._refresh_bulk_fusion_plan()
        message = f"{restored} fusion rule(s) restored."
        if skipped:
            message += f" {skipped} rule(s) edited since the batch were left unchanged."
        self.statusBar().showMessage(message, 8000)


    def _selected_fusion_pairs(self):
        controls = self.workspace_controls["Fusions"]
        if controls["stack"].currentIndex() == 1:
            return [item.data(Qt.ItemDataRole.UserRole) for item in controls["image_list"].selectedItems()]
        table = controls["table"]
        return [table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                for row in sorted({i.row() for i in table.selectedItems()}) if table.item(row, 0)]

    def _edit_fusion(self, *_args, add=False):
        pairs = self._selected_fusion_pairs()
        pair = None if add else (pairs[0] if pairs else None)
        if not add and pair is None: return
        old_result = self.project.fusions.get(pair) or self.project.retail.fusions.get(pair) if pair else None
        dialog = QDialog(self); dialog.setWindowTitle("Add fusion" if add else "Edit fusion")
        form = QFormLayout(dialog)
        a = self._card_combo(dialog, pair[0] if pair else None)
        b = self._card_combo(dialog, pair[1] if pair else None)
        result = self._card_combo(dialog, old_result)
        form.addRow("Card A", a); form.addRow("Card B", b); form.addRow("Result", result)
        actions = QHBoxLayout(); ok = QPushButton("Apply"); cancel = QPushButton("Cancel")
        actions.addWidget(ok); actions.addWidget(cancel); form.addRow(actions)
        ok.clicked.connect(dialog.accept); cancel.clicked.connect(dialog.reject)
        if not dialog.exec(): return
        new_pair=(a.currentData(), b.currentData()); new_result=result.currentData()
        if not all(new_pair) or not new_result: return
        if pair and self.project.pair(*new_pair) != pair:
            self.project.set_fusion(pair[0],pair[1],None)
        self.project.set_fusion(*new_pair,new_result)
        self._mark_dirty(); self._refresh_fusions()

    def _remove_fusions(self):
        for a,b in self._selected_fusion_pairs(): self.project.set_fusion(a,b,None)
        self._mark_dirty(); self._refresh_fusions()

    def _revert_fusions(self):
        for pair in self._selected_fusion_pairs(): self.project.revert_fusion(pair)
        self._mark_dirty(); self._refresh_fusions()

    def _refresh_equips(self):
        c=self.workspace_controls.get("Equips")
        if not c:return
        self._loading_workspace=True
        equips=c["equips"]; equips.setRowCount(0)
        cards=sorted(set(self.project.equip_cards())|set(self.project.equips))
        for cid in cards:
            if cid not in self.project.cards:continue
            row=equips.rowCount(); equips.insertRow(row)
            for col,value in enumerate((f"{cid:03d}",self.project.cards[cid].name,
                                        len(self.project.equips.get(cid,set())))):
                item=QTableWidgetItem(str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,cid)
                equips.setItem(row,col,item)
        if getattr(self,"equip_current",None) is not None:
            for row in range(equips.rowCount()):
                if equips.item(row,0).data(Qt.ItemDataRole.UserRole)==self.equip_current:
                    equips.selectRow(row);break
        self._loading_workspace=False
        self._fill_equip_monsters()

    def _select_equip(self):
        if self._loading_workspace:
            return
        c=self.workspace_controls["Equips"]; row=c["equips"].currentRow()
        self.equip_current=c["equips"].item(row,0).data(Qt.ItemDataRole.UserRole) if row>=0 else None
        self._fill_equip_monsters()

    def _filter_equip_cards(self, text):
        c=self.workspace_controls.get("Equips")
        if not c:return
        table=c["equips"]; query=text.strip().casefold()
        current_row=table.currentRow()
        for row in range(table.rowCount()):
            name=table.item(row,1).text() if table.item(row,1) else ""
            table.setRowHidden(row,query not in name.casefold())
        if current_row>=0 and table.isRowHidden(current_row):
            table.clearSelection()
            self.equip_current=None
            self._fill_equip_monsters()

    def _filter_equip_monsters(self, text):
        c=self.workspace_controls.get("Equips")
        if not c:return
        table=c["monsters"]; query=text.strip().casefold()
        for row in range(table.rowCount()):
            name=table.item(row,2).text() if table.item(row,2) else ""
            table.setRowHidden(row,query not in name.casefold())

    def _fill_equip_monsters(self):
        c=self.workspace_controls.get("Equips")
        if not c:return
        table=c["monsters"]; table.blockSignals(True); table.setRowCount(0)
        cid=getattr(self,"equip_current",None)
        c["heading"].setText(f"{self.project.card_label(cid)} can equip:" if cid in self.project.cards else "Select an equip card")
        preview=c["preview"]
        if cid in self.project.cards and self.files is not None:
            try:
                pixmap=_card_image(self.project,self.files.wa,cid,self.frame_cache)
                preview.setPixmap(pixmap.scaled(preview.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.FastTransformation))
                preview.setText("")
            except (OSError,ValueError,IndexError):
                preview.setPixmap(QPixmap())
                preview.setText("Card preview unavailable")
        else:
            preview.setPixmap(QPixmap())
            preview.setText("Select an equip card")
        if cid in self.project.cards:
            now=self.project.equips.get(cid,set()); baseline=self.project.equip_baseline(cid)
            for monster in self.project.monsters():
                row=table.rowCount(); table.insertRow(row)
                check=QTableWidgetItem()
                check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked if monster in now else Qt.CheckState.Unchecked)
                check.setData(Qt.ItemDataRole.UserRole,monster); table.setItem(row,0,check)
                values=(f"{monster:03d}",self.project.cards[monster].name,TYPE_NAMES[self.project.cards[monster].type],
                        "Stock" if monster in baseline and monster in now else "Added" if monster in now else "Removed" if monster in baseline else "")
                for col,value in enumerate(values,1):table.setItem(row,col,QTableWidgetItem(str(value)))
        table.blockSignals(False)
        self._filter_equip_monsters(c["monster_search"].text())

    def _toggle_equip_monster(self,item):
        if self._loading_workspace or item.column()!=0:return
        equip=getattr(self,"equip_current",None)
        if equip not in self.project.cards:return
        monster=item.data(Qt.ItemDataRole.UserRole)
        allowed=self.project.equips.setdefault(equip,set())
        if item.checkState()==Qt.CheckState.Checked:allowed.add(monster)
        else:allowed.discard(monster)
        self._mark_dirty(); self._refresh_equips()

    def _choose_one_card(self,title,ids=None):
        dialog=QDialog(self);dialog.setWindowTitle(title);layout=QVBoxLayout(dialog)
        combo=self._card_combo(dialog,ids=ids);layout.addWidget(combo)
        buttons=QHBoxLayout();ok=QPushButton("Select");cancel=QPushButton("Cancel")
        buttons.addWidget(ok);buttons.addWidget(cancel);layout.addLayout(buttons)
        ok.clicked.connect(dialog.accept);cancel.clicked.connect(dialog.reject)
        return combo.currentData() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _add_equip_monster(self):
        equip=getattr(self,"equip_current",None)
        if equip not in self.project.cards:return
        cid=self._choose_one_card("Add monster",[i for i in self.project.monsters()])
        if cid:self.project.equips.setdefault(equip,set()).add(cid);self._mark_dirty();self._refresh_equips()

    def _equip_by_type(self,allow):
        equip=getattr(self,"equip_current",None)
        if equip not in self.project.cards:return
        typ=self.workspace_controls["Equips"]["type"].currentIndex()
        members={cid for cid,card in self.project.cards.items() if card.type==typ}
        now=self.project.equips.setdefault(equip,set())
        now.update(members) if allow else now.difference_update(members)
        self._mark_dirty();self._refresh_equips()

    def _remove_equip_monsters(self):
        equip=getattr(self,"equip_current",None)
        if equip not in self.project.cards:return
        for row in sorted({i.row() for i in self.workspace_controls['Equips']['monsters'].selectedItems()}):
            item=self.workspace_controls['Equips']['monsters'].item(row,0)
            if item:self.project.equips.setdefault(equip,set()).discard(item.data(Qt.ItemDataRole.UserRole))
        self._mark_dirty();self._refresh_equips()

    def _revert_equip(self):
        equip=getattr(self,"equip_current",None)
        if equip in self.project.cards:self.project.equips[equip]=self.project.equip_baseline(equip);self._mark_dirty();self._refresh_equips()

    def _refresh_rituals(self):
        c=self.workspace_controls["Rituals"]; cards=c["cards"]
        previous=getattr(self,"ritual_current",None)
        self._loading_workspace=True
        cards.setRowCount(0)
        rituals=sorted(set(self.project.ritual_cards())|set(self.project.rituals)|set(self.project.retail.rituals))
        for ritual in rituals:
            if ritual not in self.project.cards:continue
            row=cards.rowCount();cards.insertRow(row)
            id_item=QTableWidgetItem(f"{ritual:03d}")
            id_item.setData(Qt.ItemDataRole.UserRole,ritual)
            cards.setItem(row,0,id_item)
            cards.setItem(row,1,QTableWidgetItem(self.project.cards[ritual].name))
            now=self.project.rituals.get(ritual);retail=self.project.retail.rituals.get(ritual)
            state="Stock" if now==retail else "Added" if retail is None else "Removed" if now is None else "Changed"
            cards.setItem(row,2,QTableWidgetItem(state))
            if ritual==previous:
                cards.selectRow(row)
        if cards.currentRow()<0 and cards.rowCount():
            cards.selectRow(0)
        self.ritual_current=self._selected_ritual()
        self._loading_workspace=False
        self._filter_ritual_cards(c["search"].text())
        self._refresh_ritual_detail()

    def _select_ritual(self):
        if self._loading_workspace:return
        self.ritual_current=self._selected_ritual()
        self._refresh_ritual_detail()

    def _filter_ritual_cards(self,text):
        c=self.workspace_controls.get("Rituals")
        if not c:return
        cards=c["cards"];query=text.strip().casefold()
        for row in range(cards.rowCount()):
            name=cards.item(row,1).text() if cards.item(row,1) else ""
            cards.setRowHidden(row,query not in name.casefold())
        row=cards.currentRow()
        if row>=0 and cards.isRowHidden(row):
            cards.clearSelection();self.ritual_current=None;self._refresh_ritual_detail()

    def _refresh_ritual_detail(self):
        c=self.workspace_controls["Rituals"]; ritual=getattr(self,"ritual_current",None)
        for image,fields in zip(c["tribute_images"],c["tribute_fields"]):
            image.setPixmap(QPixmap());image.setText("—")
            self._set_ritual_fields(fields,None)
        c["summon_image"].setPixmap(QPixmap());c["summon_image"].setText("—")
        self._set_ritual_fields(c["summon_fields"],None)
        if ritual not in self.project.cards:
            c["heading"].setText("Select a ritual card")
            c["preview"].setPixmap(QPixmap());c["preview"].setText("Select a ritual card")
            self._set_ritual_fields(c["card_meta"],None)
            for fields in c["tribute_fields"]+[c["summon_fields"]]:self._set_ritual_fields(fields,None)
            c["state"].setText("State: —")
            return
        c["heading"].setText(f"Ritual Recipe (Tributes → Result) · {self.project.card_label(ritual)}")
        self._set_ritual_fields(c["card_meta"],ritual)
        if self.files is not None:
            try:
                image=_card_image(self.project,self.files.wa,ritual,self.frame_cache)
                c["preview"].setPixmap(image.scaled(c["preview"].size(),Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.FastTransformation))
                c["preview"].setText("")
            except (OSError,ValueError,IndexError):
                c["preview"].setPixmap(QPixmap());c["preview"].setText("Card preview unavailable")
        now=self.project.rituals.get(ritual);retail=self.project.retail.rituals.get(ritual)
        state="" if now==retail else "Added" if retail is None else "Removed" if now is None else "Changed"
        recipe=self.ritual_pending.get(ritual,now or (None,None,None,None))
        for combo,cid in zip(c["tribute_combos"]+[c["summon_combo"]],recipe):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0,combo.findData(cid)))
            combo.blockSignals(False)
        for index,cid in enumerate(recipe[:3]):
            if not cid:continue
            self._set_ritual_fields(c["tribute_fields"][index],cid)
            if self.files is not None:
                try:
                    image=_card_image(self.project,self.files.wa,cid,self.frame_cache)
                    c["tribute_images"][index].setPixmap(image.scaled(
                        c["tribute_images"][index].size(),Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation))
                    c["tribute_images"][index].setText("")
                except (OSError,ValueError,IndexError):
                    c["tribute_images"][index].setText("Preview unavailable")
        summoned=recipe[3]
        if summoned:
            self._set_ritual_fields(c["summon_fields"],summoned)
            if self.files is not None:
                try:
                    image=_card_image(self.project,self.files.wa,summoned,self.frame_cache)
                    c["summon_image"].setPixmap(image.scaled(
                        c["summon_image"].size(),Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation))
                    c["summon_image"].setText("")
                except (OSError,ValueError,IndexError):
                    c["summon_image"].setText("Preview unavailable")
        pending=self.ritual_pending.get(ritual)
        pending_changed=pending is not None and pending!=now
        c["state"].setText("State: Pending" if pending_changed else f"State: {state or 'Stock'}")

    def _stage_ritual_selector_recipe(self, *_):
        ritual=getattr(self,"ritual_current",None)
        if ritual not in self.project.cards:return
        c=self.workspace_controls["Rituals"]
        values=tuple(combo.currentData() for combo in c["tribute_combos"]+[c["summon_combo"]])
        self.ritual_pending[ritual]=values
        self._refresh_ritual_detail()

    def _apply_ritual_selector_recipe(self, *_):
        ritual=getattr(self,"ritual_current",None)
        if ritual not in self.project.cards:return
        values=self.ritual_pending.get(ritual)
        if values is None:return
        if not all(values):
            self.statusBar().showMessage("Choose all three materials and a summoned card before applying the recipe",5000)
            return
        current=self.project.rituals.get(ritual)
        if current!=values:
            self.project.rituals[ritual]=values
            self._mark_dirty()
        self.ritual_pending.pop(ritual,None)
        self._refresh_rituals()

    def _set_ritual_fields(self,fields,cid):
        card=self.project.cards.get(cid) if cid is not None else None
        if fields.get("id") is not None:fields["id"].setText(f"{cid:03d}" if card is not None else "")

        for key,choices,value in (("type",TYPE_NAMES,card.type if card else -1),
                                  ("attribute",ATTRIBUTE_NAMES,card.attribute if card else -1)):
            box=fields.get(key)
            if box is not None:
                if value>=0 and value<len(choices):box.setCurrentIndex(value)
                else:box.setCurrentIndex(-1)
        for key,value in (("level",card.level if card else 0),("atk",card.attack if card else 0),
                          ("def",card.defense if card else 0)):
            if fields.get(key) is not None:fields[key].setValue(value)

    def _ritual_card_summary(self,cid):
        card=self.project.cards.get(cid)
        if card is None:return "Card data unavailable"
        card_type=TYPE_NAMES[card.type] if 0<=card.type<len(TYPE_NAMES) else "Unknown type"
        lines=[f"ID {cid:03d}  ·  {card_type}"]
        if card.is_monster():
            attribute=ATTRIBUTE_NAMES[card.attribute] if 0<=card.attribute<len(ATTRIBUTE_NAMES) else "Unknown"
            star1=STAR_NAMES[card.star1] if 0<=card.star1<len(STAR_NAMES) else "Unknown"
            star2=STAR_NAMES[card.star2] if 0<=card.star2<len(STAR_NAMES) else "Unknown"
            lines.extend((f"{attribute}  ·  Level {card.level}",
                          f"ATK {card.attack}  ·  DEF {card.defense}",
                          f"Stars: {star1} / {star2}"))
        return "\n".join(lines)

    def _selected_ritual(self):
        table=self.workspace_controls["Rituals"]["cards"];row=table.currentRow()
        if row<0 or table.isRowHidden(row):return None
        item=table.item(row,0) if row>=0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _edit_ritual(self,*_):
        ritual=self._selected_ritual()
        if ritual is None:return
        recipe=self.project.rituals.get(ritual) or self.project.retail.rituals.get(ritual) or (0,0,0,0)
        dialog=QDialog(self);dialog.setWindowTitle(f"Ritual recipe · {self.project.card_label(ritual)}")
        form=QFormLayout(dialog);combos=[]
        for label,cid in zip(("Tribute 1","Tribute 2","Tribute 3","Summons"),recipe):
            combo=self._card_combo(dialog,cid or None,ids=self.project.monsters())
            form.addRow(label,combo);combos.append(combo)
        buttons=QHBoxLayout();ok=QPushButton("Apply recipe");cancel=QPushButton("Cancel")
        buttons.addWidget(ok);buttons.addWidget(cancel);form.addRow(buttons)
        ok.clicked.connect(dialog.accept);cancel.clicked.connect(dialog.reject)
        if not dialog.exec():return
        values=tuple(combo.currentData() for combo in combos)
        if not all(values):return
        self.project.rituals[ritual]=values;self._mark_dirty();self._refresh_rituals()

    def _remove_ritual(self):
        ritual=self._selected_ritual()
        if ritual is not None:
            self.ritual_pending.pop(ritual,None)
            self.project.rituals.pop(ritual,None)
            self._mark_dirty();self._refresh_rituals()

    def _revert_ritual(self):
        ritual=self._selected_ritual()
        if ritual is None:return
        self.ritual_pending.pop(ritual,None)
        if ritual in self.project.retail.rituals:self.project.rituals[ritual]=self.project.retail.rituals[ritual]
        else:self.project.rituals.pop(ritual,None)
        self._mark_dirty();self._refresh_rituals()

    def _duelist_roster_source(self):
        """Read inline, file-backed, or folder duelist definitions without losing their source form."""
        cached=getattr(self,"_duelist_entries_cache",None)
        if cached is not None and getattr(self,"_duelist_entries_cache_project",None) is self.project:
            return cached
        raw=self.project.other.get("duelists")
        entries=[];sources={};mode="inline";path=None
        if isinstance(raw,list):
            entries=[dict(e) for e in raw if isinstance(e,dict)]
            mode="inline"
        elif isinstance(raw,str):
            path=raw;mode="file"
            source=Path(self.project.source_dir or "") / raw
            try:
                blob=self.project.files.get(raw)
                loaded=json.loads(blob.decode("utf-8-sig") if blob is not None else source.read_text(encoding="utf-8-sig"))
                if isinstance(loaded,list):entries=[dict(e) for e in loaded if isinstance(e,dict)]
            except (OSError,ValueError):
                pass
        else:
            # New projects use the framework's one-duelist-per-file format,
            # even before the `duelists/` directory exists on disk.
            mode="folder"
            folder=Path(self.project.source_dir or "") / "duelists"
            files={str(file.relative_to(self.project.source_dir)):file for file in folder.glob("*.json")} if folder.is_dir() else {}
            for relative,blob in self.project.files.items():
                if relative.startswith("duelists/") and relative.endswith(".json"):
                    files.setdefault(relative,folder/Path(relative).name)
            for relative,file in sorted(files.items()):
                try:
                    blob=self.project.files.get(relative)
                    loaded=json.loads(blob.decode("utf-8-sig") if blob is not None else file.read_text(encoding="utf-8-sig"))
                    entry=loaded
                    if isinstance(entry,dict):
                        # In the folder format, the filename is the ID; an
                        # `id` property in the JSON is ignored by the game.
                        entry["id"]=file.stem;entries.append(entry);sources[file.stem]=relative
                except (OSError,ValueError):
                    continue
        result=(entries,mode,path,sources)
        self._duelist_entries_cache=result;self._duelist_entries_cache_project=self.project
        return result

    @staticmethod
    def _duelist_slug(text):
        import re
        slug=re.sub(r"[^a-z0-9]+","-",str(text).lower()).strip("-")
        return slug or "new-duelist"

    def _duelist_layout(self):
        entries,mode,path,sources=self._duelist_roster_source()
        # Slot 000 is Deck Build, not an opponent: preserve the empty grid
        # position but never expose it as an editable duelist.
        slots={i:{"slot":i,"name":DUELIST_NAMES[i],"base":i,"kind":"stock","entry":None}
               for i in range(1,min(40,len(DUELIST_NAMES)))}
        # Replacements occupy their retail positions and do not take an added slot.
        for entry in entries:
            if "replace" not in entry:continue
            from .model import duelist_named
            d=duelist_named(entry.get("replace"))
            if 0<d<40:
                slots[d]={"slot":d,"name":str(entry.get("name") or DUELIST_NAMES[d]),"base":d,
                          "kind":"replacement","entry":entry}
        # Reserve all explicit positions first, matching the framework's placement pass.
        added=[]
        for entry in entries:
            if "replace" in entry:continue
            slot=entry.get("slot")
            if isinstance(slot,int) and not isinstance(slot,bool) and 40<=slot<128 and slot not in slots:
                slots[slot]={"slot":slot,"name":str(entry.get("name") or entry.get("id") or "Duelist"),
                             "base":self._duelist_base_index(entry.get("copy")),"kind":"added","entry":entry}
            else:added.append(entry)
        for entry in added:
            free=next((slot for slot in range(40,128) if slot not in slots),None)
            if free is None:break
            slots[free]={"slot":free,"name":str(entry.get("name") or entry.get("id") or "Duelist"),
                         "base":self._duelist_base_index(entry.get("copy")),"kind":"added","entry":entry}
        self._duelist_entries_cache=(entries,mode,path,sources);self._duelist_entries_cache_project=self.project
        return slots

    @staticmethod
    def _duelist_base_index(value):
        from .model import duelist_named
        if value is None:return 1
        if isinstance(value,int) and 1<=value<len(DUELIST_NAMES):return value
        found=duelist_named(value)
        return found if found>0 else 1

    def _duelist_portrait_pixmap(self, record):
        entry=record.get("entry") or {}
        portrait=entry.get("portrait")
        if portrait:
            blob=self.project.files.get(portrait)
            if blob is None and self.project.source_dir:
                try:blob=(Path(self.project.source_dir)/portrait).read_bytes()
                except OSError:blob=None
            if blob:
                pix=QPixmap()
                if pix.loadFromData(blob):return pix
        base=int(record.get("base",1))
        if not 0<=base<40:return QPixmap()
        # Free Duel portraits can also be replaced by texture-pack entries
        # targeting their WA_MRG.MRG records.
        try:
            texture_state=art.state(self.project)
            pack_entries=texture_state.entries
            if pack_entries is None:
                manifest_path=f"{art.pack_dir(self.project)}/manifest.json"
                manifest_blob=self.project.files.get(manifest_path)
                if manifest_blob:
                    pack_entries=json.loads(manifest_blob.decode("utf-8-sig"))
            portrait_offset=0xF55000+base*0x980
            for texture in pack_entries or ():
                if (not isinstance(texture,dict) or
                        str(texture.get("archive","")).upper()!="WA_MRG.MRG" or
                        not art.contained(texture.get("file"))):
                    continue
                try:offset=int(str(texture.get("offset","-1")),0)
                except ValueError:continue
                if offset!=portrait_offset:continue
                relative=f"{art.pack_dir(self.project)}/{texture['file']}"
                blob=self.project.files.get(relative)
                if blob is None:
                    folder=texture_state.folder or self.project.source_dir
                    if folder is not None:
                        blob=(Path(folder)/relative).read_bytes()
                if blob:
                    pix=QPixmap()
                    if pix.loadFromData(blob):return pix
                break
        except (OSError,ValueError,TypeError,json.JSONDecodeError):
            pass
        try:
            wa=self.files.wa;offset=0xF55000+base*0x980
            palette=image_extract.read_palette(wa,offset+0x900,64)
            palette.extend([0]*(256-len(palette)))
            width,height,rgba=image_extract.decode(wa,offset,24,48,8,palette)
            return QPixmap.fromImage(_qimage(width,height,rgba))
        except (IndexError,ValueError,struct.error):
            return QPixmap()

    def _refresh_duelists(self,*_):
        c=self.workspace_controls["Duelists"];grid=c["duelists"]
        self.duelist_slots=self._duelist_layout()
        if not hasattr(self,"duelist_selected_slot"):self.duelist_selected_slot=1
        page=c["page"].currentIndex();query=c["search"].text().strip().casefold()
        grid.clearContents();grid.setRowCount(5);grid.setColumnCount(8)
        for cell in range(40):
            slot=page*40+cell;row,col=divmod(cell,8);record=self.duelist_slots.get(slot)
            item=QTableWidgetItem("");item.setData(Qt.ItemDataRole.UserRole,slot)
            if slot==0:item.setFlags(Qt.ItemFlag.NoItemFlags)
            grid.setItem(row,col,item)
            if record is None:
                continue
            if query and query not in record["name"].casefold() and query not in str(slot) and query not in f"{slot:03d}":
                continue
            tile=QWidget();tile.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            tile_layout=QVBoxLayout(tile);tile_layout.setContentsMargins(2,2,2,2);tile_layout.setSpacing(1)
            portrait=QLabel();portrait.setFixedSize(54,54);portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pix=self._duelist_portrait_pixmap(record)
            if not pix.isNull():portrait.setPixmap(pix.scaled(portrait.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
            else:portrait.setText("—")
            label=QLabel(f"{slot:03d} · {record['name']}");label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setWordWrap(True)
            label.setToolTip(record["name"])
            tile_layout.addWidget(portrait,0,Qt.AlignmentFlag.AlignHCenter);tile_layout.addWidget(label)
            grid.setCellWidget(row,col,tile)
        current=getattr(self,"duelist_selected_slot",1)
        cell=current-page*40
        if not 0<=cell<40 or current==0:
            cell=1 if page==0 else 0
            self.duelist_selected_slot=page*40+cell
        grid.setCurrentCell(cell//8,cell%8)
        self._select_duelist(grid.currentRow(),grid.currentColumn(),refresh_grid=False)

    def _selected_duelist(self):
        slot=getattr(self,"duelist_selected_slot",0)
        record=getattr(self,"duelist_slots",{}).get(slot)
        return (record or {}).get("base",1)

    def _select_duelist(self,row=None,column=None,refresh_grid=True):
        c=self.workspace_controls["Duelists"]
        if row is None or row<0:row=c["duelists"].currentRow()
        if column is None or column<0:column=c["duelists"].currentColumn()
        if row<0 or column<0:return
        slot=c["page"].currentIndex()*40+row*8+column
        if slot==0:return
        if slot != getattr(self,"duelist_selected_slot",None):
            self._duelist_portrait_pending=None
        self.duelist_selected_slot=slot
        self.duelist_current=self._selected_duelist()
        record=self.duelist_slots.get(slot)
        c["remove"].setEnabled(bool(record and record["kind"]=="added"))
        c["base"].setEnabled(record is None or record["kind"]=="added")
        if record:
            c["name"].setText(record["name"])
            entry=record.get("entry") or {}
            c["id"].setText(str(entry.get("id") or ""))
            c["id"].setReadOnly(record["kind"] in ("added","replacement"))
            base_index=max(1,int(record.get("base",1)))
            c["base"].setCurrentIndex(max(0,c["base"].findData(base_index)))
            wanted=entry.get("slot") if record["kind"]=="added" else None
            c["position"].setCurrentIndex(max(0,c["position"].findData(wanted)))
            pix=self._duelist_portrait_pixmap(record)
            c["portrait"].setPixmap(pix.scaled(c["portrait"].size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) if not pix.isNull() else QPixmap())
            c["portrait"].setText("" if not pix.isNull() else "Portrait")
        else:
            c["name"].clear();c["id"].clear();c["id"].setReadOnly(False)
            c["portrait"].setPixmap(QPixmap());c["portrait"].setText("Portrait")
            c["base"].setCurrentIndex(0);c["position"].setCurrentIndex(max(0,c["position"].findData(slot if slot>=40 else None)))
        self._refresh_duelist_pool()

    def _choose_duelist_portrait(self):
        path,_=QFileDialog.getOpenFileName(self,"Choose duelist portrait","","PNG images (*.png)")
        if not path:return
        image=QImage(path)
        if image.isNull():
            QMessageBox.warning(self,"Invalid portrait","Choose a readable PNG image.");return
        self._duelist_portrait_pending=Path(path).read_bytes()
        pix=QPixmap.fromImage(image)
        label=self.workspace_controls["Duelists"]["portrait"]
        label.setPixmap(pix.scaled(label.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));label.setText("")

    def _store_duelist_entries(self,entries):
        _,mode,path,sources=getattr(self,"_duelist_entries_cache",( [],"inline",None,{}))
        if mode=="inline":
            self.project.other["duelists"]=entries
        elif mode=="file":
            self.project.files[path]=json.dumps(entries,ensure_ascii=False,indent=4).encode("utf-8")+b"\n"
        else:
            for entry in entries:
                duel_id=str(entry.get("id") or "")
                relative=sources.get(duel_id,f"duelists/{duel_id}.json")
                body=dict(entry)
                # The folder format derives IDs from the filename and expects
                # only duelist properties (copy/name/slot/portrait) in JSON.
                body.pop("id",None)
                self.project.files[relative]=json.dumps(body,ensure_ascii=False,indent=4).encode("utf-8")+b"\n"

    def _save_duelist(self,adding=False):
        c=self.workspace_controls["Duelists"]
        name=c["name"].text().strip()
        if not name:
            QMessageBox.warning(self,"Duelist name required","Enter a name for this duelist.");return
        entries,mode,path,sources=self._duelist_roster_source();self._duelist_entries_cache=(entries,mode,path,sources)
        slot=getattr(self,"duelist_selected_slot",None);record=self.duelist_slots.get(slot) if slot is not None else None
        raw_id=c["id"].text().strip() or self._duelist_slug(name)
        duelist_id=self._duelist_slug(raw_id)
        existing=next((e for e in entries if str(e.get("id","")).casefold()==duelist_id.casefold()),None)
        if adding:
            if existing:
                QMessageBox.warning(self,"ID already used",f"The ID {duelist_id!r} is already in use.");return
            base=c["base"].currentData()
            if base is None:
                QMessageBox.warning(self,"Choose a base","Choose a stock duelist to copy.");return
            chosen_slot=c["position"].currentData()
            if chosen_slot is not None:
                if chosen_slot in self.duelist_slots:
                    QMessageBox.warning(self,"Position occupied",f"Grid position {chosen_slot} is occupied. Choose another position or Automatic.");return
            entry={"id":duelist_id,"copy":int(base),"name":name}
            if chosen_slot is not None:entry["slot"]=int(chosen_slot)
            entries.append(entry)
            target_id=duelist_id
            slot=chosen_slot
        else:
            if record is None:
                QMessageBox.warning(self,"Choose a duelist","Select a duelist to edit, or use Add duelist for an empty position.");return
            if record["kind"] in ("added","replacement"):
                entry=record["entry"]
                old_id=str(entry.get("id") or "")
                if duelist_id!=old_id and existing:
                    QMessageBox.warning(self,"ID already used",f"The ID {duelist_id!r} is already in use.");return
                entry["id"]=duelist_id;entry["name"]=name
                if record["kind"]=="added":
                    base=c["base"].currentData()
                    if base is None:
                        QMessageBox.warning(self,"Choose a base","Choose a stock duelist to copy.");return
                    entry["copy"]=int(base)
                    chosen_slot=c["position"].currentData()
                    if chosen_slot is not None and chosen_slot in self.duelist_slots and chosen_slot!=slot:
                        QMessageBox.warning(self,"Position occupied",f"Grid position {chosen_slot} is occupied.");return
                    if chosen_slot is None:entry.pop("slot",None)
                    else:entry["slot"]=int(chosen_slot)
                target_id=duelist_id
            else:
                if slot == 0 and record["kind"] == "stock":
                    QMessageBox.warning(self,"Reserved position","Position 000 is reserved for Deck Build and cannot be replaced.");return
                if any(e.get("replace")==DUELIST_NAMES[slot] for e in entries):
                    entry=next(e for e in entries if e.get("replace")==DUELIST_NAMES[slot])
                    entry["name"]=name;entry["id"]=duelist_id
                else:
                    entry={"id":duelist_id,"replace":DUELIST_NAMES[slot],"name":name};entries.append(entry)
                target_id=duelist_id
        portrait=getattr(self,"_duelist_portrait_pending",None)
        if portrait:
            rel=f"portraits/{target_id}.png";self.project.files[rel]=portrait
            entry["portrait"]=rel
            self._duelist_portrait_pending=None
        if mode=="folder" and entry.get("id") and entry.get("id") not in sources:
            sources[entry["id"]]=f"duelists/{entry['id']}.json"
        self._duelist_entries_cache=(entries,mode,path,sources);self._duelist_entries_cache_project=self.project
        self._store_duelist_entries(entries)
        self._mark_dirty()
        self.duelist_slots=self._duelist_layout()
        slot=next((s for s,r in self.duelist_slots.items()
                   if (r.get("entry") or {}).get("id")==target_id),slot)
        if slot is not None:
            self.duelist_selected_slot=slot
            if c["search"].text() and c["search"].text().casefold() not in name.casefold():
                c["search"].clear()
            c["page"].setCurrentIndex(slot//40)
        self._refresh_duelists()
        self.statusBar().showMessage(f"Applied edits to {name}. Use Save to write them to the mod.",8000)

    def _remove_duelist(self):
        c=self.workspace_controls["Duelists"]
        slot=getattr(self,"duelist_selected_slot",None)
        record=self.duelist_slots.get(slot) if slot is not None else None
        if not record or record.get("kind")!="added":
            QMessageBox.information(self,"Remove duelist","Select a custom-added duelist to remove. Retail duelists and replacements cannot be removed.")
            return
        name=record["name"]
        answer=QMessageBox.question(self,"Remove duelist",f"Remove {name} from the roster? Its duelists, deck, drop, and portrait files will be omitted when you save the mod.")
        if answer!=QMessageBox.StandardButton.Yes:return
        entries,mode,path,sources=self._duelist_roster_source()
        entry=record["entry"];duelist_id=str(entry.get("id") or "")
        entries=[item for item in entries if item is not entry]
        if mode=="folder":
            roster_path=sources.pop(duelist_id,f"duelists/{duelist_id}.json")
            self.project.removed_files.add(roster_path)
            for related in (f"decks/{duelist_id}.json",f"drops/{duelist_id}.json"):
                self.project.removed_files.add(related)
            portrait=entry.get("portrait") or f"portraits/{duelist_id}.png"
            still_used=any((other.get("portrait") or f"portraits/{other.get('id','')}.png")==portrait for other in entries)
            if not still_used:self.project.removed_files.add(portrait)
            for relative in (roster_path,f"decks/{duelist_id}.json",f"drops/{duelist_id}.json",portrait):
                self.project.files.pop(relative,None)
        self._duelist_entries_cache=(entries,mode,path,sources)
        self._duelist_entries_cache_project=self.project
        self._store_duelist_entries(entries)
        self._duelist_portrait_pending=None
        self._mark_dirty()
        self._refresh_duelists()

    def _selected_pool_name(self):
        return POOLS[self.workspace_controls["Duelists"]["pool"].currentIndex()]

    def _refresh_duelist_pool(self,*_):
        if "Duelists" not in self.workspace_controls:return
        c=self.workspace_controls["Duelists"];d=self._selected_duelist();name=self._selected_pool_name()
        record=getattr(self,"duelist_slots",{}).get(getattr(self,"duelist_selected_slot",d))
        is_added=bool(record and record.get("kind")=="added")
        pool=self.project.pools[d][name];retail=self.project.retail.pools[d][name]
        title=record["name"] if record else DUELIST_NAMES[d]
        c["summary"].setText(f"{title} · {POOL_LABELS[name]} · {sum(pool.values())}/{POOL_TOTAL} weight" + (" · inherited from base" if is_added else ""))
        for button_name in ("addPoolCardButton","setPoolWeightButton","removePoolCardButton","normalizePoolButton","revertPoolButton"):
            button=c["page"].findChild(QPushButton,button_name)
            if button:button.setEnabled(not is_added)
        rows=[]
        for cid in sorted(set(pool)|set(retail),key=lambda i:(-pool.get(i,0),i)):
            weight,before=pool.get(cid,0),retail.get(cid,0)
            if not weight and not before:continue
            card=self.project.cards.get(cid)
            state="" if weight==before else "Added" if not before else "Removed" if not weight else "Changed"
            rows.append((cid,card.name if card else "?",TYPE_NAMES[card.type] if card else "",weight,
                         f"{weight*100/POOL_TOTAL:.2f}%",before,state))
        table=c["table"];table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for col,value in enumerate(row):
                item=QTableWidgetItem(str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,row[0])
                table.setItem(i,col,item)

    def _select_pool_card(self):
        c=self.workspace_controls["Duelists"];row=c["table"].currentRow()
        if row>=0:c["weight"].setValue(int(c["table"].item(row,3).text()))

    def _add_pool_card(self):
        cid=self._choose_one_card("Add card to pool")
        if cid:
            d=self._selected_duelist();pool=self.project.pools[d][self._selected_pool_name()]
            pool[cid]=max(1,self.workspace_controls["Duelists"]["weight"].value())
            self._mark_dirty();self._refresh_duelists()

    def _selected_pool_cards(self):
        table=self.workspace_controls["Duelists"]["table"]
        return [table.item(row,0).data(Qt.ItemDataRole.UserRole)
                for row in sorted({x.row() for x in table.selectedItems()}) if table.item(row,0)]

    def _set_pool_weight(self):
        pool=self.project.pools[self._selected_duelist()][self._selected_pool_name()]
        weight=self.workspace_controls["Duelists"]["weight"].value()
        for cid in self._selected_pool_cards():
            if weight:pool[cid]=weight
            else:pool.pop(cid,None)
        self._mark_dirty();self._refresh_duelist_pool()

    def _remove_pool_cards(self):
        pool=self.project.pools[self._selected_duelist()][self._selected_pool_name()]
        for cid in self._selected_pool_cards():pool.pop(cid,None)
        self._mark_dirty();self._refresh_duelist_pool()

    def _normalize_pool(self):
        d=self._selected_duelist();pool=self._selected_pool_name()
        self.project.pools[d][pool]=poolmath.normalize(self.project.pools[d][pool])
        self._mark_dirty();self._refresh_duelist_pool()

    def _revert_pool(self):
        d=self._selected_duelist();pool=self._selected_pool_name()
        self.project.pools[d][pool]=dict(self.project.retail.pools[d][pool])
        self._mark_dirty();self._refresh_duelists()

    def _current_starter(self):
        index=getattr(self,"starter_current",None)
        return self.project.starter[index] if index is not None and 0<=index<len(self.project.starter) else None

    def _refresh_starter_decks(self):
        c=self.workspace_controls["Starter decks"];table=c["decks"]
        table.blockSignals(True);table.setRowCount(0)
        for index,deck in enumerate(self.project.starter):
            row=table.rowCount();table.insertRow(row)
            values=(index+1,deck.name or "(unnamed)",deck.weight,f"{deck.total()}/{DECK_SIZE}")
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,index)
                table.setItem(row,col,item)
        if self.project.starter:
            self.starter_current=min(getattr(self,"starter_current",0),len(self.project.starter)-1)
            table.selectRow(self.starter_current)
        else:self.starter_current=None
        table.blockSignals(False);self._fill_starter_cards()

    def _select_starter_deck(self):
        table=self.workspace_controls["Starter decks"]["decks"];row=table.currentRow()
        if row>=0:
            self.starter_current=table.item(row,0).data(Qt.ItemDataRole.UserRole)
            self._fill_starter_cards()

    def _fill_starter_cards(self):
        c=self.workspace_controls["Starter decks"];deck=self._current_starter();table=c["cards"]
        table.setRowCount(0)
        c["name"].setText(deck.name if deck else "")
        c["weight"].setValue(deck.weight if deck else 0)
        if not deck:return
        rows=[]
        for cid,copies in sorted(deck.cards.items()):
            card=self.project.cards.get(cid)
            warnings=[]
            if copies>DECK_COPY_LIMIT:warnings.append(f"Over {DECK_COPY_LIMIT} copies")
            if exodia_piece(cid) and copies>1:warnings.append("Exodia piece")
            rows.append((cid,card.name if card else "?",TYPE_NAMES[card.type] if card else "",copies,", ".join(warnings)))
        for label,copies in deck.kept.items():rows.append(("",label,"",copies,"Kept as written"))
        table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for col,value in enumerate(row):
                item=QTableWidgetItem(str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,row[0])
                table.setItem(i,col,item)

    def _select_starter_card(self):
        c=self.workspace_controls["Starter decks"];row=c["cards"].currentRow()
        if row>=0 and c["cards"].item(row,0).data(Qt.ItemDataRole.UserRole):
            c["copies"].setValue(int(c["cards"].item(row,3).text()))

    def _add_starter_deck(self):
        self.project.starter.append(StarterDeck(name=f"Deck {len(self.project.starter)+1}"))
        self.starter_current=len(self.project.starter)-1;self._mark_dirty();self._refresh_starter_decks()

    def _remove_starter_deck(self):
        deck=self._current_starter()
        if deck is None:return
        if QMessageBox.question(self,"Remove starter deck",f"Remove {deck.name or 'this deck'}?")!=QMessageBox.StandardButton.Yes:return
        self.project.starter.pop(self.starter_current)
        self.starter_current=max(0,self.starter_current-1) if self.project.starter else None
        self._mark_dirty();self._refresh_starter_decks()

    def _apply_starter_details(self):
        deck=self._current_starter()
        if deck is None:return
        deck.name=self.workspace_controls["Starter decks"]["name"].text().strip()
        deck.weight=self.workspace_controls["Starter decks"]["weight"].value()
        self._mark_dirty();self._refresh_starter_decks()

    def _add_starter_card(self):
        deck=self._current_starter()
        if deck is None:return
        cid=self._choose_one_card("Add card to starter deck")
        if cid:
            deck.cards[cid]=max(1,self.workspace_controls["Starter decks"]["copies"].value())
            self._mark_dirty();self._fill_starter_cards();self._refresh_starter_decks()

    def _set_starter_copies(self):
        deck=self._current_starter()
        if deck is None:return
        copies=self.workspace_controls["Starter decks"]["copies"].value()
        table=self.workspace_controls["Starter decks"]["cards"]
        for row in sorted({x.row() for x in table.selectedItems()}):
            cid=table.item(row,0).data(Qt.ItemDataRole.UserRole)
            if cid:
                if copies:deck.cards[cid]=copies
                else:deck.cards.pop(cid,None)
        self._mark_dirty();self._fill_starter_cards();self._refresh_starter_decks()

    def _remove_starter_cards(self):
        deck=self._current_starter()
        if deck is None:return
        table=self.workspace_controls["Starter decks"]["cards"]
        for row in sorted({x.row() for x in table.selectedItems()}):
            cid=table.item(row,0).data(Qt.ItemDataRole.UserRole)
            if cid:deck.cards.pop(cid,None)
        self._mark_dirty();self._fill_starter_cards();self._refresh_starter_decks()

    def _refresh_mod_info(self):
        c=self.workspace_controls.get("Mod info")
        if not c:return
        info=self.project.info
        for key in ("id","name","version","author"):c[key].setText(getattr(info,key))
        c["description"].setPlainText(info.description)
        c["settings"].setPlainText(json.dumps(info.settings,indent=2,ensure_ascii=False) if info.settings else "")
        c["other"].setPlainText(json.dumps(self.project.other,indent=2,ensure_ascii=False) if self.project.other else "")

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
            reserved=set(other)&{"id","name","version","author","description","settings","cards","fusions","equips","rituals","drops","decks"}
            if reserved:raise ValueError(f"Edit {', '.join(sorted(reserved))} in the editor's own pages.")
        except ValueError as error:
            c["status"].setText(str(error));return False
        info=self.project.info
        before=(info.id,info.name,info.version,info.author,info.description,info.settings,self.project.other)
        info.id=mod_id;info.name=c["name"].text();info.version=c["version"].text().strip()
        info.author=c["author"].text();info.description=c["description"].toPlainText()
        info.settings=settings;self.project.other=other
        after=(info.id,info.name,info.version,info.author,info.description,info.settings,self.project.other)
        c["status"].setText("Changes applied." if after!=before else "No changes to apply.")
        if after!=before:self._mark_dirty()
        return True

    def _apply_campaign(self):
        c=self.workspace_controls["Campaign"]
        text=c["data"].toPlainText().strip()
        try:value=json.loads(text) if text else None
        except ValueError as problem:c["status"].setText(f"Invalid JSON: {problem}");return False
        if value is None:self.project.other.pop("story",None)
        else:self.project.other["story"]=value
        c["status"].setText("Story data applied to the mod manifest.");self._mark_dirty()
        return True

    def _refresh_problems(self):
        c=self.workspace_controls["Problems"];issues=validate.validate(self.project);table=c["table"]
        table.setRowCount(len(issues))
        for row,issue in enumerate(issues):
            for col,value in enumerate((issue.level.title(),issue.area+" · "+issue.where,issue.message)):
                table.setItem(row,col,QTableWidgetItem(str(value)))
        errors=sum(i.level=="error" for i in issues);warnings=len(issues)-errors
        c["summary"].setText(f"{errors} error(s) · {warnings} warning(s)" if issues else "No problems found.")

    def refresh_art_list(self, *_args, select_id=None):
        if not hasattr(self, "art_table") or self.project is None:
            return
        selected = self.current_art_card if select_id is None else select_id
        query = self.art_search.text().casefold().strip()
        filter_name = self.art_filter.currentText()
        changed = art.changed_cards(self.project)
        state = art.state(self.project)
        pack_cards = {cid for cid, _part in state.gated}
        pack_cards.update(cid for cid, _part in state.owned.values())
        visible_art_cards = changed | pack_cards
        self._update_art_pack_status(state)
        self.art_table.blockSignals(True)
        sorting_enabled = self.art_table.isSortingEnabled()
        sort_column = self.art_table.horizontalHeader().sortIndicatorSection()
        sort_order = self.art_table.horizontalHeader().sortIndicatorOrder()
        self.art_table.setSortingEnabled(False)
        self.art_table.setRowCount(0)
        for cid, card in sorted(self.project.cards.items()):
            if filter_name == "Art of the mod" and cid not in visible_art_cards:
                continue
            if filter_name == "Added by the mod" and cid not in self.project.added:
                continue
            if query and query not in str(cid) and query not in card.name.casefold():
                continue
            row = self.art_table.rowCount()
            self.art_table.insertRow(row)
            part_names = []
            for part in art.PARTS:
                if (cid, part) in state.images:
                    part_names.append(art.LABELS[part])
                elif (cid, part) in state.gated:
                    part_names.append(art.LABELS[part] + " · pack")
            values = (f"{cid:03d}", card.name, ", ".join(part_names) if part_names else "Stock")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, cid)
                self.art_table.setItem(row, column, item)
        self.art_table.setSortingEnabled(sorting_enabled)
        if sorting_enabled and sort_column >= 0:
            self.art_table.sortItems(sort_column, sort_order)
        for row in range(self.art_table.rowCount()):
            if self.art_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == selected:
                self.art_table.selectRow(row)
                break
        self.art_count.setText(f"{self.art_table.rowCount()} cards")
        self.art_table.blockSignals(False)
        row = self.art_table.currentRow()
        if row >= 0:
            self.show_art_card(self.art_table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        else:
            self.show_art_card(None)

    def _update_art_pack_status(self, state=None):
        label = getattr(self, "art_pack_status", None)
        if label is None:
            return
        state = state or art.state(self.project)
        folder = self.project.other.get("textures")
        if not isinstance(folder, str) or not folder:
            label.setText("Texture pack: none configured")
        elif state.problem:
            label.setText(f"Texture pack: {folder} · could not read manifest ({state.problem})")
        elif state.entries is None:
            label.setText(f"Texture pack: {folder} · manifest not loaded")
        else:
            card_entries = set(state.owned.values()) | set(state.gated)
            gated_count = len(state.gated)
            label.setText(
                f"Texture pack loaded: {folder} · {len(state.entries)} entries · "
                f"{len(card_entries)} card images recognized ({gated_count} setting-gated)")

    def select_art_card(self):
        row = self.art_table.currentRow()
        cid = self.art_table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None
        self.show_art_card(cid)

    @staticmethod
    def _show_art_image(label, image, scale, empty_text, canvas_size):
        if image is None:
            label.setPixmap(QPixmap())
            label.setText(empty_text)
            return
        qimage = _qimage(image.width, image.height, image.rgba)
        target = QSize(canvas_size.width(), canvas_size.height())
        # All cards in a category occupy the same preview area. Scaling is
        # applied before this display fit, so 1x/2x/4x still renders different
        # game output while the surrounding layout stays stable.
        qimage = qimage.scaled(target, Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.FastTransformation)
        label.setText("")
        label.setPixmap(QPixmap.fromImage(qimage))

    def _change_art_scale(self, part, index):
        """Refresh that part's game render as soon as its scale is changed."""
        cid = getattr(self, "current_art_card", None)
        if cid is None or self.files is None or cid not in self.project.cards:
            return
        scale = index if index in (1, 2, 4) else 1
        image = art.in_game(self.project, self.files.wa, cid, part, scale)
        canvas = {"art": QSize(240, 226), "thumbnail": QSize(180, 144),
                  "title": QSize(288, 42)}[part]
        self._show_art_image(self.art_previews[part]["game"], image, scale,
                             "Not available", canvas)
        if image is not None:
            self.art_info[part]["game"].setText(
                f"{scale}× game render · {image.width} × {image.height} px · fitted to the category preview.")

    def show_art_card(self, cid):
        self.current_art_card = cid
        if cid is None or cid not in self.project.cards or self.files is None:
            self.art_heading.setText("Select a card")
            for part, previews in self.art_previews.items():
                for kind, label in previews.items():
                    label.setPixmap(QPixmap())
                    label.setText("Choose a card" if kind != "mod" else "No replacement")
                for kind, label in self.art_info[part].items():
                    if isinstance(label, QLabel):
                        label.setText("")
            self.art_status.setText("Choose a card to view its original art and mod replacements.")
            return

        card = self.project.cards[cid]
        base = self.project.base_of(cid)
        self.art_heading.setText(self.project.card_label(cid))
        if cid in self.project.added:
            detail = f"Copy based on {self.project.card_label(base)}. Picture and thumbnail replacements are saved with the added card."
        else:
            detail = "Picture and thumbnail replacements for retail cards are stored in the mod texture pack."
        if self.art_instructions is not None:
            self.art_instructions.setText(detail + " Name plates are stored as a card title image.")
        notes = []
        for part in art.PARTS:
            try:
                disc_image = art.disc_image(self.files.wa, base, part)
                if part == "title":
                    disc_image = art.plate_image(art.disc_plate_inks(self.files.wa, base), background=art.GOLD)
                game_scale = self.art_scales[part].checkedId() or 1
                game_image = art.in_game(self.project, self.files.wa, cid, part, game_scale)
                mod_image = art.replacement_image(self.project, cid, part)
                gated = art.gated_image(self.project, cid, part) if mod_image is None and part != "title" else None
                if gated is not None:
                    mod_image = gated[0]
                if part == "title" and mod_image is not None:
                    mod_image = art.plate_image(art.plate_inks(mod_image), background=art.GOLD)
                _, where = art.shown_image(self.project, self.files.wa, cid, part)
                canvas = {"art": QSize(240, 226), "thumbnail": QSize(180, 144),
                          "title": QSize(288, 42)}[part]
                self._show_art_image(self.art_previews[part]["disc"], disc_image,
                                     {"art": 2, "thumbnail": 4, "title": 4}[part], "No disc image",
                                     canvas)
                self._show_art_image(self.art_previews[part]["game"], game_image,
                                     1, "Not available", canvas)
                self._show_art_image(self.art_previews[part]["mod"], mod_image,
                                     1, "No mod replacement", canvas)
                self.art_info[part]["disc"].setText("Original asset from the game data")
                dimensions = (f"{game_image.width} × {game_image.height} px"
                              if game_image is not None else "not available")
                self.art_info[part]["game"].setText(
                    f"{game_scale}× game render · {dimensions} · shown from {where}.")
                current_art_state = art.state(self.project)
                replacement = current_art_state.images.get((cid, part))
                self.art_info[part]["mod"].setText(art.describe(self.project, cid, part))
                self.art_info[part]["export_mod"].setEnabled(
                    replacement is not None or (cid, part) in current_art_state.gated)
                self.art_info[part]["revert"].setEnabled(replacement is not None)
            except (OSError, ValueError, art.pngio.PngError) as problem:
                notes.append(f"{art.LABELS[part]}: {problem}")
        self.art_status.setText("  ".join(notes) if notes else "Preview updated from the game files and current mod data.")

    def import_art(self, part):
        cid = self.current_art_card
        if cid is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Import {art.LABELS[part]}", "", "PNG images (*.png)")
        if not path:
            return
        try:
            image = art.pngio.read(path)
            original_size = image.size
            notes = art.set_image(self.project, cid, part, image)
        except (OSError, ValueError, art.pngio.PngError) as problem:
            QMessageBox.critical(self, "Could not import artwork", str(problem))
            return
        self.fusion_art_cache.clear()
        self._mark_dirty()
        self.refresh_art_list(select_id=cid)
        self._refresh_fusions()
        details = f"Imported {Path(path).name} ({original_size[0]}×{original_size[1]})."
        if notes:
            details += " " + " ".join(notes)
        self.art_status.setText(details)

    def export_art_disc(self, part):
        cid = self.current_art_card
        if cid is None:
            return
        base = self.project.base_of(cid)
        try:
            image = (art.plate_image(art.disc_plate_inks(self.files.wa, base)) if part == "title"
                     else art.disc_image(self.files.wa, base, part))
            self._save_art_image(cid, part, image, "disc")
        except (OSError, ValueError, art.pngio.PngError) as problem:
            QMessageBox.critical(self, "Could not export artwork", str(problem))

    def export_art_mod(self, part):
        cid = self.current_art_card
        if cid is None:
            return
        try:
            image = art.replacement_image(self.project, cid, part)
            if image is None and part != "title":
                gated = art.gated_image(self.project, cid, part)
                image = gated[0] if gated is not None else None
            if image is not None:
                self._save_art_image(cid, part, image, "mod")
        except (OSError, ValueError, art.pngio.PngError) as problem:
            QMessageBox.critical(self, "Could not export artwork", str(problem))

    def _save_art_image(self, cid, part, image, source):
        if image is None:
            return
        safe_name = "-".join(self.project.cards[cid].name.lower().split())
        suffix = {"art": "", "thumbnail": ".small", "title": ".title"}[part]
        default = f"{cid:04d}-{safe_name}{suffix}-{source}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export artwork", default, "PNG images (*.png)")
        if path:
            art.pngio.write(path, image)
            self.art_status.setText(f"Exported {path}")

    def revert_art(self, part):
        cid = self.current_art_card
        if cid is None:
            return
        if (cid, part) not in art.state(self.project).images:
            return
        art.revert(self.project, cid, part)
        self.fusion_art_cache.clear()
        self._mark_dirty()
        self.refresh_art_list(select_id=cid)
        self._refresh_fusions()

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("File")
        entries = (("New mod", self.new_mod, "Ctrl+N"),
                   ("Open mod folder…", self.open_mod, "Ctrl+O"),
                   ("Save", self.save_mod, "Ctrl+S"),
                   ("Save as…", lambda: self.save_mod(choose=True), "Ctrl+Shift+S"))
        for title, callback, shortcut in entries:
            action = file_menu.addAction(title)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
        file_menu.addSeparator()
        game_action = file_menu.addAction("Game files…")
        game_action.triggered.connect(self.choose_game_files)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)

        tools_menu = self.menuBar().addMenu("Tools")
        for title, callback in (("Check the mod", self.check_mod),
                                ("Preview mod.json", self.preview_manifest),
                                ("Card text preview", self.preview_card_text)):
            tools_menu.addAction(title).triggered.connect(callback)

        view_menu = self.menuBar().addMenu("View")
        passwords_action = view_menu.addAction("Show card passwords")
        passwords_action.setCheckable(True)
        passwords_action.setChecked(True)
        passwords_action.toggled.connect(self.toggle_password_visibility)
        refresh_action = view_menu.addAction("Refresh card preview")
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._render_preview)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About").triggered.connect(self.show_about)

    def choose_game_files(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the game's disc image", str(Path.cwd()),
            "Disc images (*.bin *.iso *.img);;All files (*)")
        if not path:
            path = QFileDialog.getExistingDirectory(
                self, "Or choose a folder with SLUS_014.11 and DATA/WA_MRG.MRG", str(Path.cwd()))
        if not path:
            return
        try:
            files = disc.load(path)
            retail = gamedata.load_game(files)
        except Exception as problem:
            QMessageBox.critical(self, "Game files", str(problem))
            return
        self.files = files
        self.retail = retail
        self.project = Project(retail)
        self.current = None
        self.frame_cache.clear()
        self.fusion_art_cache.clear()
        self.dirty = False
        self.refresh_cards(select_id=1)
        self.current_art_card = 1
        self.refresh_art_list(select_id=1)
        for name in self.NAV[2:]: self._refresh_workspace(name)
        self.game_label.setText("●  Game loaded")
        self.statusBar().showMessage(f"Game files: {files.source}")

    def check_mod(self):
        if self.current and not self.apply_card(quiet=True):
            return
        if self.current_workspace == "Mod info" and not self._apply_mod_info(): return
        if self.current_workspace == "Campaign" and not self._apply_campaign(): return
        issues = validate.validate(self.project)
        errors = validate.errors(issues)
        warnings = [issue for issue in issues if issue.level == "warning"]
        if not issues:
            QMessageBox.information(self, "Check the mod", "No problems found.")
            return
        details = "\n".join(str(issue) for issue in issues[:150])
        if len(issues) > 150:
            details += f"\n… and {len(issues) - 150} more."
        QMessageBox.warning(self, "Mod check",
                            f"{len(errors)} error(s), {len(warnings)} warning(s).\n\n{details}")

    def preview_manifest(self):
        if self.current and not self.apply_card(quiet=True):
            return
        if self.current_workspace == "Mod info" and not self._apply_mod_info():
            return
        if self.current_workspace == "Campaign" and not self._apply_campaign(): return
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview mod.json")
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        text.setPlainText(manifest.dumps(manifest.build(self.project)))
        layout.addWidget(text)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def preview_card_text(self):
        description = self.description.toPlainText()
        lines = validate.text_lines(description)
        dialog = QDialog(self)
        dialog.setWindowTitle("Card text preview")
        dialog.resize(460, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Preview of the selected card description (20 characters per game line):"))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(description)
        layout.addWidget(text, 1)
        layout.addWidget(QLabel(f"{lines} game line(s) · limit 8"))
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def toggle_password_visibility(self, visible):
        self.fields["password"].setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def show_about(self):
        QMessageBox.about(self, "About FM Editor",
                          "FM Editor\n\nMakes mods for the PC port of Yu-Gi-Oh! Forbidden Memories. "
                          "It reads retail tables from your game files and saves only mod changes. "
                          "It never writes to the disc or game folder.")

    def _panel(self, title: str):
        frame = QFrame(objectName="panel")
        frame.setProperty("class", "panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        heading = QLabel(title, objectName="heading")
        heading.setProperty("class", "heading")
        layout.addWidget(heading)
        return frame, layout

    def _build_cards(self, parent):
        ui_path = Path(__file__).with_name("ui") / "cards_page.ui"
        ui_file = QFile(str(ui_path))
        if not ui_file.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError(f"Could not open Cards Designer form {ui_path}: {ui_file.errorString()}")
        loader = QUiLoader()
        page = loader.load(ui_file, parent)
        ui_file.close()
        if page is None:
            raise RuntimeError(f"Could not load Cards Designer form {ui_path}: {loader.errorString()}")
        page_layout = QVBoxLayout(parent)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(page)
        self.cards_form = page

        def widget(widget_type, name):
            found = page.findChild(widget_type, name)
            if found is None:
                raise RuntimeError(f"Cards Designer form is missing widget {name!r}")
            return found

        self.search = widget(QLineEdit, "cardSearchEdit")
        self.filter = widget(QComboBox, "cardFilterCombo")
        self.advanced_filter_button = widget(QPushButton, "advancedCardFilterButton")
        self.filter.setMaximumWidth(190)
        self.advanced_card_filters = {"types": set(), "attributes": set(), "bounds": {}}
        self.listing = widget(QTableWidget, "cardTable")
        self.card_count = widget(QLabel, "cardCountLabel")
        self.add_button = widget(QPushButton, "addCopyButton")
        designer_card_id = widget(QSpinBox, "cardIdSpinBox")
        self.card_id = CardIdSpinBox(designer_card_id.parentWidget())
        self.card_id.setObjectName(designer_card_id.objectName())
        self.card_id.setRange(designer_card_id.minimum(), designer_card_id.maximum())
        self.card_id.setReadOnly(True)
        designer_card_id.parentWidget().layout().replaceWidget(designer_card_id, self.card_id)
        designer_card_id.deleteLater()
        self.description = widget(QTextEdit, "descriptionEdit")
        self.description_status = widget(QLabel, "descriptionStatusLabel")
        self.notes = widget(QTextEdit, "notesEdit")
        self.added_panel = widget(QFrame, "addedCardPanel")
        self.key_edit = widget(QLineEdit, "stableKeyEdit")
        self.drops = widget(QCheckBox, "dropsCheckBox")
        self.opponents = widget(QCheckBox, "opponentsCheckBox")
        self.base_card_info = widget(QLabel, "baseCardInfoLabel")
        self.apply_button = widget(QPushButton, "applyButton")
        self.remove_button = widget(QPushButton, "removeCopyButton")
        self.validation = widget(QLabel, "validationLabel")
        self.preview_image = widget(QLabel, "previewImageLabel")
        self.disc_preview_button = widget(QPushButton, "discPreviewButton")
        self.hd_preview_button = widget(QPushButton, "hdPreviewButton")
        self.fields = {
            "name": widget(QLineEdit, "nameEdit"),
            "type": widget(QComboBox, "typeCombo"),
            "attribute": widget(QComboBox, "attributeCombo"),
            "level": widget(QSpinBox, "levelSpinBox"),
            "star1": widget(QComboBox, "guardian1Combo"),
            "star2": widget(QComboBox, "guardian2Combo"),
            "attack": widget(QSpinBox, "attackSpinBox"),
            "defense": widget(QSpinBox, "defenseSpinBox"),
            "frame": widget(QComboBox, "frameCombo"),
            "password": widget(QLineEdit, "passwordEdit"),
        }
        self.type_box = self.fields["type"]
        self.attribute_box = self.fields["attribute"]
        self.level_box = self.fields["level"]
        self.attack_box = self.fields["attack"]
        self.defense_box = self.fields["defense"]
        self.star1_box = self.fields["star1"]
        self.star2_box = self.fields["star2"]
        self.frame_box = self.fields["frame"]

        self.filter.addItems(self.FILTERS)
        self.type_box.addItems(TYPE_NAMES)
        self.attribute_box.addItems(["—"] + ATTRIBUTE_NAMES)
        self.star1_box.addItems(STAR_NAMES)
        self.star2_box.addItems(STAR_NAMES)
        self.frame_box.addItems(["By card type"] + FRAME_NAMES)
        self.listing.setHorizontalHeaderLabels(["ID", "Name"])
        self.listing.setAlternatingRowColors(True)
        self.listing.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.listing.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.listing.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.listing.setSortingEnabled(True)
        self.listing.verticalHeader().setVisible(False)
        self.listing.horizontalHeader().setStretchLastSection(True)
        self.listing.horizontalHeader().setSectionResizeMode(1, self.listing.horizontalHeader().ResizeMode.Stretch)
        self.attack_box.setRange(0, 5110)
        self.attack_box.setSingleStep(10)
        self.defense_box.setRange(0, 5110)
        self.defense_box.setSingleStep(10)
        self.card_id.setRange(1, 32766)
        self.card_id.setReadOnly(True)
        self.apply_button.setObjectName("primary")
        self.description_status.setStyleSheet("color:#9aacc4")
        self.card_count.setStyleSheet("color:#9aacc4")
        self.base_card_info.setStyleSheet("color:#9aacc4")
        self.validation.setStyleSheet("color:#ff7777")
        self.preview_image.setStyleSheet("background:#101a2a;border:1px solid #26374c;border-radius:7px")
        self.preview_mode_group = QButtonGroup(page)
        self.preview_mode_group.setExclusive(True)
        self.preview_mode_group.addButton(self.disc_preview_button)
        self.preview_mode_group.addButton(self.hd_preview_button)
        self.disc_preview_button.setCheckable(True)
        self.hd_preview_button.setCheckable(True)
        self.disc_preview_button.setChecked(True)
        for name in ("listTitle", "dataTitle", "previewTitle"):
            widget(QLabel, name).setStyleSheet("font-size:16px;font-weight:650;color:#f3f7fc")
        splitter = widget(QSplitter, "cardsSplitter")
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([370, 670, 600])

        self.search.textChanged.connect(self.refresh_cards)
        self.disc_preview_button.clicked.connect(lambda: self._set_preview_scale(1))
        self.hd_preview_button.clicked.connect(lambda: self._set_preview_scale(4))
        self.filter.currentTextChanged.connect(self.refresh_cards)
        self.advanced_filter_button.clicked.connect(self._open_advanced_card_filter)
        self.listing.itemSelectionChanged.connect(self.select_card)
        self.add_button.clicked.connect(self.add_card)
        self.description.textChanged.connect(self.update_text_count)
        self.apply_button.clicked.connect(self.apply_card)
        widget(QPushButton, "revertButton").clicked.connect(self.revert_card)
        self.remove_button.clicked.connect(self.remove_card)
        for field in (self.fields["name"], self.fields["password"], self.key_edit):
            field.textChanged.connect(self._render_preview)
        self.type_box.currentIndexChanged.connect(self._type_changed)
        for field in (self.attribute_box, self.star1_box, self.star2_box, self.frame_box):
            field.currentIndexChanged.connect(self._render_preview)
        for field in (self.level_box, self.attack_box, self.defense_box):
            field.valueChanged.connect(self._render_preview)

    def _card_matches(self, cid, text):
        if not text:
            return True
        card = self.project.cards[cid]
        haystack = f"{cid} {card.name} {card.description} {self.project.notes.get(cid, '')}".casefold()
        return text.casefold().strip() in haystack

    def _open_advanced_card_filter(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Advanced card filters")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        lists = QHBoxLayout()
        type_list = self._checkable_list(TYPE_NAMES, dialog, height=8)
        attribute_list = self._checkable_list(ATTRIBUTE_NAMES, dialog, height=8)
        type_list.setMaximumHeight(164)
        attribute_list.setMaximumHeight(164)
        for title, listing in (("Card type", type_list), ("Attribute", attribute_list)):
            panel = QVBoxLayout()
            panel.addWidget(QLabel(title, dialog))
            panel.addWidget(listing)
            lists.addLayout(panel, 1)
        layout.addLayout(lists)
        ranges = QGridLayout()
        range_edits = {}
        for column, (label, low, high) in enumerate((("ATK", "atk_min", "atk_max"),
                                                     ("DEF", "def_min", "def_max"),
                                                     ("Level", "level_min", "level_max"))):
            ranges.addWidget(QLabel(label, dialog), 0, column * 3)
            ranges.addWidget(QLabel("Min", dialog), 1, column * 3)
            low_edit = QLineEdit(dialog)
            low_edit.setPlaceholderText("Any")
            value = self.advanced_card_filters["bounds"].get(low)
            low_edit.setText("" if value is None else str(value))
            ranges.addWidget(low_edit, 1, column * 3 + 1)
            ranges.addWidget(QLabel("Max", dialog), 2, column * 3)
            high_edit = QLineEdit(dialog)
            high_edit.setPlaceholderText("Any")
            value = self.advanced_card_filters["bounds"].get(high)
            high_edit.setText("" if value is None else str(value))
            ranges.addWidget(high_edit, 2, column * 3 + 1)
            range_edits[low], range_edits[high] = low_edit, high_edit
        layout.addLayout(ranges)
        for listing, values in ((type_list, self.advanced_card_filters["types"]),
                                (attribute_list, self.advanced_card_filters["attributes"])):
            for i in range(listing.count()):
                if i in values:
                    listing.item(i).setCheckState(Qt.CheckState.Checked)
        actions = QHBoxLayout()
        clear = QPushButton("Clear filters", dialog)
        cancel = QPushButton("Cancel", dialog)
        apply = QPushButton("Apply filters", dialog)
        apply.setObjectName("primary")
        actions.addWidget(clear)
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(apply)
        layout.addLayout(actions)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        dialog.setMinimumWidth(550)
        clear.clicked.connect(lambda: (self._clear_checkable_list(type_list),
                                       self._clear_checkable_list(attribute_list),
                                       [edit.clear() for edit in range_edits.values()]))
        cancel.clicked.connect(dialog.reject)
        apply.clicked.connect(dialog.accept)
        if not dialog.exec():
            return
        new_bounds = {}
        try:
            for key, edit in range_edits.items():
                value = edit.text().strip()
                new_bounds[key] = int(value) if value else None
            for label, low, high in (("ATK", "atk_min", "atk_max"), ("DEF", "def_min", "def_max"),
                                     ("Level", "level_min", "level_max")):
                if new_bounds[low] is not None and new_bounds[high] is not None and new_bounds[low] > new_bounds[high]:
                    raise ValueError(f"{label} minimum exceeds maximum")
        except ValueError as problem:
            QMessageBox.warning(self, "Advanced filters", str(problem))
            return
        self.advanced_card_filters = {
            "types": {i for i in range(type_list.count())
                      if type_list.item(i).checkState() == Qt.CheckState.Checked},
            "attributes": {i for i in range(attribute_list.count())
                           if attribute_list.item(i).checkState() == Qt.CheckState.Checked},
            "bounds": new_bounds,
        }
        self.refresh_cards(select_id=self.current)

    @staticmethod
    def _clear_checkable_list(listing):
        for i in range(listing.count()):
            listing.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _wanted(self, cid):
        card = self.project.cards[cid]
        kind = self.filter.currentText()
        if kind == "Changed" and not self.project.card_changed(cid): return False
        if kind == "Added by the mod" and cid not in self.project.added: return False
        if kind == "With notes" and cid not in self.project.notes: return False
        if kind == "Monsters" and not card.is_monster(): return False
        if kind == "Non-monsters" and card.is_monster(): return False
        if kind in TYPE_NAMES and card.type != TYPE_NAMES.index(kind): return False
        advanced = getattr(self, "advanced_card_filters", {})
        if advanced.get("types") and card.type not in advanced["types"]: return False
        if advanced.get("attributes") and (not card.is_monster() or card.attribute not in advanced["attributes"]): return False
        bounds = advanced.get("bounds", {})
        if not bulk_fusions._within(card.attack, bounds.get("atk_min"), bounds.get("atk_max")): return False
        if not bulk_fusions._within(card.defense, bounds.get("def_min"), bounds.get("def_max")): return False
        if not bulk_fusions._within(card.level, bounds.get("level_min"), bounds.get("level_max")): return False
        return self._card_matches(cid, self.search.text())

    def refresh_cards(self, *_args, select_id=None):
        if not hasattr(self, "listing") or self.project is None:
            return
        selected = select_id or self.current
        self._loading = True
        sorting_enabled = self.listing.isSortingEnabled()
        sort_column = self.listing.horizontalHeader().sortIndicatorSection()
        sort_order = self.listing.horizontalHeader().sortIndicatorOrder()
        self.listing.setSortingEnabled(False)
        self.listing.setRowCount(0)
        for cid in sorted(self.project.cards):
            if not self._wanted(cid): continue
            card = self.project.cards[cid]
            row = self.listing.rowCount(); self.listing.insertRow(row)
            for col, value in enumerate((f"{cid:03d}", card.name)):
                item = QTableWidgetItem(value)
                if col == 0: item.setData(Qt.ItemDataRole.UserRole, cid)
                self.listing.setItem(row, col, item)
        self.listing.setSortingEnabled(sorting_enabled)
        if sorting_enabled and sort_column >= 0:
            self.listing.sortItems(sort_column, sort_order)
        for row in range(self.listing.rowCount()):
            if self.listing.item(row, 0).data(Qt.ItemDataRole.UserRole) == selected:
                self.listing.selectRow(row)
                break
        if self.listing.currentRow() < 0 and self.listing.rowCount():
            self.listing.selectRow(0)
        self.card_count.setText(f"{self.listing.rowCount()} cards")
        self._loading = False
        if self.listing.currentRow() >= 0:
            self.select_card()
        else:
            self.show_card(None)

    def select_card(self):
        if self._loading:
            return
        row = self.listing.currentRow()
        if row < 0: return
        item = self.listing.item(row, 0)
        cid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if cid == self.current: return
        if self.current and not self.apply_card(quiet=True):
            self.refresh_cards(select_id=self.current)
            return
        self.show_card(cid)

    def show_card(self, cid):
        self._loading = True
        self.current = cid
        if not cid or cid not in self.project.cards:
            self.preview_image.clear();
            self._loading = False
            return
        card = self.project.cards[cid]
        self.card_id.setValue(cid)
        self.fields["name"].setText(card.name)
        self.fields["type"].setCurrentIndex(card.type)
        self._last_type_index = card.type
        self.fields["attribute"].setCurrentIndex(
            card.attribute + 1 if 0 <= card.attribute < len(ATTRIBUTE_NAMES) else -1)
        self.fields["level"].setValue(card.level)
        self.fields["attack"].setValue(card.attack)
        self.fields["defense"].setValue(card.defense)
        self.fields["star1"].setCurrentIndex(max(0,min(len(STAR_NAMES)-1,card.star1)))
        self.fields["star2"].setCurrentIndex(max(0,min(len(STAR_NAMES)-1,card.star2)))
        self._set_monster_fields_enabled(card.is_monster())
        self.fields["frame"].setCurrentIndex(card.frame + 1)
        self.fields["password"].setText(self.project.password(cid))
        self.description.setPlainText(card.description)
        self.notes.setPlainText(self.project.notes.get(cid, ""))
        added = self.project.added.get(cid)
        self.added_panel.setVisible(added is not None)
        self.remove_button.setVisible(added is not None)
        self.key_edit.setText(added.key if added else "")
        self.drops.setChecked(added.drops if added else True)
        self.opponents.setChecked(added.opponents if added else False)
        self.base_card_info.setText(f"Copy of {self.project.card_label(added.base)}" if added else "")
        self._render_preview()
        self.update_text_count()
        self.validation.setText("")
        self._loading = False
        self._render_preview()

    def _set_monster_fields_enabled(self, enabled):
        for name in ("attribute", "level", "attack", "defense", "star1", "star2"):
            self.fields[name].setEnabled(enabled)

    def _type_changed(self, index):
        previous = self._last_type_index
        self._last_type_index = index
        if self._loading:
            return
        monster = index < gamedata.TYPE_MAGIC
        if previous is not None and previous < gamedata.TYPE_MAGIC and not monster:
            self.fields["attribute"].setCurrentIndex(0)
            self.fields["level"].setValue(0)
            self.fields["attack"].setValue(0)
            self.fields["defense"].setValue(0)
            self.fields["star1"].setCurrentIndex(0)
            self.fields["star2"].setCurrentIndex(0)
        self._set_monster_fields_enabled(monster)
        self._render_preview()

    def _render_preview(self):
        if not self.current or self._loading: return
        try:
            card = self.project.cards[self.current].copy()
            card.name = self.fields["name"].text()
            card.type = self.fields["type"].currentIndex()
            monster = card.type < gamedata.TYPE_MAGIC
            card.attribute = max(0, self.fields["attribute"].currentIndex() - 1) if monster else 0
            card.level = self.fields["level"].value() if monster else 0
            card.attack = self.fields["attack"].value() if monster else 0
            card.defense = self.fields["defense"].value() if monster else 0
            card.star1 = self.fields["star1"].currentIndex() if monster else 0
            card.star2 = self.fields["star2"].currentIndex() if monster else 0
            card.frame = self.fields["frame"].currentIndex() - 1
            card.description = self.description.toPlainText()
            preview_project = Project.__new__(Project)
            preview_project.__dict__ = self.project.__dict__.copy()
            preview_project.cards = self.project.cards.copy()
            preview_project.cards[self.current] = card
            scale = self.preview_scale
            pixmap = _card_image(preview_project, self.files.wa, self.current, self.frame_cache, scale)
            interpolation = (Qt.TransformationMode.SmoothTransformation if scale == 4
                             else Qt.TransformationMode.FastTransformation)
            self.preview_image.setPixmap(pixmap.scaled(
                self.preview_image.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio, interpolation))
            card = preview_project.cards[self.current]
            kind = TYPE_NAMES[card.type] if 0 <= card.type < len(TYPE_NAMES) else "Unknown"
            attribute = ATTRIBUTE_NAMES[card.attribute] if 0 <= card.attribute < len(ATTRIBUTE_NAMES) else ""
            stars = [STAR_NAMES[s] for s in (card.star1, card.star2) if 0 < s < len(STAR_NAMES)]
        except (IndexError, ValueError, OSError, art.pngio.PngError) as problem:
            self.preview_image.clear()

    def _set_preview_scale(self, scale):
        self.preview_scale = scale
        self._render_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        controls = getattr(self, "workspace_controls", {}).get("Fusions")
        if controls:
            self._set_fusion_view(0 if controls["grid"].isChecked() else 1)
            self._sync_fusion_header()
        if self.current: self._render_preview()

    def update_text_count(self):
        count = _line_count(self.description.toPlainText())
        self.description_status.setText(f"{count} of 8 game lines · 20 characters per line")
        self.description_status.setStyleSheet("color:#ff7777" if count > 8 else "color:#9aacc4")
        if self.current: self._render_preview()

    def apply_card(self, quiet=False):
        cid = self.current
        if not cid: return True
        card = self.project.cards[cid].copy()
        card.name = self.fields["name"].text()
        card.type = self.fields["type"].currentIndex()
        monster = card.type < gamedata.TYPE_MAGIC
        card.attribute = max(0, self.fields["attribute"].currentIndex() - 1) if monster else 0
        card.level = self.fields["level"].value() if monster else 0
        card.attack = self.fields["attack"].value() if monster else 0
        card.defense = self.fields["defense"].value() if monster else 0
        card.star1 = self.fields["star1"].currentIndex() if monster else 0
        card.star2 = self.fields["star2"].currentIndex() if monster else 0
        card.frame = self.fields["frame"].currentIndex() - 1
        card.description = self.description.toPlainText()
        password = self.fields["password"].text().strip()
        if password and not (password.isascii() and password.isdigit() and len(password) <= 8):
            self.validation.setText("Password must be up to 8 digits, or blank.")
            return False
        password = password.zfill(8) if password else ""
        changed = not card.same(self.project.cards[cid])
        added = self.project.added.get(cid)
        if added:
            key = self.key_edit.text().strip()
            if not KEY_RE.fullmatch(key) or any(x.key == key and n != cid for n, x in self.project.added.items()):
                self.validation.setText("The stable key must use letters, digits, _ or - and be unique.")
                return False
            if key != added.key or added.drops != self.drops.isChecked() or added.opponents != self.opponents.isChecked():
                added.key = key; added.drops = self.drops.isChecked(); added.opponents = self.opponents.isChecked()
                changed = True
        notes = self.notes.toPlainText()
        if notes != self.project.notes.get(cid, ""):
            self.project.set_notes(cid, notes); changed = True
        if password != self.project.password(cid):
            self.project.set_password(cid, password); changed = True
        if changed:
            self.project.cards[cid] = card
            problems = validate.validate_card(self.project, cid)
            self.statusBar().showMessage(f"Updated {self.project.card_label(cid)}")
            self._mark_dirty()
        else:
            problems = []
        self.validation.setText("\n".join(i.message for i in problems))
        if changed:
            self.refresh_cards(select_id=cid)
            self.refresh_art_list(select_id=self.current_art_card)
            self._render_preview()
        return True

    def revert_card(self):
        cid = self.current
        if not cid: return
        if cid in self.project.added:
            QMessageBox.information(self, "Added card", "Added cards are copies. Remove and add a new copy to start over.")
            return
        self.project.revert_card(cid)
        self.show_card(cid)
        self.refresh_cards(select_id=cid)
        self.refresh_art_list(select_id=self.current_art_card)
        self.statusBar().showMessage("Restored retail card data")
        self._mark_dirty()

    def add_card(self):
        if not self.current: return
        if not self.apply_card(quiet=True): return
        source = self.project.cards[self.current]
        base = self.project.base_of(self.current)
        cid = self.project.add_card(base)
        self.project.cards[cid] = source.copy(id=cid, name=source.name + " II")
        self._mark_dirty()
        self.statusBar().showMessage(f"Added a copy: {self.project.card_label(cid)}")
        self.filter.setCurrentText("All cards")
        self.search.clear()
        self.refresh_cards(select_id=cid)
        self.refresh_art_list(select_id=cid)

    def remove_card(self):
        cid = self.current
        if cid not in self.project.added: return
        answer = QMessageBox.question(self, "Remove copy", "Remove this added card and rules that reference it?")
        if answer != QMessageBox.StandardButton.Yes: return
        self.project.remove_card(cid)
        self._mark_dirty()
        self.current = None
        self.refresh_cards(select_id=1)
        self.current_art_card = 1
        self.refresh_art_list(select_id=1)

    def new_mod(self):
        if not self.confirm_discard(): return
        self.project = Project(self.retail)
        self.fusion_art_cache.clear()
        self.duelist_selected_slot=0
        self.project.source_dir = None
        self.current = None
        self.refresh_cards(select_id=1)
        self.current_art_card = 1
        self.refresh_art_list(select_id=1)
        for name in self.NAV[2:]: self._refresh_workspace(name)
        self.setWindowTitle("FM Editor — New mod")
        self.dirty = False
        self.statusBar().showMessage("New mod · based on retail data")

    def open_mod(self):
        if not self.confirm_discard(): return
        folder = QFileDialog.getExistingDirectory(self, "Open mod folder")
        if folder: self.open_mod_path(folder)

    def open_mod_path(self, folder):
        try:
            project, messages = manifest.open_mod(self.retail, folder)
        except (ValueError, OSError) as problem:
            QMessageBox.critical(self, "Could not open mod", str(problem)); return
        self.project = project
        self.duelist_selected_slot=0
        self.current = None
        self.frame_cache.clear()
        self.fusion_art_cache.clear()
        self.dirty = False
        self.refresh_cards(select_id=1)
        self.current_art_card = 1
        self.refresh_art_list(select_id=1)
        for name in self.NAV[2:]: self._refresh_workspace(name)
        self.statusBar().showMessage(f"Opened {folder}" + (f" · {len(messages)} note(s)" if messages else ""))

    def save_mod(self, choose=False):
        if self.current and not self.apply_card(quiet=True): return
        if self.current_workspace == "Mod info" and not self._apply_mod_info(): return
        if self.current_workspace == "Campaign" and not self._apply_campaign(): return
        folder = str(self.project.source_dir or "")
        if choose or not folder:
            folder = QFileDialog.getExistingDirectory(self, "Save mod in folder")
            if not folder: return
            if (Path(folder) / "mod.json").exists() and Path(folder) != Path(self.project.source_dir or ""):
                answer = QMessageBox.question(self, "Replace mod files?",
                    f"{folder} already contains a mod. Replace its mod.json and matching files?")
                if answer != QMessageBox.StandardButton.Yes: return
        issues = validate.validate(self.project)
        errors = validate.errors(issues)
        if errors:
            answer = QMessageBox.question(self, "Mod validation",
                f"The game loader would reject {len(errors)} issue(s), including:\n\n{errors[0]}\n\nSave anyway?")
            if answer != QMessageBox.StandardButton.Yes: return
        try:
            path = manifest.save_mod(self.project, folder)
        except (ValueError, OSError) as problem:
            QMessageBox.critical(self, "Could not save mod", str(problem)); return
        self.statusBar().showMessage(f"Saved {path}")
        self.dirty = False
        self.setWindowTitle(f"{self.project.info.name} — FM Editor")

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.setWindowTitle("* " + self.project.info.name + " — FM Editor")

    def confirm_discard(self):
        if self.current and not self.apply_card(quiet=True): return False
        if self.current_workspace == "Mod info" and not self._apply_mod_info(): return False
        if self.current_workspace == "Campaign" and not self._apply_campaign(): return False
        if not self.dirty: return True
        answer = QMessageBox.question(self, "Unsaved changes", "Save changes to this mod before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel: return False
        if answer == QMessageBox.StandardButton.Save:
            self.save_mod()
            return not self.dirty
        return True

    def closeEvent(self, event):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def main(game=None, mod=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("FM Editor")
    try:
        window = ModernEditor(game, mod)
    except SystemExit as problem:
        return int(problem.code or 0)
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
