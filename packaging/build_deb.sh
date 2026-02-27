#!/bin/bash
# build_deb.sh
# Creates a .deb installer for FolderFlow

set -e
cd "$(dirname "$0")"/..

APP_NAME="folderflow"
DISPLAY_NAME="FolderFlow"
VERSION="1.0.0"
ARCH="amd64"
DESCRIPTION="Sincronizador de carpetas con Google Drive"
PKG_DIR="packaging/deb_build"

echo "==> Limpiando build anterior..."
rm -rf "$PKG_DIR"

echo "==> Preparando estructura del paquete .deb..."
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/local/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/pixmaps"

# 1. Copiar binario
echo "==> Copiando ejecutable..."
cp dist/FolderFlow "$PKG_DIR/usr/local/bin/$APP_NAME"
chmod 755 "$PKG_DIR/usr/local/bin/$APP_NAME"

# 2. Copiar ícono
echo "==> Copiando ícono..."
cp folderFlow-icon.png "$PKG_DIR/usr/share/pixmaps/folderflow.png"

# 3. Crear archivo .desktop (esto es lo que lo pone en el cajón de apps)
echo "==> Creando entrada de escritorio..."
cat > "$PKG_DIR/usr/share/applications/com.dialp.folderflow.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$DISPLAY_NAME
Comment=$DESCRIPTION
Exec=/usr/local/bin/$APP_NAME
Icon=/usr/share/pixmaps/folderflow.png
Terminal=false
Categories=Utility;FileTools;Network;
StartupWMClass=FolderFlow
EOF

# 4. Crear archivo de control del paquete
echo "==> Creando metadatos del paquete..."
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: libglib2.0-0, libgl1, libxcb-cursor0
Maintainer: dialp <dialp@github.com>
Description: $DESCRIPTION
 Sincronizador de archivos local-nube basado en Google Drive.
EOF

# 5. Script post-instalación para refrescar el caché de íconos
cat > "$PKG_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
update-desktop-database /usr/share/applications/ 2>/dev/null || true
gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# 6. Construir el .deb
echo "==> Compilando paquete .deb..."
dpkg-deb --build "$PKG_DIR" "dist/${APP_NAME}_${VERSION}_${ARCH}.deb"

echo ""
echo "✅ Paquete creado: dist/${APP_NAME}_${VERSION}_${ARCH}.deb"
echo "   Para instalar: sudo dpkg -i dist/${APP_NAME}_${VERSION}_${ARCH}.deb"
