import logging
import sys
from pathlib import Path

from PySide6.QtCore import QIODevice, QFile
from PySide6.QtGui import QFontDatabase, QIcon
from app_context import AppContext
from core.error_handler import GuardedApplication
from ui.main_window import MainWindow

try:
    import resources_rc  # noqa: F401
except ImportError:
    resources_rc = None

logger = logging.getLogger(__name__)


def load_stylesheet(path: str | Path) -> str:
    if isinstance(path, str) and path.startswith(':/'):
        file = QFile(path)
        if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
            return ''
        try:
            return bytes(file.readAll()).decode('utf-8')
        finally:
            file.close()

    file_path = Path(path)
    if not file_path.exists():
        return ''
    return file_path.read_text(encoding='utf-8')


def rewrite_icon_paths(stylesheet: str, icons_root: Path) -> str:
    if ':/icons/' not in stylesheet:
        return stylesheet

    base_path = str(icons_root.resolve()).replace('\\', '/')
    return stylesheet.replace(':/icons/', f'{base_path}/')



def register_qt_material_fonts(base_dir: Path) -> None:
    for font_file in (base_dir / 'assets' / 'fonts' / 'roboto').glob('*.ttf'):
        QFontDatabase.addApplicationFont(str(font_file))


def main() -> None:
    
    app = GuardedApplication(sys.argv)
    base_dir = MainWindow.base_path()

    app.setWindowIcon(QIcon(str(base_dir / "assets" / "logo.ico")))

    register_qt_material_fonts(base_dir)

    base_qss = load_stylesheet(':/styles/qt_material_base.qss')
    material_qss = load_stylesheet(':/styles/material_theme.qss')

    if not base_qss:
        base_qss = load_stylesheet(base_dir / 'styles' / 'qt_material_base.qss')
        base_qss = rewrite_icon_paths(base_qss, base_dir / 'assets' / 'icons')
        material_qss = material_qss or load_stylesheet(base_dir / 'styles' / 'material_theme.qss')

    app.setStyle('Fusion')
    app.setStyleSheet('\n'.join(filter(None, [base_qss, material_qss])))

    context = AppContext()
    app.aboutToQuit.connect(context.shutdown)
    window = MainWindow(context)
    window.show()

    logger.info('Application started successfully.')
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
