#!/bin/bash
# Установщик Punto-подобного переключателя раскладки для macOS
# Запуск: bash setup.sh

set -e

APP_DIR="$HOME/punto"
PLIST="$HOME/Library/LaunchAgents/com.user.punto.plist"
PY_SCRIPT="$APP_DIR/punto.py"

echo "==> 1. Проверка Python 3"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 не найден. Установите его с https://www.python.org/downloads/ или командой: xcode-select --install"
  exit 1
fi
python3 --version

echo "==> 2. Создание виртуального окружения"
mkdir -p "$APP_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q pynput pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ApplicationServices

echo "==> 3. Копирование скрипта"
if [ ! -f "$PY_SCRIPT" ]; then
  if [ -f "$(dirname "$0")/punto.py" ]; then
    cp "$(dirname "$0")/punto.py" "$PY_SCRIPT"
  else
    echo "Не найден punto.py рядом с setup.sh"
    exit 1
  fi
fi

echo "==> 4. Настройка автозапуска (LaunchAgent)"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.punto</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_DIR/venv/bin/python</string>
        <string>$PY_SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$APP_DIR/punto.log</string>
    <key>StandardErrorPath</key>
    <string>$APP_DIR/punto.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo ""
echo "Готово! Punto запущен и будет стартовать при входе в систему."
echo ""
echo "ВАЖНО - выдайте разрешения (один раз):"
echo "  Системные настройки -> Конфиденциальность и безопасность ->"
echo "    * Мониторинг ввода (Input Monitoring) - добавьте Terminal (или Python из $APP_DIR/venv/bin)"
echo "    * Универсальный доступ (Accessibility) - добавьте Terminal (или Python)"
echo "Затем перезапустите: launchctl unload $PLIST && launchctl load $PLIST"
echo ""
echo "Логи: $APP_DIR/punto.err.log"
echo "Удалить автозапуск: launchctl unload $PLIST && rm $PLIST"
