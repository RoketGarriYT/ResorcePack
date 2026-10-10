
import sys
import os
import re
import csv
import html
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QFileDialog,
    QProgressBar, QTableWidget, QTableWidgetItem, QTextBrowser,
    QSplitter, QMessageBox, QHeaderView, QFrame, QComboBox
)


APP_NAME = "X_XSquad"
APP_VERSION = "2.0"


STYLESHEET = """
QMainWindow, QWidget {
    background-color: #101116;
    color: #e8e9f0;
    font-family: "Segoe UI";
    font-size: 13px;
}
QFrame#Panel {
    background-color: #171920;
    border: 1px solid #292c37;
    border-radius: 10px;
}
QLabel#Title {
    color: #ff414d;
    font-size: 25px;
    font-weight: 800;
}
QLabel#Subtitle {
    color: #8b90a2;
    font-size: 12px;
}
QLineEdit, QComboBox {
    background-color: #101116;
    color: #f0f0f5;
    border: 1px solid #343745;
    border-radius: 7px;
    padding: 10px;
    selection-background-color: #a82937;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #ff414d;
}
QPushButton {
    background-color: #272a34;
    color: #f0f0f5;
    border: 1px solid #373b49;
    border-radius: 7px;
    padding: 9px 15px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #353946;
    border-color: #ff414d;
}
QPushButton:disabled {
    color: #666a78;
    background-color: #1b1d24;
}
QPushButton#Primary {
    background-color: #e83243;
    border: 1px solid #ff4a58;
    color: white;
}
QPushButton#Primary:hover {
    background-color: #ff414d;
}
QPushButton#Danger {
    background-color: #70212a;
    border: 1px solid #a8323d;
}
QCheckBox {
    spacing: 8px;
    color: #c8cad4;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
}
QProgressBar {
    background-color: #101116;
    color: #ffffff;
    border: 1px solid #303340;
    border-radius: 5px;
    text-align: center;
    height: 15px;
}
QProgressBar::chunk {
    background-color: #f03b4b;
    border-radius: 4px;
}
QTableWidget {
    background-color: #14161d;
    alternate-background-color: #191c24;
    color: #e4e5ed;
    border: 1px solid #292c37;
    border-radius: 7px;
    gridline-color: #292c37;
    selection-background-color: #61232c;
    selection-color: white;
}
QHeaderView::section {
    background-color: #20232c;
    color: #bfc2cf;
    padding: 9px;
    border: none;
    border-bottom: 1px solid #343745;
    font-weight: 700;
}
QTextBrowser {
    background-color: #111319;
    color: #e8e9f0;
    border: 1px solid #292c37;
    border-radius: 7px;
    padding: 8px;
}
QScrollBar:vertical {
    background: #15171e;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #414451;
    border-radius: 4px;
    min-height: 25px;
}
QScrollBar::handle:vertical:hover {
    background: #e83243;
}
"""


def highlight_html(text, query, use_regex=False, case_sensitive=False):
    """Build safe HTML highlighting without modifying the original text."""
    if not query:
        return html.escape(text)

    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        pattern = re.compile(query if use_regex else re.escape(query), flags)
    except re.error:
        return html.escape(text)

    pieces = []
    last_end = 0

    for match in pattern.finditer(text):
        start, end = match.span()

        # Avoid infinite loops and zero-length regex matches.
        if start == end:
            continue

        pieces.append(html.escape(text[last_end:start]))
        pieces.append(
            '<span style="background-color:#ff414d;'
            'color:#ffffff;font-weight:bold;">'
            + html.escape(text[start:end])
            + '</span>'
        )
        last_end = end

    pieces.append(html.escape(text[last_end:]))
    return "".join(pieces)


