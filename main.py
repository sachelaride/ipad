import sys
import time
import traceback

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QMessageBox,
    QLineEdit, QSpinBox, QDialogButtonBox,
    QPlainTextEdit
)
from PyQt5.QtCore import QSettings, Qt, QThread, pyqtSignal, QTimer

from pymobiledevice3.lockdown import create_using_usbmux

from exploits import get_exploit
from exploits.common import parse_version
from exploits.itunesstored.itunesstored import (
    DEFAULT_ATTEMPTS, DEFAULT_BACKEND_URL, DEFAULT_PAYLOAD_TIMEOUT, ItunesstoredExploit
)


def load_settings():
    settings = QSettings()
    return {
        'backend_url': settings.value('backend_url', DEFAULT_BACKEND_URL, str),
        'attempts': settings.value('attempts', DEFAULT_ATTEMPTS, int),
        'timeout': settings.value('timeout', DEFAULT_PAYLOAD_TIMEOUT, int),
    }


def save_settings(settings):
    out = QSettings()
    out.setValue('backend_url', settings['backend_url'])
    out.setValue('attempts', settings['attempts'])
    out.setValue('timeout', settings['timeout'])


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')

        self.backend_url = QLineEdit(settings['backend_url'])
        self.backend_url.setPlaceholderText(DEFAULT_BACKEND_URL)
        self.backend_url.setMinimumWidth(320)

        self.attempts = QSpinBox()
        self.attempts.setRange(1, 99)
        self.attempts.setValue(settings['attempts'])

        self.timeout = QSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setSingleStep(15)
        self.timeout.setSuffix(' s')
        self.timeout.setValue(settings.get('timeout', DEFAULT_PAYLOAD_TIMEOUT))

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addRow(QLabel('<b>itunesstored</b>'))
        layout.addRow('Backend URL:', self.backend_url)
        layout.addRow('Attempts:', self.attempts)
        layout.addRow('Timeout:', self.timeout)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return {
            'backend_url': self.backend_url.text().strip() or DEFAULT_BACKEND_URL,
            'attempts': self.attempts.value(),
            'timeout': self.timeout.value(),
        }


class ActivationThread(QThread):
    status = pyqtSignal(str)
    log_message = pyqtSignal(str)
    success = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def emit_log(self, text):
        self.log_message.emit(text)
        short_line = text.splitlines()[0] if text else ''
        self.status.emit(short_line)

    def run(self):
        try:
            self.emit_log('[INIT] Conectando ao serviço lockdown via usbmux...')
            lockdown = create_using_usbmux()
            values = lockdown.get_value()

            product = values.get('ProductType', 'Unknown')
            version = values.get('ProductVersion', 'Unknown')
            build = values.get('BuildVersion', 'Unknown')
            act_state = values.get('ActivationState', 'Unknown')

            self.emit_log(f'[INIT] Dispositivo: {product} (iOS {version}, Build {build})')
            self.emit_log(f'[INIT] ActivationState atual: {act_state}')

            if act_state == 'Activated':
                self.emit_log('[INFO] Dispositivo já se encontra ativado!')
                self.success.emit('Device is already activated')
                return

            exploit_cls = get_exploit(parse_version(version), lockdown.udid)
            if exploit_cls is None:
                self.emit_log(f'[ERRO] Versão do iOS não suportada: {version}')
                self.error.emit(f'Unsupported iOS version: {version}')
                return

            self.emit_log(f'[INIT] Exploit selecionado: {exploit_cls.name}')
            self.emit_log('Ativando dispositivo...')
            exploit_cls(log=self.emit_log, **self.settings).run(lockdown)
            self.emit_log('[SUCESSO] Processo de ativação finalizado!')
            self.success.emit('Done!')

        except TimeoutError:
            err_msg = 'O dispositivo não reconectou a tempo após o reboot. Verifique o cabo USB e tente novamente.'
            self.emit_log(f'[ERRO] {err_msg}')
            self.error.emit(err_msg)
        except Exception as e:
            trace = traceback.format_exc()
            self.emit_log(f'[EXCEÇÃO CRÍTICA]\n{trace}')
            self.error.emit(f"{e}\n\nConsulte o console de debug para o log completo.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('hacktiv8 v1.2.2 (Debug Console)')
        self.setMinimumSize(640, 500)
        self.resize(720, 550)

        self.version = (0,)
        self.settings = load_settings()
        self._last_device_state = None

        self.status = QLabel('No device connected')
        self.status.setStyleSheet('font-weight: bold; font-size: 13px; color: #38bdf8;')

        self.activate = QPushButton('Activate Device')
        self.activate.setEnabled(False)
        self.activate.setMinimumHeight(32)

        self.settings_btn = QPushButton('\u2699')
        self.settings_btn.setFixedWidth(36)
        self.settings_btn.setMinimumHeight(32)
        self.settings_btn.setToolTip('Configurações (Backend URL, Tentativas, Timeout)')
        self.settings_btn.clicked.connect(self.open_settings)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.activate)
        row.addWidget(self.settings_btn)

        # Header do Console de Debug
        debug_header = QHBoxLayout()
        debug_label = QLabel('<b>Console de Logs e Diagnóstico em Tempo Real:</b>')
        
        self.btn_clear = QPushButton('Limpar Log')
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.clicked.connect(self.clear_log)

        self.btn_copy = QPushButton('Copiar Log')
        self.btn_copy.setFixedHeight(24)
        self.btn_copy.clicked.connect(self.copy_log)

        debug_header.addWidget(debug_label)
        debug_header.addStretch()
        debug_header.addWidget(self.btn_copy)
        debug_header.addWidget(self.btn_clear)

        # Caixa de texto do log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0f172a;
                color: #4ade80;
                font-family: 'Consolas', 'Courier New', 'DejaVu Sans Mono', monospace;
                font-size: 11px;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout()
        layout.addWidget(self.status)
        layout.addLayout(row)
        layout.addSpacing(10)
        layout.addLayout(debug_header)
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.activate.clicked.connect(self.start_activation)

        self.append_log("[SISTEMA] hacktiv8 inicializado. Aguardando conexão de dispositivo iOS via USB...")
        self.append_log(f"[CONFIG] Backend URL configurada: {self.settings['backend_url']}")
        self.append_log(f"[CONFIG] Tentativas: {self.settings['attempts']} | Timeout: {self.settings['timeout']}s")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_device)
        self.timer.start(1000)

    def append_log(self, text):
        timestamp = time.strftime('%H:%M:%S')
        formatted = f"[{timestamp}] {text}"
        self.log_view.appendPlainText(formatted)
        self.log_view.ensureCursorVisible()
        print(formatted, flush=True)

    def clear_log(self):
        self.log_view.clear()

    def copy_log(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_view.toPlainText())
        self.append_log("[SISTEMA] Logs copiados para a área de transferência.")

    def poll_device(self):
        try:
            lockdown = create_using_usbmux()
            values = lockdown.get_value()

            product = values.get('ProductType')
            version = values.get('ProductVersion')
            build = values.get('BuildVersion')
            version_tuple = parse_version(version)
            exploit_cls = get_exploit(version_tuple, lockdown.udid)
        except Exception:
            if self._last_device_state != 'disconnected':
                self._last_device_state = 'disconnected'
                self.append_log('[POLL] Nenhum dispositivo conectado via usbmux.')
            self._set_state('No device connected', False)
            return

        device_signature = f"{product}:{version}:{build}"
        if self._last_device_state != device_signature:
            self._last_device_state = device_signature
            self.append_log(f'[POLL] Dispositivo conectado: {product} (iOS {version}, Build {build}) | UDID: {lockdown.udid}')
            self.append_log(f'[POLL] Estado de ativação: {values.get("ActivationState", "Desconhecido")}')

        if exploit_cls is None:
            self._set_state(f'Unsupported {product} iOS version: {version}', False)
            return

        try:
            supported = exploit_cls.available(product, build, lockdown.udid, **self.settings)
        except Exception as e:
            self.append_log(f'[POLL] Erro ao consultar backend {self.settings["backend_url"]}: {e}')
            self._set_state('Could not reach backend. Please check your internet connection!', False)
            return

        if not supported:
            self._set_state(exploit_cls.unavailable.format(product=product, version=version), False)
            return

        self.version = version_tuple
        self._set_state(f'Connected: {product} ({version})', True)

    def _set_state(self, text, enabled):
        self.status.setText(text)
        self.activate.setEnabled(enabled)

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            self.settings = dialog.values()
            save_settings(self.settings)
            self.append_log(f"[CONFIG] Configurações salvas: URL={self.settings['backend_url']}, Tentativas={self.settings['attempts']}, Timeout={self.settings['timeout']}s")

    def start_activation(self):
        if ItunesstoredExploit.supports(self.version):
            note = 'Certifique-se de que o iPad está conectado ao Wi-Fi.'
        else:
            note = 'Seu dispositivo será reiniciado durante o processo.'

        QMessageBox.information(
            self,
            'Info',
            'O processo de ativação será iniciado.\n' + note
        )

        self.timer.stop()
        self.activate.setEnabled(False)

        self.append_log("=" * 55)
        self.append_log("[INÍCIO] Iniciando processo de ativação...")
        self.worker = ActivationThread(self.settings)
        self.worker.log_message.connect(self.append_log)
        self.worker.status.connect(self.status.setText)
        self.worker.success.connect(self.on_success)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_success(self, msg):
        self.status.setText(msg)
        self.append_log(f"[CONCLUÍDO] {msg}")
        QMessageBox.information(self, 'Success', msg)
        self.activate.setEnabled(True)
        self.timer.start(1000)

    def on_error(self, msg):
        self.append_log(f"[FALHA] {msg}")
        QMessageBox.critical(self, 'Error', msg)
        self.status.setText('Error occurred')
        self.timer.start(1000)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())