class SearchWorker(QThread):
    result_found = pyqtSignal(dict)
    progress_changed = pyqtSignal(int, int)
    status_changed = pyqtSignal(str)
    search_finished = pyqtSignal(int, bool)
    search_error = pyqtSignal(str)

    def __init__(
        self,
        root_folder,
        query,
        use_regex=False,
        case_sensitive=False,
        parent=None
    ):
        super().__init__(parent)

        self.root_folder = Path(root_folder)
        self.query = query
        self.use_regex = use_regex
        self.case_sensitive = case_sensitive
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        total_matches = 0
        cancelled = False

        try:
            if self.use_regex:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                pattern = re.compile(self.query, flags)
            else:
                pattern = re.compile(
                    re.escape(self.query),
                    0 if self.case_sensitive else re.IGNORECASE
                )

            self.status_changed.emit("Сканирование файлов...")

            files = []

            for root, _, filenames in os.walk(self.root_folder):
                if self._stop_event.is_set():
                    cancelled = True
                    break

                for filename in filenames:
                    if filename.lower().endswith(".txt"):
                        files.append(Path(root) / filename)

            if cancelled:
                self.search_finished.emit(0, True)
                return

            total_files = len(files)

            if total_files == 0:
                self.status_changed.emit("TXT-файлы не найдены.")
                self.progress_changed.emit(0, 0)
                self.search_finished.emit(0, False)
                return

            for index, file_path in enumerate(files, start=1):
                if self._stop_event.is_set():
                    cancelled = True
                    break

                try:
                    # utf-8-sig handles ordinary UTF-8 and UTF-8 BOM.
                    # Replacement characters prevent one bad byte from
                    # stopping the entire scan.
                    with file_path.open(
                        "r",
                        encoding="utf-8-sig",
                        errors="replace"
                    ) as file:
                        for line_number, line in enumerate(file, start=1):
                            if self._stop_event.is_set():
                                cancelled = True
                                break

                            line = line.rstrip("\r\n")

                            if pattern.search(line):
                                total_matches += 1

                                self.result_found.emit({
                                    "file": file_path.name,
                                    "path": str(file_path),
                                    "line": line_number,
                                    "text": line
                                })

                        if cancelled:
                            break

                except (OSError, UnicodeError) as exc:
                    self.status_changed.emit(
                        f"Не удалось прочитать {file_path.name}: {exc}"
                    )

                self.progress_changed.emit(index, total_files)

            if cancelled:
                self.status_changed.emit("Поиск остановлен.")
            else:
                self.status_changed.emit(
                    f"Поиск завершён. Совпадений: {total_matches}"
                )

            self.search_finished.emit(total_matches, cancelled)

        except re.error as exc:
            self.search_error.emit(f"Ошибка регулярного выражения: {exc}")
            self.search_finished.emit(total_matches, False)

        except Exception as exc:
            self.search_error.emit(f"Ошибка поиска: {exc}")
            self.search_finished.emit(total_matches, False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} — TXT Scanner")
        self.resize(1200, 780)
        self.setMinimumSize(850, 600)

        self.worker = None
        self.results = []
        self.closing = False

        self.build_ui()
        self.setStyleSheet(STYLESHEET)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()

        title_box = QVBoxLayout()

        title = QLabel("X_XSquad")
        title.setObjectName("Title")

        subtitle = QLabel(
            "TXT Scanner  •  Поиск по текстовым файлам"
        )
        subtitle.setObjectName("Subtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        self.version_label = QLabel(f"VERSION {APP_VERSION}")
        self.version_label.setStyleSheet(
            "color:#ff414d;font-weight:700;"
            "background:#28191e;padding:8px 12px;border-radius:6px;"
        )
        header.addWidget(self.version_label)

        root.addLayout(header)

        # Search settings panel
        settings = QFrame()
        settings.setObjectName("Panel")

        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(15, 15, 15, 15)
        settings_layout.setSpacing(12)

        folder_row = QHBoxLayout()

        folder_row.addWidget(QLabel("Папка:"))

        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText(
            "Выбери папку с TXT-файлами..."
        )
        folder_row.addWidget(self.folder_input, 1)

        self.browse_button = QPushButton("Обзор")
        self.browse_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.browse_button)

        settings_layout.addLayout(folder_row)

        query_row = QHBoxLayout()

        query_row.addWidget(QLabel("Поиск:"))

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText(
            "Введи текст или регулярное выражение..."
        )
        self.query_input.returnPressed.connect(self.start_search)
        query_row.addWidget(self.query_input, 1)

        self.search_button = QPushButton("Начать поиск")
        self.search_button.setObjectName("Primary")
        self.search_button.clicked.connect(self.start_search)
        query_row.addWidget(self.search_button)

        self.stop_button = QPushButton("Остановить")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_search)
        query_row.addWidget(self.stop_button)

        settings_layout.addLayout(query_row)

        options_row = QHBoxLayout()

        self.regex_checkbox = QCheckBox("Regex")
        self.regex_checkbox.setToolTip(
            "Искать по регулярному выражению Python"
        )
        options_row.addWidget(self.regex_checkbox)

        self.case_checkbox = QCheckBox("Учитывать регистр")
        options_row.addWidget(self.case_checkbox)

        options_row.addStretch()

        self.export_format = QComboBox()
        self.export_format.addItems(["CSV", "TXT"])
        self.export_format.setMinimumWidth(90)
        options_row.addWidget(QLabel("Экспорт:"))
        options_row.addWidget(self.export_format)

        self.export_button = QPushButton("Экспорт результатов")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_results)
        options_row.addWidget(self.export_button)

        settings_layout.addLayout(options_row)

        root.addWidget(settings)

        # Progress and status
        progress_row = QHBoxLayout()

        self.status_label = QLabel("Готов к работе.")
        self.status_label.setObjectName("Subtitle")
        progress_row.addWidget(self.status_label, 1)

        self.counter_label = QLabel("0 совпадений")
        self.counter_label.setStyleSheet(
            "color:#ff5965;font-weight:700;"
        )
        progress_row.addWidget(self.counter_label)

        root.addLayout(progress_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        # Results table and preview
        splitter = QSplitter(Qt.Orientation.Vertical)

        results_panel = QFrame()
        results_panel.setObjectName("Panel")

        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(10, 10, 10, 10)

        results_title = QLabel("РЕЗУЛЬТАТЫ")
        results_title.setStyleSheet(
            "color:#aeb2c1;font-weight:700;padding:3px;"
        )
        results_layout.addWidget(results_title)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Файл", "Строка", "Совпадение", "Путь"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )

        self.table.itemSelectionChanged.connect(self.show_preview)
        self.table.cellDoubleClicked.connect(self.copy_selected_path)

        results_layout.addWidget(self.table)

        preview_panel = QFrame()
        preview_panel.setObjectName("Panel")

        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        preview_title = QLabel("ПРЕДПРОСМОТР")
        preview_title.setStyleSheet(
            "color:#aeb2c1;font-weight:700;padding:3px;"
        )
        preview_layout.addWidget(preview_title)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setPlaceholderText(
            "Выбери результат, чтобы увидеть строку."
        )
        preview_layout.addWidget(self.preview)

        splitter.addWidget(results_panel)
        splitter.addWidget(preview_panel)
        splitter.setSizes([470, 170])

        root.addWidget(splitter, 1)

        footer = QLabel(
            "X_XSquad Scanner  •  Поиск выполняется в отдельном потоке"
        )
        footer.setStyleSheet("color:#666b7c;font-size:11px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выбери папку с TXT-файлами",
            self.folder_input.text() or str(Path.home())
        )

        if folder:
            self.folder_input.setText(folder)

    def start_search(self):
        if self.worker is not None and self.worker.isRunning():
            return

        folder = self.folder_input.text().strip()
        query = self.query_input.text()

        if not folder:
            QMessageBox.warning(
                self, "Не выбрана папка",
                "Сначала выбери папку для поиска."
            )
            return

        if not Path(folder).is_dir():
            QMessageBox.warning(
                self, "Ошибка папки",
                "Указанная папка не существует или недоступна."
            )
            return

        if not query:
            QMessageBox.warning(
                self, "Пустой запрос",
                "Введи текст для поиска."
            )
            return

        # Validate regex before starting the thread.
        try:
            re.compile(
                query if self.regex_checkbox.isChecked()
                else re.escape(query),
                0 if self.case_checkbox.isChecked()
                else re.IGNORECASE
            )
        except re.error as exc:
            QMessageBox.warning(
                self, "Ошибка регулярного выражения", str(exc)
            )
            return

        self.results.clear()
        self.table.setRowCount(0)
        self.preview.clear()
        self.counter_label.setText("0 совпадений")
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Подготовка поиска...")

        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.browse_button.setEnabled(False)

        self.worker = SearchWorker(
            root_folder=folder,
            query=query,
            use_regex=self.regex_checkbox.isChecked(),
            case_sensitive=self.case_checkbox.isChecked()
        )

        self.worker.result_found.connect(self.add_result)
        self.worker.progress_changed.connect(self.update_progress)
        self.worker.status_changed.connect(self.update_status)
        self.worker.search_finished.connect(self.on_search_finished)
        self.worker.search_error.connect(self.show_search_error)

        self.worker.start()

    def stop_search(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.status_label.setText("Остановка поиска...")

    def add_result(self, result):
        self.results.append(result)

        row = self.table.rowCount()
        self.table.insertRow(row)

        values = [
            result["file"],
            str(result["line"]),
            result["text"],
            result["path"]
        ]

        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            self.table.setItem(row, column, item)

        self.counter_label.setText(
            f"{len(self.results)} совпадений"
        )

    def update_progress(self, current, total):
        # Indeterminate progress is used while collecting file names.
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            return

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(
            min(100, int(current * 100 / total))
        )

    def update_status(self, message):
        self.status_label.setText(message)

    def on_search_finished(self, total_matches, cancelled):
        self.progress_bar.setRange(0, 100)

        # A cancelled scan must not falsely display 100%.
        if cancelled:
            self.status_label.setText(
                f"Поиск остановлен. Найдено: {len(self.results)}"
            )
        else:
            self.progress_bar.setValue(100)
            self.status_label.setText(
                f"Готово. Найдено совпадений: {len(self.results)}"
            )

        self.counter_label.setText(
            f"{len(self.results)} совпадений"
        )

        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.browse_button.setEnabled(True)
        self.export_button.setEnabled(bool(self.results))

        # Do not delete the QThread while it is running.
        worker = self.worker
        if worker is not None:
            worker.quit()
            worker.wait()
            self.worker = None

    def show_search_error(self, message):
        self.status_label.setText("Поиск завершился с ошибкой.")
        QMessageBox.warning(self, "Ошибка поиска", message)

    def show_preview(self):
        selected = self.table.selectionModel().selectedRows()

        if not selected:
            self.preview.clear()
            return

        row = selected[0].row()

        if row < 0 or row >= len(self.results):
            return

        result = self.results[row]
        query = self.query_input.text()

        highlighted = highlight_html(
            result["text"],
            query,
            use_regex=self.regex_checkbox.isChecked(),
            case_sensitive=self.case_checkbox.isChecked()
        )

        path = html.escape(result["path"])
        filename = html.escape(result["file"])

        document = f"""
        <div style="font-family:Consolas,monospace;">
            <div style="color:#ff5965;font-weight:bold;">
                {filename} : строка {result["line"]}
            </div>
            <div style="color:#858b9e;font-size:11px;margin-top:4px;">
                {path}
            </div>
            <hr style="border:0;border-top:1px solid #343745;">
            <div style="white-space:pre-wrap;word-wrap:break-word;">
                {highlighted}
            </div>
        </div>
        """

        self.preview.setHtml(document)

    def copy_selected_path(self, row, column):
        if row < 0 or row >= len(self.results):
            return

        QApplication.clipboard().setText(self.results[row]["path"])
        self.status_label.setText("Путь к файлу скопирован.")

    def export_results(self):
        if not self.results:
            QMessageBox.information(
                self, "Нет результатов",
                "Сначала выполни поиск."
            )
            return

        extension = (
            ".csv" if self.export_format.currentText() == "CSV"
            else ".txt"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить результаты",
            str(Path.home() / f"X_XSquad_results{extension}"),
            "CSV (*.csv);;Text files (*.txt)"
        )

        if not filename:
            return

        output_path = Path(filename)

        # Ensure the file extension matches the selected filter.
        if output_path.suffix.lower() not in (".csv", ".txt"):
            output_path = output_path.with_suffix(extension)

        try:
            if output_path.suffix.lower() == ".csv":
                with output_path.open(
                    "w", newline="", encoding="utf-8-sig"
                ) as file:
                    writer = csv.writer(file)
                    writer.writerow(
                        ["File", "Line", "Text", "Full path"]
                    )

                    for result in self.results:
                        writer.writerow([
                            result["file"],
                            result["line"],
                            result["text"],
                            result["path"]
                        ])
            else:
                with output_path.open(
                    "w", encoding="utf-8-sig"
                ) as file:
                    for result in self.results:
                        file.write(
                            f'File: {result["file"]}\n'
                            f'Line: {result["line"]}\n'
                            f'Path: {result["path"]}\n'
                            f'Text: {result["text"]}\n'
                            f'{"-" * 60}\n'
                        )

            self.status_label.setText(
                f"Экспортировано: {output_path.name}"
            )

            QMessageBox.information(
                self, "Экспорт завершён",
                f"Результаты сохранены:\n{output_path}"
            )

        except OSError as exc:
            QMessageBox.critical(
                self, "Ошибка экспорта",
                f"Не удалось сохранить файл:\n{exc}"
            )

    def closeEvent(self, event):
        worker = self.worker

        if worker is not None and worker.isRunning():
            self.status_label.setText("Остановка поиска перед выходом...")
            worker.stop()

            # The worker checks the stop flag while scanning files and lines.
            # Wait until it exits to avoid destroying a running QThread.
            worker.wait()

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
